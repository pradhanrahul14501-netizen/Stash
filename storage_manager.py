import json
import os
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from io import BytesIO
from datetime import datetime, timedelta
from app_paths import BASE_DIR, STORAGE_DIR

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

from library_security import (
    decrypt_json,
    encrypt_media_file,
    encrypt_media_stream,
    encrypt_file_in_place,
    encrypt_json,
    initialize_library_encryption,
    is_encrypted_media,
)

MEDIA_DIR = os.path.join(STORAGE_DIR, "media")
STORAGE_FILE = os.path.join(STORAGE_DIR, "clipboard.json")
LIBRARY_LOCK_FILE = os.path.join(STORAGE_DIR, ".clipboard.lock")
ITEM_ID_COUNTER_FILE = os.path.join(STORAGE_DIR, ".next_item_id")
FOLDERS_FILE = os.path.join(STORAGE_DIR, "folders.json")
WORKSPACE_MODE_SETTINGS_FILE = os.path.join(STORAGE_DIR, "workspace_mode_settings.json")
PRIVACY_SETTINGS_FILE = os.path.join(STORAGE_DIR, "privacy_settings.json")
_STORAGE_LOCK = threading.RLock()
_LIBRARY_LOCK_STATE = threading.local()
_FOLDERS_LOCK = threading.RLock()
_WORKSPACE_MODE_SETTINGS_LOCK = threading.RLock()
_PRIVACY_SETTINGS_LOCK = threading.RLock()
_WORKSPACE_MODES = ("developer", "editor", "student")
_APP_BUNDLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,255}$")
_SITE_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


def secure_storage_permissions():
    os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(STORAGE_DIR, 0o700)
    except OSError:
        pass

    for directory in (
        MEDIA_DIR,
        os.path.join(STORAGE_DIR, "videos"),
        os.path.join(STORAGE_DIR, "shared_media"),
        os.path.join(STORAGE_DIR, "integrations"),
    ):
        if os.path.isdir(directory):
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass

    for filename in (
        "clipboard.json",
        ".clipboard.lock",
        ".next_item_id",
        "folders.json",
        "copy_maker.db",
        "copy_maker_auth.sqlite3",
        "shared_service.sqlite3",
        "firebase_auth_config.json",
        "firebase-admin.json",
        "workspace_mode_settings.json",
        "bin_settings.json",
        "privacy_settings.json",
        ".copy_maker_session_key",
        ".copy_maker_extension_token",
        ".copy_maker_totp_key",
    ):
        path = os.path.join(STORAGE_DIR, filename)
        if os.path.isfile(path):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass


@contextmanager
def _library_write_lock():
    """Serialize library read-modify-write transactions across threads and processes."""
    with _STORAGE_LOCK:
        depth = getattr(_LIBRARY_LOCK_STATE, "depth", 0)
        if depth:
            _LIBRARY_LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LIBRARY_LOCK_STATE.depth -= 1
            return

        os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
        descriptor = os.open(
            LIBRARY_LOCK_FILE,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        try:
            try:
                os.chmod(LIBRARY_LOCK_FILE, 0o600)
            except OSError:
                pass
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            elif msvcrt is not None:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                raise RuntimeError("This platform has no supported Stash library lock.")

            _LIBRARY_LOCK_STATE.depth = 1
            try:
                yield
            finally:
                _LIBRARY_LOCK_STATE.depth = 0
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                elif msvcrt is not None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(descriptor)


def _read_item_id_counter():
    try:
        with open(ITEM_ID_COUNTER_FILE, "r", encoding="ascii") as counter_file:
            value = int(counter_file.read().strip())
    except FileNotFoundError:
        return 0
    except (OSError, ValueError) as error:
        raise RuntimeError("Stash's item ID counter could not be read safely.") from error
    if value < 0:
        raise RuntimeError("Stash's item ID counter is invalid.")
    return value


def _write_item_id_counter(value):
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".next-item-id-",
        suffix=".tmp",
        dir=STORAGE_DIR,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as counter_file:
            counter_file.write(str(value))
            counter_file.flush()
            os.fsync(counter_file.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, ITEM_ID_COUNTER_FILE)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def _highest_item_id(items):
    highest = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            highest = max(highest, int(item.get("id", 0)))
        except (TypeError, ValueError, OverflowError):
            continue
    return highest


def _reserve_item_ids(items):
    highest = _highest_item_id(items)
    if highest > _read_item_id_counter():
        _write_item_id_counter(highest)


def _allocate_next_item_id(items):
    item_id = max(_highest_item_id(items), _read_item_id_counter()) + 1
    _write_item_id_counter(item_id)
    return item_id


def load_stash_folders():
    """Return saved user folder names, preserving their creation order."""
    with _FOLDERS_LOCK:
        try:
            with open(FOLDERS_FILE, "rb") as file:
                raw = file.read()
            folders, encrypted = decrypt_json(raw)
        except (json.JSONDecodeError, FileNotFoundError, OSError):
            return []

        if not encrypted:
            _write_stash_folders(folders)

        if not isinstance(folders, list):
            return []

        cleaned = []
        seen = set()
        for value in folders:
            if not isinstance(value, str):
                continue
            name = value.strip()
            key = name.casefold()
            if not name or len(name) > 48 or key in seen or key in {"unfiled", "all folders"}:
                continue
            cleaned.append(name)
            seen.add(key)
        return cleaned


def _write_stash_folders(folders):
    os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".folders-",
        suffix=".tmp",
        dir=STORAGE_DIR,
    )
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(encrypt_json(folders))
            file.flush()
            os.fsync(file.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, FOLDERS_FILE)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def create_stash_folder(name):
    if not isinstance(name, str):
        raise ValueError("Enter a folder name.")
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Enter a folder name.")
    if len(cleaned_name) > 48:
        raise ValueError("Folder names can be up to 48 characters.")
    if cleaned_name.casefold() in {"unfiled", "all folders"}:
        raise ValueError("That name is reserved for Stash navigation.")

    with _FOLDERS_LOCK:
        folders = load_stash_folders()
        if any(folder.casefold() == cleaned_name.casefold() for folder in folders):
            raise ValueError("A folder with that name already exists.")
        folders.append(cleaned_name)
        _write_stash_folders(folders)
        return folders


def move_items_to_stash_folder(item_ids, folder_name):
    """Update folder assignment for active copies in one atomic library write."""
    wanted_ids = set()
    for value in item_ids:
        try:
            wanted_ids.add(int(value))
        except (TypeError, ValueError, OverflowError):
            continue

    if not wanted_ids:
        return []

    with _library_write_lock():
        items = load_items()
        moved = []
        for item in items:
            if not isinstance(item, dict) or item.get("trashed_at"):
                continue
            try:
                matches = int(item.get("id", -1)) in wanted_ids
            except (TypeError, ValueError, OverflowError):
                matches = False
            if not matches:
                continue

            if folder_name is None:
                item.pop("folder_name", None)
            else:
                item["folder_name"] = folder_name
            moved.append(item)

        if moved:
            _write_items(items)
        return moved


def get_workspace_mode_settings():
    """Return the local automatic-sorting preferences, enabled by default."""
    with _WORKSPACE_MODE_SETTINGS_LOCK:
        try:
            with open(WORKSPACE_MODE_SETTINGS_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
        except (OSError, ValueError):
            saved = {}

        modes = saved.get("modes", saved) if isinstance(saved, dict) else {}
        if not isinstance(modes, dict):
            modes = {}
        return {mode: modes.get(mode) is not False for mode in _WORKSPACE_MODES}


def set_workspace_mode_setting(mode, enabled):
    if mode not in _WORKSPACE_MODES or not isinstance(enabled, bool):
        raise ValueError("Choose a valid Stash section and on/off setting.")

    storage_dir = os.path.dirname(WORKSPACE_MODE_SETTINGS_FILE)
    os.makedirs(storage_dir, mode=0o700, exist_ok=True)
    with _WORKSPACE_MODE_SETTINGS_LOCK:
        modes = get_workspace_mode_settings()
        modes[mode] = enabled
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".workspace-modes-",
            suffix=".tmp",
            dir=storage_dir,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump({"modes": modes}, file)
                file.flush()
                os.fsync(file.fileno())
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, WORKSPACE_MODE_SETTINGS_FILE)
        finally:
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass
    return modes


def infer_workspace_mode(item):
    """Classify a copy locally for the Developer, Editor, or Student section."""
    if not isinstance(item, dict):
        return None

    saved_mode = item.get("workspace_mode")
    if saved_mode in _WORKSPACE_MODES:
        return saved_mode

    item_type = str(item.get("type") or item.get("media_type") or "").lower()
    mime_type = str(item.get("mime_type") or "").lower()
    filename = str(item.get("original_name") or item.get("title") or item.get("file") or "")
    extension = os.path.splitext(filename.split("?", 1)[0])[1].lower()

    if (
        item_type in {"image", "audio", "video"}
        or mime_type.startswith(("image/", "audio/", "video/"))
        or extension in {
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg",
            ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus", ".aiff",
            ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpeg", ".mpg",
        }
    ):
        return "editor"

    if extension in {
        ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css",
        ".scss", ".json", ".yaml", ".yml", ".sh", ".bash", ".zsh", ".sql", ".java",
        ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb",
        ".swift", ".dart", ".vue", ".svelte", ".xml", ".toml", ".ipynb",
    }:
        return "developer"

    content = item.get("content")
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text:
        return None

    try:
        parsed_json = json.loads(text)
        if isinstance(parsed_json, (dict, list)):
            return "developer"
    except (json.JSONDecodeError, RecursionError):
        pass

    code_patterns = (
        r"(?m)^\s*(?:def|class|function|const|let|var|import|from\s+\S+\s+import|return|public\s+(?:static\s+)?(?:class|void)|#include)\b",
        r"(?m)^\s*(?:#!|<\/?(?:html|script|style|div|body|head)\b|SELECT\s+.+\s+FROM\s+)",
        r"(?m)^\s*(?:console\.log|printf|print|echo)\s*\(",
        r"(?m)^\s*(?:async\s+function|export\s+(?:default\s+)?(?:function|class|const))\b",
        r"```[\w+#.-]*\s*\n",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in code_patterns):
        return "developer"
    code_marks = len(re.findall(r"=>|===?|!==?|&&|\|\||</?\w+[^>]*>|[{};]", text))
    if code_marks >= 3 and re.search(r"\b(?:function|const|let|var|class|def|import|return|console\.log|print)\b", text):
        return "developer"

    study_terms = re.findall(
        r"\b(?:study|studies|student|teacher|lecture|class notes?|syllabus|homework|assignment|exam|quiz|flashcards?|revision|textbook|chapter|lesson|worksheet|coursework|lab report|research paper|practice problems?)\b",
        text,
        re.IGNORECASE,
    )
    strong_study_phrases = (
        r"\b(?:study guide|exam prep|lecture notes?|class notes?|homework|syllabus|flashcards?|worksheet|coursework)\b",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in strong_study_phrases):
        return "student"
    academic_topics = re.search(
        r"\b(?:photosynthesis|mitosis|osmosis|gravity|algebra|geometry|calculus|derivative|integral|newton(?:'s)? laws?|periodic table|cell division|theorem|equation|chemical reaction|atomic structure|ecosystem|evolution|world war|historical causes?|constitution|supply and demand|plate tectonics|probability|quadratic formula)\b",
        text,
        re.IGNORECASE,
    )
    learning_prompt = re.search(r"\b(?:explain|define|solve|summari[sz]e|compare and contrast|what is|how does|why does)\b", text, re.IGNORECASE)
    academic_explainer = re.search(r"\b(?:is the process|refers to|is defined as|is a type of|the formula for|the law of)\b", text, re.IGNORECASE)
    if len(study_terms) >= 2 or (academic_topics and (learning_prompt or academic_explainer)):
        return "student"

    return None


def load_items(*, read_only=False):
    with (_STORAGE_LOCK if read_only else _library_write_lock()):
        if not read_only:
            os.makedirs(STORAGE_DIR, exist_ok=True)

        if not os.path.exists(STORAGE_FILE):
            return []

        try:
            with open(STORAGE_FILE, "rb") as file:
                raw = file.read()
            items, encrypted = decrypt_json(raw)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            if read_only:
                raise
            return []

        # Convert the existing library once, atomically, so old clipboard text
        # does not remain in plaintext after the first protected read.
        if not encrypted and not read_only:
            _write_items(items)

        if read_only:
            return items

        # Finder can remove a copied video or file without going through Stash.
        # Drop only stale references into Stash-managed media folders so the
        # library and its counts stay aligned with files that still exist.
        if not isinstance(items, list):
            return items

        managed_roots = (
            os.path.abspath(MEDIA_DIR),
            os.path.abspath(os.path.join(STORAGE_DIR, "videos")),
            os.path.abspath(os.path.join(STORAGE_DIR, "shared_media")),
        )
        current_items = []
        removed_stale = False
        for item in items:
            file_path = item.get("file") if isinstance(item, dict) else None
            if not isinstance(file_path, str) or not file_path.strip():
                current_items.append(item)
                continue

            absolute_path = os.path.abspath(
                file_path if os.path.isabs(file_path) else os.path.join(BASE_DIR, file_path)
            )
            try:
                managed = any(
                    os.path.commonpath((root, absolute_path)) == root
                    and absolute_path != root
                    for root in managed_roots
                )
            except ValueError:
                managed = False

            if managed and not os.path.isfile(absolute_path):
                removed_stale = True
                continue
            current_items.append(item)

        if removed_stale:
            _write_items(current_items)
        return current_items


def _write_items(items):
    """Atomically persist clipboard metadata without exposing partial JSON."""
    os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".clipboard-",
        suffix=".tmp",
        dir=STORAGE_DIR
    )

    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(encrypt_json(items))
            file.flush()
            os.fsync(file.fileno())

        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, STORAGE_FILE)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def ensure_encrypted_media_storage():
    """Encrypt old local media in place before the web app starts serving it."""
    secure_storage_permissions()
    initialize_library_encryption()
    roots = (MEDIA_DIR, os.path.join(STORAGE_DIR, "videos"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            os.chmod(root, 0o700)
        except OSError:
            pass
        for current_root, _, filenames in os.walk(root):
            for filename in filenames:
                path = os.path.join(current_root, filename)
                if not os.path.isfile(path) or is_encrypted_media(path):
                    continue
                encrypt_file_in_place(path)
    if os.path.isfile(STORAGE_FILE):
        load_items()
    if os.path.isfile(FOLDERS_FILE):
        load_stash_folders()


def get_privacy_settings():
    defaults = {
        "capture_enabled": True,
        "retention_days": 0,
        "excluded_app_bundle_ids": [],
        "excluded_sites": [],
    }
    with _PRIVACY_SETTINGS_LOCK:
        try:
            with open(PRIVACY_SETTINGS_FILE, "r", encoding="utf-8") as source:
                value = json.load(source)
        except (OSError, ValueError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        retention_days = value.get("retention_days", defaults["retention_days"])
        if type(retention_days) is not int or retention_days not in {0, 1, 7, 30, 90, 365}:
            retention_days = defaults["retention_days"]
        app_ids = value.get("excluded_app_bundle_ids", [])
        sites = value.get("excluded_sites", [])
        if not isinstance(app_ids, list):
            app_ids = []
        if not isinstance(sites, list):
            sites = []
        app_ids = [item.strip() for item in app_ids[:100] if isinstance(item, str) and _APP_BUNDLE_ID_PATTERN.fullmatch(item.strip())]
        sites = [item.strip().lower().removeprefix("*.").lstrip(".") for item in sites[:100] if isinstance(item, str)]
        sites = [item for item in sites if _SITE_PATTERN.fullmatch(item)]
        return {
            "capture_enabled": value.get("capture_enabled") is not False,
            "retention_days": retention_days,
            "excluded_app_bundle_ids": app_ids,
            "excluded_sites": sites,
        }


def _validate_exclusion_list(values, pattern, label, *, normalize_site=False):
    if values is None:
        return None
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError(f"Choose up to 100 {label}.")
    normalized = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"Each {label[:-1]} must be text.")
        item = value.strip()
        if normalize_site:
            item = item.lower().removeprefix("*.").lstrip(".")
        if item and not pattern.fullmatch(item):
            raise ValueError(f"Enter valid {label[:-1]} values.")
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def set_privacy_settings(capture_enabled=None, retention_days=None, excluded_app_bundle_ids=None, excluded_sites=None):
    if capture_enabled is not None and not isinstance(capture_enabled, bool):
        raise ValueError("Choose whether Stash capture is on or paused.")
    if retention_days is not None and (
        type(retention_days) is not int or retention_days not in {0, 1, 7, 30, 90, 365}
    ):
        raise ValueError("Choose a supported retention period.")
    app_ids = _validate_exclusion_list(
        excluded_app_bundle_ids, _APP_BUNDLE_ID_PATTERN, "app bundle IDs"
    )
    sites = _validate_exclusion_list(
        excluded_sites, _SITE_PATTERN, "site domains", normalize_site=True
    )
    with _PRIVACY_SETTINGS_LOCK:
        settings = get_privacy_settings()
        if capture_enabled is not None:
            settings["capture_enabled"] = capture_enabled
        if retention_days is not None:
            settings["retention_days"] = retention_days
        if app_ids is not None:
            settings["excluded_app_bundle_ids"] = app_ids
        if sites is not None:
            settings["excluded_sites"] = sites
        os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".privacy-settings-", suffix=".tmp", dir=STORAGE_DIR
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(settings, output)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, PRIVACY_SETTINGS_FILE)
        finally:
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass
        return settings


def purge_expired_items(now=None):
    days = get_privacy_settings()["retention_days"]
    if not days:
        return 0
    cutoff_timestamp = (now or datetime.now()).timestamp() - timedelta(days=days).total_seconds()
    expired_ids = []
    for item in load_items():
        if not isinstance(item, dict):
            continue
        try:
            created_at = datetime.fromisoformat(str(item.get("created_at", "")))
        except (TypeError, ValueError):
            continue
        if created_at.timestamp() < cutoff_timestamp:
            expired_ids.append(item.get("id"))
    removed = 0
    for item_id in expired_ids:
        if delete_item(item_id) is not None:
            removed += 1
    return removed


def _encrypt_managed_media_paths(item):
    if not isinstance(item, dict):
        return
    managed_roots = (
        os.path.realpath(MEDIA_DIR),
        os.path.realpath(os.path.join(STORAGE_DIR, "videos")),
    )
    for key in ("file", "shareable_mp4_file"):
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        path = value if os.path.isabs(value) else os.path.join(BASE_DIR, value)
        path = os.path.realpath(path)
        try:
            managed = any(os.path.commonpath((root, path)) == root and path != root for root in managed_roots)
        except ValueError:
            managed = False
        if managed and os.path.isfile(path) and not is_encrypted_media(path):
            encrypt_file_in_place(path)


def save_metadata(item, *, id_reserved=False):
    with _library_write_lock():
        items = load_items()
        if isinstance(item, dict):
            if item.get("id") is None:
                item["id"] = _allocate_next_item_id(items)
                id_reserved = True
            else:
                try:
                    item_id = int(item.get("id"))
                except (TypeError, ValueError, OverflowError) as error:
                    raise ValueError("Stash item IDs must be integers.") from error
                existing_ids = {
                    int(existing["id"])
                    for existing in items
                    if isinstance(existing, dict)
                    and str(existing.get("id", "")).lstrip("-").isdigit()
                }
                if item_id in existing_ids:
                    raise ValueError("Stash item IDs must be unique.")
                _reserve_item_ids(items)
                if id_reserved:
                    if item_id > _read_item_id_counter():
                        raise ValueError("The Stash item ID was not reserved.")
                else:
                    if item_id <= _read_item_id_counter():
                        raise ValueError("Stash item IDs must be allocated by storage.")
                    _write_item_id_counter(item_id)

        _encrypt_managed_media_paths(item)
        if isinstance(item, dict):
            item["workspace_mode_checked"] = True
        if isinstance(item, dict) and not item.get("workspace_mode"):
            mode = infer_workspace_mode(item)
            if mode and get_workspace_mode_settings().get(mode, False):
                item["workspace_mode"] = mode
        items.append(item)
        _write_items(items)


def save_metadata_with_next_id(item):
    """Allocate a unique item ID and append metadata under one storage lock."""
    if not isinstance(item, dict):
        raise TypeError("Stash library metadata must be an object.")
    with _library_write_lock():
        items = load_items()
        existing_ids = set()
        for existing in items:
            if not isinstance(existing, dict):
                continue
            try:
                existing_ids.add(int(existing.get("id")))
            except (TypeError, ValueError, OverflowError):
                continue

        item_id = _allocate_next_item_id(items)
        while item_id in existing_ids:
            item_id += 1

        saved_item = dict(item)
        saved_item["id"] = item_id
        save_metadata(saved_item, id_reserved=True)
        return saved_item


def replace_items(items):
    """Atomically replace the encrypted library metadata."""
    if not isinstance(items, list):
        raise TypeError("Stash library items must be a list.")
    with _library_write_lock():
        _reserve_item_ids(items)
        for item in items:
            _encrypt_managed_media_paths(item)
        _write_items(items)
    return items


def next_item_id(items):
    """Reserve and return the next ID, preserving the library's high-water mark."""
    with _library_write_lock():
        return _allocate_next_item_id(load_items())


def save_item(item_type, content):
    with _library_write_lock():
        items = load_items()
        item_id = _allocate_next_item_id(items)

        item = {
            "id": item_id,
            "type": item_type,
            "content": content,
            "created_at": datetime.now().isoformat()
        }

        save_metadata(item, id_reserved=True)
        return item


def save_file(item_type, source_path):
    os.makedirs(MEDIA_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(MEDIA_DIR, 0o700)
    except OSError:
        pass

    if not os.path.isfile(source_path):
        raise FileNotFoundError(source_path)

    extension = os.path.splitext(source_path)[1]
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".stash-file-",
        suffix=extension,
        dir=MEDIA_DIR
    )
    os.close(descriptor)
    destination = None

    try:
        size = os.path.getsize(source_path)
        encrypt_media_file(source_path, temporary_path)
        with _library_write_lock():
            item_id = _allocate_next_item_id(load_items())
            filename = f"{item_type}_{item_id}{extension}"
            destination = os.path.join(MEDIA_DIR, filename)
            os.replace(temporary_path, destination)

            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass

            item = {
                "id": item_id,
                "type": item_type,
                "file": destination,
                "original_name": os.path.basename(source_path),
                "size": size,
                "created_at": datetime.now().isoformat()
            }

            save_metadata(item, id_reserved=True)
            return item
    except Exception:
        for path in (temporary_path, destination):
            if path:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        raise


def save_bytes(item_type, raw_bytes, extension):
    os.makedirs(MEDIA_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(MEDIA_DIR, 0o700)
    except OSError:
        pass

    if not extension.startswith("."):
        extension = "." + extension

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".stash-bytes-",
        suffix=extension,
        dir=MEDIA_DIR
    )
    destination = None

    try:
        with os.fdopen(descriptor, "wb") as file:
            encrypt_media_stream(BytesIO(raw_bytes), file, len(raw_bytes))
            file.flush()
            os.fsync(file.fileno())

        with _library_write_lock():
            item_id = _allocate_next_item_id(load_items())
            filename = f"{item_type}_{item_id}{extension}"
            destination = os.path.join(MEDIA_DIR, filename)
            os.replace(temporary_path, destination)

            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass

            item = {
                "id": item_id,
                "type": item_type,
                "file": destination,
                "original_name": filename,
                "size": len(raw_bytes),
                "created_at": datetime.now().isoformat()
            }

            save_metadata(item, id_reserved=True)
            return item
    except Exception:
        for path in (temporary_path, destination):
            if path:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        raise


def update_item(item_id, updates):
    with _library_write_lock():
        items = load_items()

        for item in items:
            try:
                matches_item = int(item.get("id", -1)) == int(item_id)
            except (TypeError, ValueError, OverflowError):
                continue

            if matches_item:
                item.update(updates)
                _encrypt_managed_media_paths(item)
                _write_items(items)
                return item

        return None


def update_items_fields(updates_by_id):
    """Apply field changes to current records without replacing a stale snapshot."""
    if not isinstance(updates_by_id, dict):
        raise TypeError("Stash item updates must be keyed by item ID.")

    normalized = {}
    for item_id, updates in updates_by_id.items():
        if not isinstance(updates, dict):
            continue
        try:
            key = str(int(item_id))
        except (TypeError, ValueError, OverflowError):
            continue
        normalized[key] = updates

    if not normalized:
        return []

    with _library_write_lock():
        items = load_items()
        changed = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                key = str(int(item.get("id")))
            except (TypeError, ValueError, OverflowError):
                continue
            updates = normalized.get(key)
            if updates is None:
                continue
            item.update(updates)
            _encrypt_managed_media_paths(item)
            changed.append(item)
        if changed:
            _write_items(items)
        return changed


def clear_legacy_auto_delete_schedules():
    """Remove the retired per-copy deletion dates without deleting any copies."""
    with _library_write_lock():
        items = load_items()
        cleared = 0
        for item in items:
            if isinstance(item, dict) and "auto_delete_at" in item:
                item.pop("auto_delete_at", None)
                cleared += 1
        if cleared:
            _write_items(items)
        return cleared


def delete_item(item_id, *, expected_item=None):
    with _library_write_lock():
        items = load_items()
        _reserve_item_ids(items)
        remaining = []
        deleted = None

        try:
            target_id = int(item_id)
        except (TypeError, ValueError, OverflowError):
            return None

        for item in items:
            try:
                stored_id = int(item.get("id", -1))
            except (AttributeError, TypeError, ValueError, OverflowError):
                # Preserve malformed or legacy records while allowing valid
                # scheduled items to be deleted from the same clipboard file.
                remaining.append(item)
                continue

            if stored_id == target_id:
                deleted = item
            else:
                remaining.append(item)

        if deleted is None:
            return None
        if expected_item is not None and deleted != expected_item:
            return None

        # Delete associated stored file.
        file_path = deleted.get("file")

        if file_path:
            if not os.path.isabs(file_path):
                file_path = os.path.join(BASE_DIR, file_path)

            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except OSError as error:
                print("⚠️ Could not delete media:", error)

        shareable_mp4_file = deleted.get("shareable_mp4_file")
        if shareable_mp4_file:
            if not os.path.isabs(shareable_mp4_file):
                shareable_mp4_file = os.path.join(BASE_DIR, shareable_mp4_file)
            shareable_mp4_file = os.path.realpath(shareable_mp4_file)
            original_file_path = deleted.get("file") or ""
            if not os.path.isabs(original_file_path):
                original_file_path = os.path.join(BASE_DIR, original_file_path)
            original_file_path = os.path.realpath(original_file_path)
            video_dir = os.path.realpath(os.path.join(STORAGE_DIR, "videos"))
            try:
                if (
                    os.path.commonpath((video_dir, shareable_mp4_file)) == video_dir
                    and os.path.isfile(shareable_mp4_file)
                    and original_file_path != shareable_mp4_file
                ):
                    os.remove(shareable_mp4_file)
            except (OSError, ValueError) as error:
                print("⚠️ Could not delete shareable MP4:", error)

        _write_items(remaining)

        return deleted
