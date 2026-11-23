"""Private, short-lived Ava conversation state with restart-safe confirmations."""

from collections import OrderedDict
from contextlib import contextmanager
import json
import logging
import os
import stat
import tempfile
import threading
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Stash's supported beta is macOS.
    fcntl = None


_MAX_CONVERSATIONS = 100
_CONVERSATION_TTL_SECONDS = 10 * 60
_MAX_STATE_BYTES = 8 * 1024 * 1024
_registry_lock = threading.RLock()
_conversations = OrderedDict()
_logger = logging.getLogger(__name__)


def _new_state():
    return {
        "last_result_set": [],
        "has_last_result_set": False,
        "last_search": None,
        "pending_action": None,
        "target_folder": None,
        "last_question": None,
        "last_question_request": None,
        "last_question_repeat_count": 0,
    }


def _valid_conversation_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return False
    return all(char.isalnum() or char in "-_" for char in value)


def _state_fields(state):
    """Persist only explicitly supported fields, never transient request flags."""
    allowed = _new_state()
    for key in allowed:
        if key in state:
            allowed[key] = state[key]
    if not isinstance(allowed["last_result_set"], list):
        allowed["last_result_set"] = []
    allowed["last_result_set"] = [
        item for item in allowed["last_result_set"][:5000]
        if isinstance(item, dict)
    ]
    allowed["has_last_result_set"] = bool(allowed["has_last_result_set"])
    if not isinstance(allowed["last_search"], dict):
        allowed["last_search"] = None
    if not isinstance(allowed["pending_action"], dict):
        allowed["pending_action"] = None
    if not isinstance(allowed["target_folder"], str):
        allowed["target_folder"] = None
    for key in ("last_question", "last_question_request"):
        value = allowed[key]
        allowed[key] = value[:2000] if isinstance(value, str) else None
    try:
        allowed["last_question_repeat_count"] = max(0, min(100, int(allowed["last_question_repeat_count"] or 0)))
    except (TypeError, ValueError, OverflowError):
        allowed["last_question_repeat_count"] = 0
    return allowed


def _validate_pending_action(value):
    if not isinstance(value, dict) or value.get("type") not in {"delete", "move"}:
        return None
    targets = value.get("targets")
    if not isinstance(targets, list) or not targets or len(targets) > 10000:
        return None
    normalized_targets = []
    for target in targets:
        target = str(target)
        if not target.isdecimal():
            return None
        normalized_targets.append(target)
    folder = value.get("folder")
    if value["type"] == "move" and (
        not isinstance(folder, str) or not folder.strip() or len(folder) > 48
    ):
        return None
    item_type = value.get("item_type")
    if item_type not in {None, "file", "text", "link", "image", "video", "audio"}:
        return None
    return {
        "type": value["type"],
        "targets": normalized_targets,
        "folder": folder,
        "item_type": item_type,
        "awaiting_confirmation": True,
        "dry_run": value.get("dry_run") is True,
    }


def _storage_paths(conversation_id, *, create):
    import storage_manager

    root = Path(storage_manager.STORAGE_DIR).resolve(strict=False)
    directory = root / "ava_sessions"
    if directory.is_symlink():
        raise OSError("Ava conversation storage cannot be a symbolic link.")
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    if directory.exists() and directory.resolve(strict=False).parent != root:
        raise OSError("Ava conversation storage resolved outside Stash storage.")
    return directory, directory / f"{conversation_id}.json", directory / f"{conversation_id}.lock"


@contextmanager
def _disk_lock(conversation_id):
    directory, state_path, lock_path = _storage_paths(conversation_id, create=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield directory, state_path
    finally:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _read_state_file(state_path):
    state = _new_state()
    try:
        info = state_path.lstat()
        if not stat.S_ISREG(info.st_mode) or state_path.is_symlink() or info.st_size > _MAX_STATE_BYTES:
            return state
        with state_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except FileNotFoundError:
        return state
    except (OSError, ValueError, json.JSONDecodeError) as error:
        _logger.warning("Could not read Ava conversation state (%s).", type(error).__name__)
        return state

    if not isinstance(payload, dict) or not isinstance(payload.get("state"), dict):
        return state
    stored = payload["state"]
    try:
        updated_at = float(payload.get("updated_at"))
    except (TypeError, ValueError, OverflowError):
        return state

    age = time.time() - updated_at
    if age < 0 or age > _CONVERSATION_TTL_SECONDS:
        expired = _validate_pending_action(stored.get("pending_action"))
        if expired:
            state["_expired_pending_action"] = expired
        return state

    state.update(_state_fields(stored))
    state["pending_action"] = _validate_pending_action(stored.get("pending_action"))
    return state


def _write_state_file(state_path, state, updated_at):
    persisted = {
        "version": 1,
        "updated_at": updated_at,
        "state": _state_fields(state),
    }
    encoded = json.dumps(persisted, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_STATE_BYTES:
        raise OSError("Ava conversation state exceeded its size limit.")
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".ava-session-", suffix=".tmp", dir=str(state_path.parent)
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, state_path)
        os.chmod(state_path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


@contextmanager
def conversation_state(conversation_id):
    """Yield serialized state for a chat ID, persisting it with a ten-minute TTL."""
    if not _valid_conversation_id(conversation_id):
        yield _new_state()
        return

    now = time.time()
    with _registry_lock:
        for key, record in list(_conversations.items()):
            if now - record["updated_at"] > _CONVERSATION_TTL_SECONDS:
                _conversations.pop(key, None)
        record = _conversations.get(conversation_id)
        if record is None:
            record = {"state": _new_state(), "lock": threading.RLock(), "updated_at": now}
            _conversations[conversation_id] = record
        _conversations.move_to_end(conversation_id)

    with record["lock"]:
        disk_lock = _disk_lock(conversation_id)
        try:
            _, state_path = disk_lock.__enter__()
        except OSError as error:
            _logger.warning("Ava conversation persistence is unavailable (%s).", type(error).__name__)
            try:
                yield record["state"]
            finally:
                record["updated_at"] = time.time()
        else:
            try:
                record["state"] = _read_state_file(state_path)
                state = record["state"]
                try:
                    yield state
                finally:
                    updated_at = time.time()
                    try:
                        _write_state_file(state_path, state, updated_at)
                    except (OSError, TypeError, ValueError) as error:
                        _logger.warning("Could not save Ava conversation state (%s).", type(error).__name__)
                    record["updated_at"] = updated_at
            finally:
                disk_lock.__exit__(None, None, None)

    with _registry_lock:
        while len(_conversations) > _MAX_CONVERSATIONS:
            _conversations.popitem(last=False)


def clear_all(*, preserve_disk=False):
    """Clear process memory; tests may also clear state inside their temp library."""
    with _registry_lock:
        _conversations.clear()
    if preserve_disk or os.environ.get("STASH_TEST_MODE") != "1":
        return
    try:
        from app_paths import is_temporary_storage
        import storage_manager

        root = storage_manager.STORAGE_DIR
        if not is_temporary_storage(root):
            return
        directory, _, _ = _storage_paths("test-cleanup", create=False)
        if directory.is_symlink() or not directory.is_dir():
            return
        for path in directory.glob("*.json"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
    except OSError as error:
        _logger.warning("Could not clear temporary Ava state (%s).", type(error).__name__)
