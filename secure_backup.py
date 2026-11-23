"""Password-encrypted Stash backups and restart-time recovery staging."""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile

from app_paths import STORAGE_DIR
from library_security import (
    export_library_key_for_encrypted_backup,
    restore_library_key_from_encrypted_backup,
)


BACKUP_MAGIC = b"STASHBACKUP1\n"
MAX_BACKUP_BYTES = 50 * 1024 * 1024 * 1024
MAX_BACKUP_FILES = 200_000
MAX_BACKUP_PASSWORD_BYTES = 1024
MANIFEST_NAME = "__stash_backup_manifest__.json"
RESTORE_KEY_NAME = ".stash-library-key-for-restore"
RESTORE_READY_NAME = ".stash-restore-ready"
EXCLUDED_DIRECTORIES = {
    "python_packages",
    "__pycache__",
    ".git",
    ".pytest_cache",
}
EXCLUDED_FILES = {
    ".copy_maker_session_key",
    ".copy_maker_extension_token",
    ".clipboard.lock",
    MANIFEST_NAME,
    RESTORE_KEY_NAME,
    RESTORE_READY_NAME,
}


def _password_bytes(password):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Use a backup password with at least 12 characters.")
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_BACKUP_PASSWORD_BYTES:
        raise ValueError("The backup password is too long.")
    return encoded


def _derive_key(password, salt):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password)


def _is_excluded_file(name):
    return (
        name in EXCLUDED_FILES
        or name.endswith((".tmp", ".part", ".download", "-wal", "-shm"))
        or name.startswith(".stash-restore-")
    )


def _add_file_to_archive(archive, source_path, relative_path):
    """Use SQLite's online snapshot API for databases that may be open."""
    if not source_path.endswith((".sqlite3", ".db")):
        archive.write(source_path, relative_path, compress_type=zipfile.ZIP_STORED)
        return
    descriptor, snapshot_path = tempfile.mkstemp(prefix="stash-backup-db-", suffix=".sqlite3")
    os.close(descriptor)
    try:
        source = sqlite3.connect(source_path, timeout=10)
        destination = sqlite3.connect(snapshot_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        archive.write(snapshot_path, relative_path, compress_type=zipfile.ZIP_STORED)
    finally:
        try:
            os.remove(snapshot_path)
        except OSError:
            pass


def create_encrypted_backup(password):
    """Create a single AES-GCM encrypted backup file outside the library folder."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    password = _password_bytes(password)
    archive_fd, archive_path = tempfile.mkstemp(prefix="stash-backup-", suffix=".zip")
    encrypted_fd, encrypted_path = tempfile.mkstemp(prefix="stash-backup-", suffix=".stashbackup")
    os.close(encrypted_fd)
    os.chmod(archive_path, 0o600)
    os.chmod(encrypted_path, 0o600)
    try:
        os.close(archive_fd)
        manifest = {
            "format": 1,
            "created_at": int(time.time()),
            "library_key": base64.b64encode(export_library_key_for_encrypted_backup()).decode("ascii"),
        }
        with zipfile.ZipFile(archive_path, "w", allowZip64=True) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, separators=(",", ":")))
            file_count = 0
            for current_root, directories, filenames in os.walk(STORAGE_DIR, followlinks=False):
                directories[:] = sorted(
                    directory for directory in directories
                    if directory not in EXCLUDED_DIRECTORIES
                    and not os.path.islink(os.path.join(current_root, directory))
                )
                for filename in sorted(filenames):
                    if _is_excluded_file(filename):
                        continue
                    source_path = os.path.join(current_root, filename)
                    if os.path.islink(source_path) or not os.path.isfile(source_path):
                        continue
                    relative_path = os.path.relpath(source_path, STORAGE_DIR).replace(os.sep, "/")
                    if relative_path.startswith("../") or relative_path.startswith("/"):
                        raise ValueError("Stash found a file outside its library while making the backup.")
                    before = os.stat(source_path)
                    _add_file_to_archive(archive, source_path, relative_path)
                    after = os.stat(source_path)
                    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                        raise ValueError("A Stash file changed while the backup was being made. Wait for copying to finish and try again.")
                    file_count += 1
                    if file_count > MAX_BACKUP_FILES:
                        raise ValueError("This Stash library has too many files for one backup.")

        if os.path.getsize(archive_path) > MAX_BACKUP_BYTES - 1024:
            raise ValueError("This Stash library is larger than the 50 GB backup limit.")
        salt = os.urandom(16)
        nonce = os.urandom(12)
        header = BACKUP_MAGIC + salt + nonce
        key = _derive_key(password, salt)
        encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(header)
        with open(archive_path, "rb") as source, open(encrypted_path, "wb") as destination:
            destination.write(header)
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                destination.write(encryptor.update(chunk))
            destination.write(encryptor.finalize())
            destination.write(encryptor.tag)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(encrypted_path, 0o600)
        return encrypted_path
    except Exception:
        try:
            os.remove(encrypted_path)
        except OSError:
            pass
        raise
    finally:
        try:
            os.remove(archive_path)
        except OSError:
            pass


def _copy_upload_to_temp(upload_stream):
    descriptor, path = tempfile.mkstemp(prefix="stash-restore-upload-", suffix=".stashbackup")
    os.chmod(path, 0o600)
    total = 0
    try:
        with os.fdopen(descriptor, "wb") as target:
            while True:
                chunk = upload_stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BACKUP_BYTES:
                    raise ValueError("This backup is larger than Stash's 50 GB restore limit.")
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        return path, total
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


def _decrypt_backup(encrypted_path, password, zip_path):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    password = _password_bytes(password)
    size = os.path.getsize(encrypted_path)
    header_size = len(BACKUP_MAGIC) + 16 + 12
    if size < header_size + 16 or size > MAX_BACKUP_BYTES:
        raise ValueError("This Stash backup file is incomplete or too large.")
    with open(encrypted_path, "rb") as source:
        header = source.read(header_size)
        if not header.startswith(BACKUP_MAGIC):
            raise ValueError("This is not a Stash backup file.")
        salt_start = len(BACKUP_MAGIC)
        salt = header[salt_start:salt_start + 16]
        nonce = header[salt_start + 16:salt_start + 28]
        source.seek(size - 16)
        tag = source.read(16)
        source.seek(header_size)
        decryptor = Cipher(
            algorithms.AES(_derive_key(password, salt)),
            modes.GCM(nonce, tag),
        ).decryptor()
        decryptor.authenticate_additional_data(header)
        remaining = size - header_size - 16
        with open(zip_path, "wb") as destination:
            os.chmod(zip_path, 0o600)
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("This Stash backup file is incomplete.")
                remaining -= len(chunk)
                destination.write(decryptor.update(chunk))
            try:
                destination.write(decryptor.finalize())
            except Exception as error:
                raise ValueError("The backup password is incorrect or the file was changed.") from error
            destination.flush()
            os.fsync(destination.fileno())


def _safe_archive_path(name):
    if not isinstance(name, str) or not name or "\\" in name or name.startswith("/"):
        return False
    parts = name.split("/")
    return all(part not in {"", ".", ".."} for part in parts) and not (len(parts[0]) == 2 and parts[0][1] == ":")


def stage_restore(upload_stream, password):
    """Decrypt and validate a backup without replacing the live library yet."""
    upload_path = zip_path = None
    stage_path = STORAGE_DIR + ".restore-pending"
    if os.path.exists(stage_path):
        raise ValueError("A Stash restore is already waiting. Restart Stash before starting another.")
    try:
        upload_path, encrypted_size = _copy_upload_to_temp(upload_stream)
        if encrypted_size <= 0:
            raise ValueError("Choose a Stash backup file first.")
        zip_fd, zip_path = tempfile.mkstemp(prefix="stash-restore-", suffix=".zip")
        os.close(zip_fd)
        _decrypt_backup(upload_path, password, zip_path)
        parent = os.path.dirname(STORAGE_DIR)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        os.mkdir(stage_path, 0o700)
        with zipfile.ZipFile(zip_path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_BACKUP_FILES + 1:
                raise ValueError("This backup contains too many files.")
            manifest_info = next((item for item in infos if item.filename == MANIFEST_NAME), None)
            if not manifest_info or manifest_info.file_size > 16 * 1024:
                raise ValueError("This Stash backup is missing its recovery information.")
            manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("format") != 1:
                raise ValueError("This Stash backup format is not supported by this version.")
            try:
                library_key = base64.b64decode(manifest.get("library_key", ""), validate=True)
            except (ValueError, TypeError) as error:
                raise ValueError("The backup's Stash library key is invalid.") from error
            if len(library_key) != 32:
                raise ValueError("The backup's Stash library key is invalid.")
            total_uncompressed = 0
            restored_files = 0
            for info in infos:
                if info.filename == MANIFEST_NAME:
                    continue
                if not _safe_archive_path(info.filename):
                    raise ValueError("This backup contains an unsafe file path.")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise ValueError("This backup contains a symbolic link, which Stash will not restore.")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_BACKUP_BYTES:
                    raise ValueError("The restored library would exceed Stash's 50 GB restore limit.")
                destination = os.path.join(stage_path, *info.filename.split("/"))
                if info.is_dir():
                    os.makedirs(destination, mode=0o700, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(destination), mode=0o700, exist_ok=True)
                with archive.open(info, "r") as source, open(destination, "xb") as output:
                    os.chmod(destination, 0o600)
                    copied = 0
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > info.file_size:
                            raise ValueError("This backup contains an invalid file size.")
                        output.write(chunk)
                    if copied != info.file_size:
                        raise ValueError("This backup contains an incomplete file.")
                    output.flush()
                    os.fsync(output.fileno())
                restored_files += 1
            if not restored_files:
                raise ValueError("This Stash backup does not contain a library.")
        key_path = os.path.join(stage_path, RESTORE_KEY_NAME)
        with open(key_path, "xb") as key_file:
            os.chmod(key_path, 0o600)
            key_file.write(library_key)
            key_file.flush()
            os.fsync(key_file.fileno())
        with open(os.path.join(stage_path, RESTORE_READY_NAME), "x", encoding="ascii") as marker:
            marker.write("1")
        return {"success": True, "files": restored_files, "restart_required": True}
    except zipfile.BadZipFile as error:
        raise ValueError("The decrypted Stash backup archive is damaged.") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Stash could not safely prepare this backup for restore.") from error
    finally:
        for path in (upload_path, zip_path):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        if os.path.isdir(stage_path) and not os.path.exists(os.path.join(stage_path, RESTORE_READY_NAME)):
            shutil.rmtree(stage_path, ignore_errors=True)


def apply_pending_restore():
    """Apply a validated restore only during app startup, before storage opens."""
    stage_path = STORAGE_DIR + ".restore-pending"
    marker_path = os.path.join(stage_path, RESTORE_READY_NAME)
    if not os.path.isfile(marker_path):
        return False
    key_path = os.path.join(stage_path, RESTORE_KEY_NAME)
    with open(key_path, "rb") as key_file:
        new_key = key_file.read()
    if len(new_key) != 32:
        raise RuntimeError("The staged Stash recovery key is invalid.")

    old_key = export_library_key_for_encrypted_backup()
    old_storage = STORAGE_DIR + ".restore-previous"
    if os.path.exists(old_storage):
        raise RuntimeError("A previous Stash restore needs cleanup before this backup can be applied.")
    if os.path.exists(STORAGE_DIR):
        os.replace(STORAGE_DIR, old_storage)
    try:
        os.replace(stage_path, STORAGE_DIR)
        restore_library_key_from_encrypted_backup(new_key)
        # Recovery invalidates all browser sessions and browser-extension tokens.
        for name in (".copy_maker_session_key", ".copy_maker_extension_token", RESTORE_KEY_NAME, RESTORE_READY_NAME):
            try:
                os.remove(os.path.join(STORAGE_DIR, name))
            except FileNotFoundError:
                pass
        auth_database = os.path.join(STORAGE_DIR, "copy_maker_auth.sqlite3")
        if os.path.isfile(auth_database):
            import sqlite3

            connection = sqlite3.connect(auth_database, timeout=5)
            try:
                connection.execute("DELETE FROM owner_sessions")
                connection.commit()
            except sqlite3.Error:
                pass
            finally:
                connection.close()
        shutil.rmtree(old_storage, ignore_errors=True)
        try:
            os.chmod(STORAGE_DIR, 0o700)
        except OSError:
            pass
        return True
    except Exception:
        if os.path.isdir(STORAGE_DIR):
            shutil.rmtree(STORAGE_DIR, ignore_errors=True)
        if os.path.exists(old_storage):
            os.replace(old_storage, STORAGE_DIR)
        try:
            restore_library_key_from_encrypted_backup(old_key)
        except Exception:
            pass
        raise
