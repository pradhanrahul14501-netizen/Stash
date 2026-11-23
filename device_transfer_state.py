"""Short-lived state for local Stash-to-Stash Wi-Fi transfers."""

import hashlib
import hmac
import ipaddress
import secrets
import threading
import time


PAIR_CODE_TTL_SECONDS = 10 * 60
TRANSFER_TTL_SECONDS = 30 * 60
MAX_TRANSFER_ITEMS = 100
MAX_TRANSFER_BYTES = 4 * 1024 * 1024 * 1024

_LOCK = threading.RLock()
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_PAIR_CODE_HASH = ""
_PAIR_CODE_EXPIRES = 0
_PAIR_CODE_ATTEMPTS = 0
_RECEIVER_READY = False
_RECEIVER_ERROR = ""
_TRANSFERS = {}
_JOBS = {}


def _purge_expired_transfers(now):
    for session_key, session in list(_TRANSFERS.items()):
        if now > session["expires"]:
            _TRANSFERS.pop(session_key, None)


def set_receiver_status(ready, error=""):
    global _RECEIVER_READY, _RECEIVER_ERROR
    with _LOCK:
        _RECEIVER_READY = bool(ready)
        _RECEIVER_ERROR = str(error or "")[:240]


def receiver_status():
    with _LOCK:
        return {"ready": _RECEIVER_READY, "error": _RECEIVER_ERROR}


def create_pair_code():
    global _PAIR_CODE_HASH, _PAIR_CODE_EXPIRES, _PAIR_CODE_ATTEMPTS
    code = secrets.token_hex(4).upper()
    with _LOCK:
        _PAIR_CODE_HASH = hashlib.sha256(code.encode("ascii")).hexdigest()
        _PAIR_CODE_EXPIRES = int(time.time()) + PAIR_CODE_TTL_SECONDS
        _PAIR_CODE_ATTEMPTS = 0
    return code, _PAIR_CODE_EXPIRES


def _private_lan_peer(remote_address):
    try:
        address = ipaddress.ip_address(str(remote_address or ""))
    except ValueError:
        return False
    return (
        address.version == 4
        and any(address in network for network in _RFC1918_NETWORKS)
    )


def begin_transfer(code, item_count, total_bytes, remote_address):
    global _PAIR_CODE_HASH, _PAIR_CODE_EXPIRES, _PAIR_CODE_ATTEMPTS
    if not _private_lan_peer(remote_address):
        raise ValueError("Transfers are allowed only from another device on a private Wi-Fi network.")
    if not isinstance(code, str) or not 1 <= len(code) <= 32:
        raise ValueError("Enter the current one-time code from the receiving laptop.")
    try:
        item_count = int(item_count)
        total_bytes = int(total_bytes)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("The selected copies could not be prepared for transfer.") from error
    if not 1 <= item_count <= MAX_TRANSFER_ITEMS:
        raise ValueError(f"Choose between 1 and {MAX_TRANSFER_ITEMS} copies at a time.")
    if not 0 <= total_bytes <= MAX_TRANSFER_BYTES:
        raise ValueError("This transfer is larger than Stash's 4 GB transfer limit.")

    candidate = hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()
    with _LOCK:
        now = int(time.time())
        _purge_expired_transfers(now)
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
            raise ValueError("That code expired or is incorrect. Create a new code on the receiving laptop.")

        _PAIR_CODE_HASH = ""
        _PAIR_CODE_EXPIRES = 0
        _PAIR_CODE_ATTEMPTS = 0
        token = secrets.token_urlsafe(32)
        _TRANSFERS[hashlib.sha256(token.encode("ascii")).hexdigest()] = {
            "expires": now + TRANSFER_TTL_SECONDS,
            "expected_items": item_count,
            "expected_bytes": total_bytes,
            "received_items": 0,
            "received_bytes": 0,
        }
        return token


def record_received_item(token, byte_count):
    key = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    try:
        byte_count = int(byte_count)
    except (TypeError, ValueError, OverflowError):
        return False
    with _LOCK:
        now = int(time.time())
        _purge_expired_transfers(now)
        session = _TRANSFERS.get(key)
        if not session or byte_count < 0:
            return False
        if session["received_items"] >= session["expected_items"]:
            return False
        if session["received_bytes"] + byte_count > session["expected_bytes"]:
            return False
        session["received_items"] += 1
        session["received_bytes"] += byte_count
        return True


def authorize_transfer(token, byte_count=None):
    key = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    try:
        byte_count = None if byte_count is None else int(byte_count)
    except (TypeError, ValueError, OverflowError):
        return False
    with _LOCK:
        now = int(time.time())
        _purge_expired_transfers(now)
        session = _TRANSFERS.get(key)
        return bool(
            session
            and session["received_items"] < session["expected_items"]
            and (byte_count is None or (
                byte_count >= 0
                and session["received_bytes"] + byte_count <= session["expected_bytes"]
            ))
        )


def finish_transfer(token):
    key = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    with _LOCK:
        session = _TRANSFERS.pop(key, None)
    if not session or int(time.time()) > session["expires"]:
        return False
    return (
        session["received_items"] == session["expected_items"]
        and session["received_bytes"] == session["expected_bytes"]
    )


def create_send_job(item_count, total_bytes):
    job_id = secrets.token_urlsafe(18)
    now = int(time.time())
    job = {
        "status": "starting",
        "message": "Connecting to the receiving laptop…",
        "item_count": int(item_count),
        "total_bytes": int(total_bytes),
        "completed_items": 0,
        "sent_bytes": 0,
        "current_name": "",
        "error": "",
        "created": now,
    }
    with _LOCK:
        for previous_job_id, previous_job in list(_JOBS.items()):
            if now - previous_job["created"] > 60 * 60:
                _JOBS.pop(previous_job_id, None)
        _JOBS[job_id] = job
    return job_id


def update_send_job(job_id, **changes):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        job.update(changes)
        return dict(job)


def get_send_job(job_id):
    with _LOCK:
        job = _JOBS.get(str(job_id or ""))
        if not job:
            return None
        if int(time.time()) - job["created"] > 60 * 60:
            _JOBS.pop(str(job_id), None)
            return None
        return dict(job)
