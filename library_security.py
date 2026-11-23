"""Transparent encryption for the local Stash library, backed by macOS Keychain."""

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from app_paths import BASE_DIR, STORAGE_DIR, is_temporary_storage

KEYCHAIN_BRIDGE = os.path.join(BASE_DIR, "keychain_bridge.swift")
JSON_MAGIC = b"STASHLIB1\n"
MEDIA_MAGIC = b"STASHMED1"
MEDIA_HEADER_SIZE = len(MEDIA_MAGIC) + 8
CHUNK_SIZE = 1024 * 1024
_KEY_LOCK = threading.RLock()
_KEY = None
_VENDORED_PACKAGES = os.path.join(STORAGE_DIR, "python_packages")
if os.path.isdir(_VENDORED_PACKAGES) and _VENDORED_PACKAGES not in sys.path:
    sys.path.insert(0, _VENDORED_PACKAGES)


class LibraryEncryptionError(RuntimeError):
    pass


def _run_keychain(command, input_bytes=b""):
    swift = shutil.which("swift") or "/usr/bin/swift"
    if not os.path.isfile(swift):
        raise LibraryEncryptionError(
            "Stash needs macOS Swift support to access its encrypted local library key."
        )
    try:
        result = subprocess.run(
            [swift, KEYCHAIN_BRIDGE, command],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LibraryEncryptionError("Stash could not access the macOS Keychain.") from error
    return result


def _get_key():
    global _KEY
    with _KEY_LOCK:
        if _KEY is not None:
            return _KEY
        if os.environ.get("STASH_TEST_MODE") == "1":
            configured_storage = os.environ.get("STASH_STORAGE_DIR")
            if not configured_storage or not is_temporary_storage(configured_storage):
                raise LibraryEncryptionError(
                    "Test encryption is allowed only with an explicit temporary storage directory."
                )
            return hashlib.sha256(b"stash-isolated-test-key-only").digest()
        result = _run_keychain("get")
        if result.returncode == 44:
            key = os.urandom(32)
            stored = _run_keychain("set", key)
            if stored.returncode != 0:
                raise LibraryEncryptionError("Stash could not save its library key in the macOS Keychain.")
        elif result.returncode == 0:
            try:
                key = base64.b64decode(result.stdout.strip(), validate=True)
            except (ValueError, base64.binascii.Error) as error:
                raise LibraryEncryptionError("The macOS Keychain returned an invalid Stash library key.") from error
        else:
            raise LibraryEncryptionError("Stash could not unlock its library key in the macOS Keychain.")
        if len(key) != 32:
            raise LibraryEncryptionError("The Stash library key has an invalid length.")
        _KEY = key
        return _KEY


def initialize_library_encryption():
    """Confirm Keychain access before Stash serves or writes local content."""
    _get_key()


def export_library_key_for_encrypted_backup():
    """Return the key only to the encrypted backup writer."""
    return bytes(_get_key())


def restore_library_key_from_encrypted_backup(key):
    """Restore a validated library key to this Mac's Keychain."""
    global _KEY
    value = bytes(key)
    if len(value) != 32:
        raise LibraryEncryptionError("The backup's Stash library key is invalid.")
    stored = _run_keychain("set", value)
    if stored.returncode != 0:
        raise LibraryEncryptionError("Stash could not restore the library key to macOS Keychain.")
    with _KEY_LOCK:
        _KEY = value


def encrypt_json(value):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    plaintext = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(_get_key()).encrypt(nonce, plaintext, JSON_MAGIC)
    return JSON_MAGIC + nonce + base64.urlsafe_b64encode(ciphertext)


def decrypt_json(raw):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not raw.startswith(JSON_MAGIC):
        return json.loads(raw.decode("utf-8")), False
    nonce_start = len(JSON_MAGIC)
    nonce = raw[nonce_start:nonce_start + 12]
    try:
        ciphertext = base64.urlsafe_b64decode(raw[nonce_start + 12:])
        plaintext = AESGCM(_get_key()).decrypt(nonce, ciphertext, JSON_MAGIC)
        return json.loads(plaintext.decode("utf-8")), True
    except Exception as error:
        if isinstance(error, LibraryEncryptionError):
            raise
        raise LibraryEncryptionError("The encrypted Stash library could not be opened.") from error


def is_encrypted_media(path):
    try:
        with open(path, "rb") as source:
            return source.read(len(MEDIA_MAGIC)) == MEDIA_MAGIC
    except OSError:
        return False


def encrypt_media_stream(source, destination, size):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_key()
    header = MEDIA_MAGIC + struct.pack(">Q", int(size))
    cipher = AESGCM(key)
    destination.write(header)
    index = 0
    remaining = int(size)
    while remaining:
        chunk = source.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise LibraryEncryptionError("A copied file changed while Stash was encrypting it.")
        nonce = os.urandom(12)
        aad = header + struct.pack(">II", index, len(chunk))
        encrypted = cipher.encrypt(nonce, chunk, aad)
        destination.write(struct.pack(">I", len(chunk)))
        destination.write(nonce)
        destination.write(encrypted)
        remaining -= len(chunk)
        index += 1
    if source.read(1):
        raise LibraryEncryptionError("A copied file changed while Stash was encrypting it.")


def encrypt_media_file(source_path, destination_path):
    if is_encrypted_media(source_path):
        shutil.copy2(source_path, destination_path)
        return
    size = os.path.getsize(source_path)
    with open(source_path, "rb") as source, open(destination_path, "wb") as destination:
        encrypt_media_stream(source, destination, size)
        destination.flush()
        os.fsync(destination.fileno())
    try:
        os.chmod(destination_path, 0o600)
    except OSError:
        pass


def media_plaintext_size(path):
    with open(path, "rb") as source:
        if source.read(len(MEDIA_MAGIC)) != MEDIA_MAGIC:
            return os.path.getsize(path)
        size_bytes = source.read(8)
        if len(size_bytes) != 8:
            raise LibraryEncryptionError("The encrypted Stash file header is incomplete.")
        return struct.unpack(">Q", size_bytes)[0]


def iter_decrypted_media(path, start=0, end=None):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with open(path, "rb") as source:
        magic = source.read(len(MEDIA_MAGIC))
        if magic != MEDIA_MAGIC:
            source.seek(0)
            while True:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
            return

        size_bytes = source.read(8)
        if len(size_bytes) != 8:
            raise LibraryEncryptionError("The encrypted Stash file header is incomplete.")
        size = struct.unpack(">Q", size_bytes)[0]
        if size == 0:
            return
        requested_end = size - 1 if end is None else min(int(end), size - 1)
        requested_start = max(0, int(start))
        if requested_start > requested_end:
            return
        first_index = requested_start // CHUNK_SIZE
        last_index = requested_end // CHUNK_SIZE
        record_size = 4 + 12 + CHUNK_SIZE + 16
        cipher = AESGCM(_get_key())
        header = magic + size_bytes
        for index in range(first_index, last_index + 1):
            source.seek(MEDIA_HEADER_SIZE + index * record_size)
            length_bytes = source.read(4)
            nonce = source.read(12)
            if len(length_bytes) != 4 or len(nonce) != 12:
                raise LibraryEncryptionError("The encrypted Stash file is incomplete.")
            length = struct.unpack(">I", length_bytes)[0]
            encrypted = source.read(length + 16)
            if length == 0 or len(encrypted) != length + 16:
                raise LibraryEncryptionError("The encrypted Stash file is incomplete.")
            aad = header + struct.pack(">II", index, length)
            try:
                plaintext = cipher.decrypt(nonce, encrypted, aad)
            except Exception as error:
                raise LibraryEncryptionError("An encrypted Stash file failed its integrity check.") from error
            block_start = index * CHUNK_SIZE
            trim_start = max(0, requested_start - block_start)
            trim_end = min(length, requested_end - block_start + 1)
            if trim_end > trim_start:
                yield plaintext[trim_start:trim_end]


def decrypt_media_file(source_path, destination_path):
    with open(destination_path, "wb") as destination:
        for chunk in iter_decrypted_media(source_path):
            destination.write(chunk)
        destination.flush()
        os.fsync(destination.fileno())
    try:
        os.chmod(destination_path, 0o600)
    except OSError:
        pass


@contextmanager
def decrypted_temp_file(source_path, suffix=""):
    descriptor, temporary_path = tempfile.mkstemp(prefix=".stash-export-", suffix=suffix)
    os.close(descriptor)
    try:
        decrypt_media_file(source_path, temporary_path)
        yield temporary_path
    finally:
        try:
            os.remove(temporary_path)
        except OSError:
            pass


def encrypt_file_in_place(path):
    if is_encrypted_media(path) or not os.path.isfile(path):
        return False
    descriptor, temporary_path = tempfile.mkstemp(prefix=".stash-encrypted-", dir=os.path.dirname(path))
    os.close(descriptor)
    try:
        encrypt_media_file(path, temporary_path)
        os.replace(temporary_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return True
    finally:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
