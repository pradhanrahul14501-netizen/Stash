"""Encrypted storage and capture routing for Stash's private Vault."""

import base64
import json
import math
import os
import re
import secrets
import sys
import tempfile
import threading
from datetime import datetime
from app_paths import BASE_DIR, STORAGE_DIR

VAULT_FILE = os.path.join(STORAGE_DIR, "vault.json")
CAPTURE_SETTINGS_FILE = os.path.join(STORAGE_DIR, "vault_capture_settings.json")

# The project already vendors cryptography for its other server components.
_VENDORED_PACKAGES = os.path.join(STORAGE_DIR, "python_packages")
if os.path.isdir(_VENDORED_PACKAGES) and _VENDORED_PACKAGES not in sys.path:
    sys.path.insert(0, _VENDORED_PACKAGES)

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_VAULT_LOCK = threading.RLock()
_MEMORY_KEY = None
_LAST_ACTIVITY = 0.0
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1


class VaultLockedError(RuntimeError):
    pass


def _ensure_storage_permissions():
    os.makedirs(STORAGE_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(STORAGE_DIR, 0o700)
    except OSError:
        pass


def _atomic_write_json(path, value):
    _ensure_storage_permissions()
    directory = os.path.dirname(path)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".stash-vault-",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def _read_vault_file():
    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as source:
            value = json.load(source)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Stash could not read the encrypted Vault.") from error
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("The encrypted Vault format is not recognized.")
    if not isinstance(value.get("entries"), list):
        raise ValueError("The encrypted Vault data is incomplete.")
    return value


def _is_configured():
    return os.path.isfile(VAULT_FILE)


def _load_capture_all_setting():
    try:
        with open(CAPTURE_SETTINGS_FILE, "r", encoding="utf-8") as source:
            value = json.load(source)
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("capture_all_text") is True


def _load_vault_settings():
    try:
        with open(CAPTURE_SETTINGS_FILE, "r", encoding="utf-8") as source:
            settings = json.load(source)
    except (OSError, json.JSONDecodeError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    idle_lock_minutes = settings.get("idle_lock_minutes", 5)
    if type(idle_lock_minutes) is not int or idle_lock_minutes not in {1, 2, 5, 10, 15, 30}:
        idle_lock_minutes = 5
    return {
        "capture_all_text": settings.get("capture_all_text") is True,
        "idle_lock_minutes": idle_lock_minutes,
    }


def set_capture_all_text(enabled):
    if not isinstance(enabled, bool):
        raise ValueError("Choose whether every copied text should go to the Vault.")
    with _VAULT_LOCK:
        if not _is_configured():
            raise VaultLockedError("Create a Vault before changing its capture setting.")
        _require_key()
        settings = _load_vault_settings()
        settings["capture_all_text"] = enabled
        _atomic_write_json(CAPTURE_SETTINGS_FILE, settings)
    return enabled


def set_idle_lock_minutes(minutes):
    if type(minutes) is not int or minutes not in {1, 2, 5, 10, 15, 30}:
        raise ValueError("Choose a supported Vault auto-lock time.")
    with _VAULT_LOCK:
        if not _is_configured():
            raise VaultLockedError("Create a Vault before changing its lock setting.")
        _require_key()
        settings = _load_vault_settings()
        settings["idle_lock_minutes"] = minutes
        _atomic_write_json(CAPTURE_SETTINGS_FILE, settings)
        return minutes


def _derive_key(password, salt):
    return Scrypt(
        salt=salt,
        length=32,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    ).derive(password.encode("utf-8"))


def _b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value):
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _encrypt_payload(key, entry_id, payload):
    nonce = os.urandom(12)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(bytes(key)).encrypt(nonce, plaintext, entry_id.encode("utf-8"))
    return {"id": entry_id, "nonce": _b64(nonce), "ciphertext": _b64(ciphertext)}


def _decrypt_payload(key, entry):
    plaintext = AESGCM(bytes(key)).decrypt(
        _unb64(entry["nonce"]),
        _unb64(entry["ciphertext"]),
        str(entry["id"]).encode("utf-8"),
    )
    value = json.loads(plaintext.decode("utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("content"), str):
        raise ValueError("The encrypted Vault entry is invalid.")
    return value


def _wipe_key():
    global _MEMORY_KEY, _LAST_ACTIVITY
    if isinstance(_MEMORY_KEY, bytearray):
        for index in range(len(_MEMORY_KEY)):
            _MEMORY_KEY[index] = 0
    _MEMORY_KEY = None
    _LAST_ACTIVITY = 0.0


def _expire_idle_key():
    global _LAST_ACTIVITY
    timeout = int(_load_vault_settings()["idle_lock_minutes"]) * 60
    if _MEMORY_KEY is not None and _LAST_ACTIVITY and (datetime.now().timestamp() - _LAST_ACTIVITY) >= timeout:
        _wipe_key()


def _require_key():
    global _LAST_ACTIVITY
    _expire_idle_key()
    if _MEMORY_KEY is None:
        raise VaultLockedError("Unlock the Vault to continue.")
    _LAST_ACTIVITY = datetime.now().timestamp()
    return _MEMORY_KEY


def _make_entry_payload(title, content, source):
    return {
        "title": (str(title or "Secure copy").strip() or "Secure copy")[:120],
        "content": content,
        "source": str(source or "manual")[:40],
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _encrypted_entry(payload):
    entry_id = secrets.token_urlsafe(18)
    return _encrypt_payload(_require_key(), entry_id, payload)


def _write_entries(entries):
    data = _read_vault_file()
    if data is None:
        raise ValueError("The encrypted Vault has not been created.")
    data["entries"] = entries
    _atomic_write_json(VAULT_FILE, data)


def create_vault(password):
    global _MEMORY_KEY, _LAST_ACTIVITY
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Choose a Vault password with at least 12 characters.")
    with _VAULT_LOCK:
        if _is_configured():
            raise ValueError("A Vault already exists. Unlock it with its current password.")
        salt = os.urandom(16)
        key = _derive_key(password, salt)
        verifier_nonce = os.urandom(12)
        verifier = AESGCM(key).encrypt(
            verifier_nonce,
            b"stash-vault-password-check-v1",
            b"stash-vault-verifier-v1",
        )
        data = {
            "version": 1,
            "kdf": {
                "name": "scrypt",
                "salt": _b64(salt),
                "n": _SCRYPT_N,
                "r": _SCRYPT_R,
                "p": _SCRYPT_P,
            },
            "verifier": {"nonce": _b64(verifier_nonce), "ciphertext": _b64(verifier)},
            "entries": [],
        }
        _atomic_write_json(VAULT_FILE, data)
        _MEMORY_KEY = bytearray(key)
        _LAST_ACTIVITY = datetime.now().timestamp()
        try:
            set_capture_all_text(False)
        except Exception:
            _wipe_key()
            raise
        return {"unlocked": True}


def unlock_vault(password):
    global _MEMORY_KEY, _LAST_ACTIVITY
    if not isinstance(password, str) or not password:
        raise ValueError("Enter your Vault password.")
    with _VAULT_LOCK:
        data = _read_vault_file()
        if data is None:
            raise ValueError("Create a Vault password first.")
        kdf = data.get("kdf") or {}
        if kdf.get("name") != "scrypt":
            raise ValueError("This Vault uses an unsupported password format.")
        key = Scrypt(
            salt=_unb64(kdf["salt"]),
            length=32,
            n=int(kdf["n"]),
            r=int(kdf["r"]),
            p=int(kdf["p"]),
        ).derive(password.encode("utf-8"))
        verifier = data.get("verifier") or {}
        try:
            AESGCM(key).decrypt(
                _unb64(verifier["nonce"]),
                _unb64(verifier["ciphertext"]),
                b"stash-vault-verifier-v1",
            )
        except Exception as error:
            raise ValueError("That Vault password is not correct.") from error
        _wipe_key()
        _MEMORY_KEY = bytearray(key)
        _LAST_ACTIVITY = datetime.now().timestamp()
        return {"unlocked": True}


def lock_vault(force=False):
    with _VAULT_LOCK:
        if _MEMORY_KEY is None:
            return True
        _wipe_key()
        return True


def get_vault_status():
    global _LAST_ACTIVITY
    with _VAULT_LOCK:
        _expire_idle_key()
        data = _read_vault_file() if _is_configured() else None
        count = len(data["entries"]) if data else 0
        return {
            "configured": data is not None,
            "unlocked": _MEMORY_KEY is not None,
            "entry_count": count,
            "pending_count": 0,
            "dropped_count": 0,
            "capture_all_text": _load_capture_all_setting(),
            "idle_lock_minutes": _load_vault_settings()["idle_lock_minutes"],
        }


def add_entry(title, content, source="manual"):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Add some text to save in the Vault.")
    with _VAULT_LOCK:
        key = _require_key()
        data = _read_vault_file()
        if data is None:
            raise ValueError("Create a Vault password first.")
        entry = _encrypt_payload(key, secrets.token_urlsafe(18), _make_entry_payload(title, content, source))
        entries = list(data["entries"])
        entries.append(entry)
        data["entries"] = entries
        _atomic_write_json(VAULT_FILE, data)
        return entry["id"]


def list_entries():
    with _VAULT_LOCK:
        key = _require_key()
        data = _read_vault_file()
        if data is None:
            raise ValueError("Create a Vault password first.")
        result = []
        for entry in data["entries"]:
            payload = _decrypt_payload(key, entry)
            result.append({
                "id": entry["id"],
                "title": payload.get("title") or "Secure copy",
                "created_at": payload.get("created_at"),
            })
        return list(reversed(result))


def get_entry(entry_id):
    with _VAULT_LOCK:
        key = _require_key()
        data = _read_vault_file()
        if data is None:
            raise ValueError("Create a Vault password first.")
        for entry in data["entries"]:
            if secrets.compare_digest(str(entry.get("id", "")), str(entry_id)):
                payload = _decrypt_payload(key, entry)
                return {"id": entry["id"], **payload}
        return None


def delete_entry(entry_id):
    with _VAULT_LOCK:
        _require_key()
        data = _read_vault_file()
        if data is None:
            raise ValueError("Create a Vault password first.")
        remaining = [entry for entry in data["entries"] if str(entry.get("id")) != str(entry_id)]
        if len(remaining) == len(data["entries"]):
            return False
        _write_entries(remaining)
        return True


_LABEL_VALUE = re.compile(
    r"(?im)^\s*(?:[\"']?)(?:password|passphrase|passwd|pwd|pin|passcode|one[- ]time\s+(?:password|code)|otp|verification\s+code|recovery\s+code|secret|api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|auth(?:entication)?[-_ ]?token|bearer|client[-_ ]?secret|private\s+key|account\s+number|bank\s+account|routing\s+number|iban|swift|ifsc|card\s+number|credit\s+card|debit\s+card|cvv|cvc|security\s+code|social\s+security\s+number|ssn)(?:[\"']?)\s*(?:[:=]|\bis\b)\s*[^\s,;]+"
)
_SECRET_KEY_VALUE = re.compile(
    r"(?i)[\"']?(?:password|passphrase|passwd|pwd|pin|passcode|otp|secret|api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|auth[-_ ]?token|client[-_ ]?secret|account[-_ ]?number|bank[-_ ]?account|routing[-_ ]?number|iban|swift|ifsc|card[-_ ]?number|cvv|cvc|ssn)[\"']?\s*[:=]\s*[\"']?[^\s,;\"'}]+"
)
_USER_PASSWORD = re.compile(r"(?i)\b[^\s:@]+@[^\s:@]+\.[^\s:@]+\s*:\s*[^\s:@]{3,}")
_EMAIL = re.compile(r"(?i)^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$")
_KNOWN_SECRET_TOKEN = re.compile(
    r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:live|test)-[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")


def _luhn_valid(number):
    digits = [int(character) for character in number]
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def looks_sensitive(text):
    """Best-effort local detector; users can also arm capture-all in Vault."""
    if not isinstance(text, str) or not text.strip():
        return False
    if (
        _LABEL_VALUE.search(text)
        or _SECRET_KEY_VALUE.search(text)
        or _USER_PASSWORD.search(text)
        or _KNOWN_SECRET_TOKEN.search(text)
        or _PRIVATE_KEY.search(text)
    ):
        return True
    if re.search(r"(?im)^\s*(?:password|passphrase|pin|passcode|otp|api[-_ ]?key|account|bank|card)\s*[:=]\s*$", text):
        return True

    for candidate in re.findall(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", text):
        digits = re.sub(r"\D", "", candidate)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            return True

    compact_digits = re.sub(r"[\s()+.-]", "", text.strip())
    if compact_digits.isdigit() and 4 <= len(compact_digits) <= 20:
        # Standalone numeric copies are often PINs, OTPs, phone numbers, or account IDs.
        return True

    if _EMAIL.fullmatch(text.strip()):
        return True

    compact = text.strip()
    if (
        10 <= len(compact) <= 256
        and not re.search(r"\s", compact)
        and not re.match(r"(?i)^(?:https?|ftp)://", compact)
    ):
        alphabet = set(compact)
        classes = sum((
            bool(re.search(r"[a-z]", compact)),
            bool(re.search(r"[A-Z]", compact)),
            bool(re.search(r"\d", compact)),
            bool(re.search(r"[^A-Za-z0-9]", compact)),
        ))
        if len(alphabet) >= 8 and (classes >= 2 or len(compact) >= 18):
            entropy = 0.0
            for character in alphabet:
                probability = compact.count(character) / len(compact)
                entropy -= probability * math.log2(probability)
            if entropy >= (2.8 if classes >= 2 else 3.5):
                return True
    return False


def route_copied_text(content, source="clipboard"):
    """Save secrets only while the Vault is unlocked; otherwise discard them."""
    if not isinstance(content, str):
        return "library"
    with _VAULT_LOCK:
        should_capture = looks_sensitive(content) or _load_capture_all_setting()
        if not should_capture:
            return "library"

        if _MEMORY_KEY is None:
            return "blocked"
        try:
            add_entry("Copied text", content, source)
            return "vault"
        except Exception:
            # Fail closed. Never put sensitive text in Stash's ordinary
            # library or retain it in a plaintext queue after an error.
            return "blocked"
