"""State and pairing helpers for the private-Wi-Fi Android companion link."""

import hashlib
import hmac
import os
import secrets
import tempfile
import threading
import time
import uuid

from storage_manager import STORAGE_DIR


_LOCK = threading.RLock()
_PAIR_CODE_HASH = ""
_PAIR_CODE_EXPIRES = 0
_PAIR_CODE_ATTEMPTS = 0
_ACTIONS = {}
_STATE_FILE = os.path.join(STORAGE_DIR, "mobile_companion.json")
_PAIR_CODE_TTL = 10 * 60
_ACTION_TTL = 5 * 60
_MAX_FOLLOW_UPS = 5000


def _read_state():
    try:
        from library_security import decrypt_json

        with open(_STATE_FILE, "rb") as state_file:
            state, _encrypted = decrypt_json(state_file.read())
    except (OSError, ValueError):
        state = {}
    return state if isinstance(state, dict) else {}


def _write_state(state):
    os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".mobile-companion-", suffix=".tmp", dir=STORAGE_DIR,
    )
    try:
        from library_security import encrypt_json

        with os.fdopen(descriptor, "wb") as state_file:
            state_file.write(encrypt_json(state))
            state_file.flush()
            os.fsync(state_file.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, _STATE_FILE)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def create_pair_code():
    global _PAIR_CODE_HASH, _PAIR_CODE_EXPIRES, _PAIR_CODE_ATTEMPTS
    code = secrets.token_hex(4).upper()
    with _LOCK:
        _PAIR_CODE_HASH = hashlib.sha256(code.encode("ascii")).hexdigest()
        _PAIR_CODE_EXPIRES = int(time.time()) + _PAIR_CODE_TTL
        _PAIR_CODE_ATTEMPTS = 0
    return code, _PAIR_CODE_EXPIRES


def exchange_pair_code(code, remote_address):
    global _PAIR_CODE_HASH, _PAIR_CODE_EXPIRES, _PAIR_CODE_ATTEMPTS
    try:
        import ipaddress

        address = ipaddress.ip_address(str(remote_address or ""))
    except ValueError as error:
        raise ValueError("Pairing is available only on a private Wi-Fi network.") from error
    if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local:
        raise ValueError("Pairing is available only on a private Wi-Fi network.")
    if not isinstance(code, str) or not 1 <= len(code) <= 32:
        raise ValueError("Enter the current one-time code shown in desktop Stash Settings.")
    candidate = hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
    with _LOCK:
        now = int(time.time())
        if (
            not _PAIR_CODE_HASH
            or now > _PAIR_CODE_EXPIRES
            or _PAIR_CODE_ATTEMPTS >= 5
            or not hmac.compare_digest(candidate, _PAIR_CODE_HASH)
        ):
            _PAIR_CODE_ATTEMPTS += 1
            if _PAIR_CODE_ATTEMPTS >= 5 or now > _PAIR_CODE_EXPIRES:
                _PAIR_CODE_HASH = ""
                _PAIR_CODE_EXPIRES = 0
            raise ValueError("That code expired or is incorrect. Create a new code in desktop Stash Settings.")
        _PAIR_CODE_HASH = ""
        _PAIR_CODE_EXPIRES = 0
        _PAIR_CODE_ATTEMPTS = 0
        token = secrets.token_urlsafe(32)
        state = _read_state()
        state["phone_token_hash"] = hashlib.sha256(token.encode("ascii")).hexdigest()
        state["paired_at"] = now
        _write_state(state)
        return token


def is_authorized(token):
    if not isinstance(token, str) or not token:
        return False
    candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _LOCK:
        expected = _read_state().get("phone_token_hash", "")
    return isinstance(expected, str) and bool(expected) and hmac.compare_digest(candidate, expected)


def is_paired():
    with _LOCK:
        token_hash = _read_state().get("phone_token_hash", "")
    return isinstance(token_hash, str) and len(token_hash) == 64


def unpair(token):
    if not is_authorized(token):
        return False
    with _LOCK:
        state = _read_state()
        state.pop("phone_token_hash", None)
        state.pop("paired_at", None)
        _write_state(state)
        _ACTIONS.clear()
    return True


def revoke_pairing():
    with _LOCK:
        state = _read_state()
        was_paired = bool(state.pop("phone_token_hash", None))
        state.pop("paired_at", None)
        _write_state(state)
        _ACTIONS.clear()
        return was_paired


def enqueue_action(confirmation_token, preview):
    action_id = uuid.uuid4().hex
    safe_preview = {
        key: preview.get(key)
        for key in ("operation", "by", "count", "message")
        if isinstance(preview.get(key), (str, int, float, bool))
    }
    all_items = preview.get("items", [])
    if not isinstance(all_items, list):
        all_items = []
    safe_preview["items_total"] = len(all_items)
    safe_preview["items_truncated"] = len(all_items) > 200
    safe_preview["items"] = [
        {
            key: item[key][:800] if isinstance(item.get(key), str) else item[key]
            for key in ("path", "destination", "size", "collision_suffix")
            if key in item and isinstance(item.get(key), (str, int, float, bool))
        }
        for item in all_items[:200]
        if isinstance(item, dict)
    ]
    with _LOCK:
        now = time.monotonic()
        for old_id, old_action in list(_ACTIONS.items()):
            if old_action["expires_at"] <= now:
                _ACTIONS.pop(old_id, None)
        _ACTIONS[action_id] = {
            "confirmation_token": confirmation_token,
            "preview": safe_preview,
            "status": "pending",
            "created_at": now,
            "expires_at": now + _ACTION_TTL,
        }
    return action_id


def list_actions():
    with _LOCK:
        now = time.monotonic()
        for action_id, action in list(_ACTIONS.items()):
            if action["expires_at"] <= now:
                _ACTIONS.pop(action_id, None)
        return [
            {"id": action_id, "preview": action["preview"], "status": action["status"]}
            for action_id, action in _ACTIONS.items()
            if action["status"] == "pending"
        ]


def decide_action(action_id, decision):
    if decision not in {"approved", "rejected"}:
        return None
    with _LOCK:
        action = _ACTIONS.get(str(action_id or ""))
        if not action or action["expires_at"] <= time.monotonic() or action["status"] != "pending":
            return None
        action["status"] = decision
        return {"id": action_id, "status": decision}


def claim_approved_action(action_id):
    with _LOCK:
        action = _ACTIONS.get(str(action_id or ""))
        if not action or action["expires_at"] <= time.monotonic() or action["status"] != "approved":
            return None
        action["status"] = "executing"
        return action.get("confirmation_token")


def finish_action(action_id, success, message):
    with _LOCK:
        action = _ACTIONS.get(str(action_id or ""))
        if not action:
            return False
        action["status"] = "executed" if success else "error"
        action["message"] = str(message or "")[:600]
        return True


def action_status(action_id):
    with _LOCK:
        action = _ACTIONS.get(str(action_id or ""))
        if not action or action["expires_at"] <= time.monotonic():
            _ACTIONS.pop(str(action_id or ""), None)
            return None
        return {"id": action_id, "status": action["status"], "message": action.get("message", "")}


def clear_action(action_id):
    with _LOCK:
        return _ACTIONS.pop(str(action_id or ""), None) is not None


def clear_action_by_confirmation(confirmation_token):
    with _LOCK:
        for action_id, action in list(_ACTIONS.items()):
            if action.get("confirmation_token") == confirmation_token:
                _ACTIONS.pop(action_id, None)


def get_follow_ups():
    with _LOCK:
        state = _read_state()
        values = state.get("follow_ups", [])
        return values if isinstance(values, list) else []


def merge_follow_ups(values):
    if not isinstance(values, list) or len(values) > _MAX_FOLLOW_UPS:
        raise ValueError("Stash could not sync this many reminders.")
    clean = []
    for value in values:
        if not isinstance(value, dict):
            continue
        follow_up_id = value.get("id")
        if not isinstance(follow_up_id, str) or not 1 <= len(follow_up_id) <= 80:
            continue
        record = {"id": follow_up_id}
        for key in ("sourceItemId", "sourceTitle", "eventLabel"):
            field = value.get(key, "")
            record[key] = field[:500] if isinstance(field, str) else ""
        for key in ("eventAt", "remindAt", "createdAt", "updatedAt", "deletedAt", "notifiedAt"):
            field = value.get(key)
            if field is None:
                record[key] = None
            elif isinstance(field, int) and 0 <= field <= 9_999_999_999_999:
                record[key] = field
            else:
                record[key] = None
        if not record["sourceItemId"] or not record["eventAt"] or not record["remindAt"]:
            continue
        clean.append(record)
    with _LOCK:
        state = _read_state()
        previous = state.get("follow_ups", [])
        by_id = {
            item["id"]: item
            for item in previous
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for item in clean:
            old = by_id.get(item["id"])
            if old is None or (item.get("updatedAt") or item.get("createdAt") or 0) >= (
                old.get("updatedAt") or old.get("createdAt") or 0
            ):
                same_version = old is not None and (
                    item.get("updatedAt") or item.get("createdAt") or 0
                ) == (old.get("updatedAt") or old.get("createdAt") or 0)
                if same_version and old.get("desktop_notified_for"):
                    item["desktop_notified_for"] = old["desktop_notified_for"]
                by_id[item["id"]] = item
        state["follow_ups"] = list(by_id.values())[-_MAX_FOLLOW_UPS:]
        _write_state(state)
        return state["follow_ups"]


def pop_due_follow_ups(now_ms=None):
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    due = []
    changed = False
    with _LOCK:
        state = _read_state()
        values = state.get("follow_ups", [])
        if not isinstance(values, list):
            return due
        for item in values:
            if not isinstance(item, dict) or item.get("deletedAt") is not None:
                continue
            remind_at = item.get("remindAt")
            version = item.get("updatedAt") or item.get("createdAt") or 0
            if isinstance(remind_at, int) and remind_at <= now_ms and item.get("desktop_notified_for") != version:
                item["desktop_notified_for"] = version
                due.append(dict(item))
                changed = True
        if changed:
            state["follow_ups"] = values
            _write_state(state)
    return due


PAIR_CODE_TTL_SECONDS = _PAIR_CODE_TTL
