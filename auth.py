import base64
import hmac
import hashlib
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from datetime import timedelta
from urllib.parse import quote, urlsplit

from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask.sessions import SecureCookieSessionInterface
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from app_paths import BASE_DIR, STORAGE_DIR

LOCAL_PYTHON_PACKAGES = os.path.join(STORAGE_DIR, "python_packages")
if os.path.isdir(LOCAL_PYTHON_PACKAGES):
    sys.path.insert(0, LOCAL_PYTHON_PACKAGES)

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import storage as firebase_storage
except ImportError:
    firebase_admin = None
    firebase_auth = None
    firebase_credentials = None
    firebase_storage = None


AUTH_DIR = STORAGE_DIR
AUTH_DATABASE = os.path.join(AUTH_DIR, "copy_maker_auth.sqlite3")
SESSION_KEY_FILE = os.path.join(AUTH_DIR, ".copy_maker_session_key")
EXTENSION_TOKEN_FILE = os.path.join(AUTH_DIR, ".copy_maker_extension_token")
TOTP_KEY_FILE = os.path.join(AUTH_DIR, ".copy_maker_totp_key")
FIREBASE_CONFIG_FILE = os.path.join(AUTH_DIR, "firebase_auth_config.json")

auth_blueprint = Blueprint("copy_maker_auth", __name__)

_LOGIN_FAILURES = {}
_LOGIN_FAILURE_LOCK = threading.Lock()
_LOGIN_WINDOW_SECONDS = 600
_MAX_LOGIN_FAILURES = 5
_AUTH_RATE_LIMITS = {}
_AUTH_RATE_LIMIT_LOCK = threading.Lock()
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(32), method="scrypt")
_EXTENSION_REQUEST_TOKEN = ""
_LOCAL_PAIRING_CODE_HASH = ""
_LOCAL_PAIRING_CODE_EXPIRES = 0
_LOCAL_PAIRING_LOCK = threading.Lock()
_TOTP_KEY = b""
_TOTP_SETUP_PENDING = {}
_TOTP_SETUP_LOCK = threading.Lock()
_SESSION_TOUCH = {}
_SESSION_IDLE_SECONDS = 12 * 60 * 60
_SESSION_ABSOLUTE_SECONDS = 14 * 24 * 60 * 60
_RECOVERY_CODE_COUNT = 10
_LOCAL_EXTENSION_PATHS = {
    "/api/browser-copy",
    "/api/browser-copy/import-audio-download",
    "/api/video-capture-start",
}
_LOCAL_HOSTS = {
    "127.0.0.1:5050",
    "localhost:5050",
    "[::1]:5050",
}
_FIREBASE_APP = None
_FIREBASE_WEB_CONFIG = None
_FIREBASE_AUTH_READY = False
_FIREBASE_ENABLED_PROVIDERS = ["google"]
_FIREBASE_STORAGE_BUCKET = ""
_CLOUD_STORAGE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
_CLOUD_STORAGE_LOCK = threading.Lock()


class ProxyAwareSessionInterface(SecureCookieSessionInterface):
    def get_cookie_secure(self, app):
        if super().get_cookie_secure(app):
            return True
        return is_trusted_secure_proxy_request()


def _connect():
    connection = sqlite3.connect(AUTH_DATABASE, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _load_or_create_session_key():
    configured_key = os.environ.get("COPY_MAKER_SECRET_KEY")
    if configured_key:
        return configured_key

    try:
        descriptor = os.open(
            SESSION_KEY_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        with open(SESSION_KEY_FILE, "rb") as key_file:
            return key_file.read()

    key = secrets.token_bytes(48)
    with os.fdopen(descriptor, "wb") as key_file:
        key_file.write(key)
    return key


def _load_or_create_extension_token():
    try:
        with open(EXTENSION_TOKEN_FILE, "r", encoding="utf-8") as token_file:
            token = token_file.read().strip()
        if len(token) >= 40:
            os.chmod(EXTENSION_TOKEN_FILE, 0o600)
            return token
    except OSError:
        pass

    token = secrets.token_urlsafe(48)
    descriptor = os.open(
        EXTENSION_TOKEN_FILE,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
        token_file.write(token)
    return token


def _load_or_create_totp_key():
    try:
        with open(TOTP_KEY_FILE, "rb") as key_file:
            key = key_file.read()
    except OSError:
        key = secrets.token_bytes(32)
        try:
            descriptor = os.open(TOTP_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            with open(TOTP_KEY_FILE, "rb") as key_file:
                key = key_file.read()
        else:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(key)
                key_file.flush()
                os.fsync(key_file.fileno())
    if len(key) != 32:
        raise RuntimeError("The local two-step verification key is damaged. Restore Stash from an encrypted backup.")
    os.chmod(TOTP_KEY_FILE, 0o600)
    return key


def _rate_limit(bucket, limit, window_seconds):
    """Return retry-after seconds when a source has exhausted a short auth limit."""
    now = time.time()
    key = (str(bucket), _failure_key(""))
    with _AUTH_RATE_LIMIT_LOCK:
        attempts = [
            started for started in _AUTH_RATE_LIMITS.get(key, [])
            if now - started < window_seconds
        ]
        if len(attempts) >= limit:
            _AUTH_RATE_LIMITS[key] = attempts
            return max(1, int(window_seconds - (now - attempts[0])))
        attempts.append(now)
        _AUTH_RATE_LIMITS[key] = attempts
        if len(_AUTH_RATE_LIMITS) > 4096:
            for old_key, old_attempts in list(_AUTH_RATE_LIMITS.items()):
                kept = [started for started in old_attempts if now - started < window_seconds]
                if kept:
                    _AUTH_RATE_LIMITS[old_key] = kept
                else:
                    _AUTH_RATE_LIMITS.pop(old_key, None)
    return 0


def _limited_response(retry_after):
    response = jsonify({"error": "Too many attempts. Wait a few minutes, then try again."})
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


def rate_limit_auth_attempt(bucket, limit, window_seconds):
    return _rate_limit(bucket, limit, window_seconds)


def _session_key_hash(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _device_label():
    user_agent = request.user_agent
    browser = user_agent.browser or "Browser"
    platform = user_agent.platform or "device"
    return f"{browser.title()} on {platform.title()}"[:120]


def _totp_encrypt_key():
    if len(_TOTP_KEY) != 32:
        raise RuntimeError("Stash could not load its local two-step verification key.")
    return _TOTP_KEY


def _encrypt_totp_secret(secret):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(_totp_encrypt_key()).encrypt(nonce, secret.encode("ascii"), b"stash-totp-v1")


def _decrypt_totp_secret(ciphertext):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = bytes(ciphertext or b"")
    if len(raw) < 29:
        raise ValueError("The saved two-step verification secret is invalid.")
    plaintext = AESGCM(_totp_encrypt_key()).decrypt(raw[:12], raw[12:], b"stash-totp-v1")
    return plaintext.decode("ascii")


def _new_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_code(secret, timestamp=None):
    timestamp = time.time() if timestamp is None else float(timestamp)
    padded_secret = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    counter = int(timestamp // 30)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _matching_totp_counter(secret, candidate):
    code = str(candidate or "").strip().replace(" ", "")
    if not re.fullmatch(r"\d{6}", code):
        return None
    current_counter = int(time.time() // 30)
    matches = [
        counter
        for counter in range(max(0, current_counter - 1), current_counter + 2)
        if hmac.compare_digest(_totp_code(secret, counter * 30), code)
    ]
    return max(matches) if matches else None


def _consume_account_totp_code(account_id, candidate):
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT totp_secret_enc, totp_last_counter FROM owner_account WHERE id = ?",
            (account_id,),
        ).fetchone()
        if not row or not row["totp_secret_enc"]:
            connection.rollback()
            return False
        secret = _decrypt_totp_secret(row["totp_secret_enc"])
        counter = _matching_totp_counter(secret, candidate)
        if counter is None or counter <= int(row["totp_last_counter"] or -1):
            connection.rollback()
            return False
        connection.execute(
            "UPDATE owner_account SET totp_last_counter = ? WHERE id = ?",
            (counter, account_id),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def _account_totp_secret(account_id=1):
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT totp_secret_enc FROM owner_account WHERE id = ?", (account_id,)
        ).fetchone()
    finally:
        connection.close()
    if not row or not row["totp_secret_enc"]:
        return None
    return _decrypt_totp_secret(row["totp_secret_enc"])


def _begin_two_factor_challenge(account):
    session.clear()
    session["copy_maker_pending_2fa_user_id"] = account["id"]
    session["copy_maker_pending_2fa_username"] = account["username"]
    session["copy_maker_pending_2fa_expires"] = int(time.time()) + 300


def _finish_login(account):
    if _account_totp_secret(account["id"]):
        _begin_two_factor_challenge(account)
        return True
    _set_login_session(account)
    return False


def _verify_recovery_code(account_id, candidate):
    value = str(candidate or "").strip().replace("-", "").replace(" ", "").upper()
    if not re.fullmatch(r"[A-F0-9]{20}", value):
        return False
    candidate_hash = hashlib.sha256(value.encode("ascii")).hexdigest()
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT recovery_code_hashes FROM owner_account WHERE id = ?", (account_id,)
        ).fetchone()
        try:
            hashes = json.loads(row["recovery_code_hashes"] or "[]") if row else []
        except (TypeError, ValueError, json.JSONDecodeError):
            hashes = []
        match = next((index for index, item in enumerate(hashes) if hmac.compare_digest(item, candidate_hash)), None)
        if match is None:
            connection.rollback()
            return False
        hashes.pop(match)
        connection.execute(
            "UPDATE owner_account SET recovery_code_hashes = ? WHERE id = ?",
            (json.dumps(hashes), account_id),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def _record_extension_device(token):
    token_hash = _session_key_hash(token)
    now = int(time.time())
    connection = _connect()
    try:
        connection.execute(
            """INSERT INTO owner_sessions (session_id_hash, session_type, device_label, created_at, last_seen_at, expires_at)
               VALUES (?, 'extension', 'Copy with Stash extension', ?, ?, NULL)
               ON CONFLICT(session_id_hash) DO UPDATE SET last_seen_at = excluded.last_seen_at""",
            (token_hash, now, now),
        )
        connection.commit()
    finally:
        connection.close()


def _touch_extension_device(token):
    token_hash = _session_key_hash(token)
    now = int(time.time())
    connection = _connect()
    try:
        cursor = connection.execute(
            "UPDATE owner_sessions SET last_seen_at = ? WHERE session_id_hash = ? AND session_type = 'extension'",
            (now, token_hash),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def _save_extension_token(token):
    temporary_path = EXTENSION_TOKEN_FILE + ".tmp"
    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
        token_file.write(token)
        token_file.flush()
        os.fsync(token_file.fileno())
    os.replace(temporary_path, EXTENSION_TOKEN_FILE)
    os.chmod(EXTENSION_TOKEN_FILE, 0o600)


def _rotate_local_extension_token():
    global _EXTENSION_REQUEST_TOKEN, _LOCAL_PAIRING_CODE_HASH, _LOCAL_PAIRING_CODE_EXPIRES

    new_token = secrets.token_urlsafe(48)
    with _LOCAL_PAIRING_LOCK:
        _EXTENSION_REQUEST_TOKEN = ""
        _LOCAL_PAIRING_CODE_HASH = ""
        _LOCAL_PAIRING_CODE_EXPIRES = 0
    try:
        _save_extension_token(new_token)
    except OSError:
        try:
            os.remove(EXTENSION_TOKEN_FILE)
        except OSError:
            pass
        return None
    with _LOCAL_PAIRING_LOCK:
        _EXTENSION_REQUEST_TOKEN = new_token
    return new_token


def _initialize_firebase_auth(app):
    global _FIREBASE_APP, _FIREBASE_WEB_CONFIG, _FIREBASE_AUTH_READY, _FIREBASE_ENABLED_PROVIDERS, _FIREBASE_STORAGE_BUCKET

    file_config = {}
    if os.path.isfile(FIREBASE_CONFIG_FILE):
        try:
            with open(FIREBASE_CONFIG_FILE, "r", encoding="utf-8") as config_file:
                file_config = json.load(config_file)
            if not isinstance(file_config, dict):
                raise ValueError("Firebase config must be a JSON object")
            os.chmod(FIREBASE_CONFIG_FILE, 0o600)
        except (OSError, ValueError, json.JSONDecodeError):
            app.logger.exception("Could not read the Firebase sign-in configuration")
            file_config = {}

    project_id = os.environ.get("COPY_MAKER_FIREBASE_PROJECT_ID", file_config.get("project_id", "")).strip()
    api_key = os.environ.get("COPY_MAKER_FIREBASE_API_KEY", file_config.get("api_key", "")).strip()
    app_id = os.environ.get("COPY_MAKER_FIREBASE_APP_ID", file_config.get("app_id", "")).strip()
    auth_domain = os.environ.get("COPY_MAKER_FIREBASE_AUTH_DOMAIN", file_config.get("auth_domain", "")).strip()
    sender_id = os.environ.get("COPY_MAKER_FIREBASE_MESSAGING_SENDER_ID", file_config.get("messaging_sender_id", "")).strip()
    _FIREBASE_STORAGE_BUCKET = os.environ.get(
        "COPY_MAKER_FIREBASE_STORAGE_BUCKET",
        file_config.get("storage_bucket", ""),
    ).strip()
    if not _FIREBASE_STORAGE_BUCKET and project_id:
        _FIREBASE_STORAGE_BUCKET = f"{project_id}.firebasestorage.app"
    service_account_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        file_config.get("service_account_path", ""),
    ).strip()
    if service_account_path and not os.path.isabs(service_account_path):
        service_account_path = os.path.join(AUTH_DIR, service_account_path)

    enabled_providers = file_config.get("enabled_providers", ["google"])
    allowed_providers = {"google", "apple", "phone"}
    if isinstance(enabled_providers, list):
        _FIREBASE_ENABLED_PROVIDERS = [
            provider for provider in enabled_providers
            if isinstance(provider, str) and provider in allowed_providers
        ]
    else:
        _FIREBASE_ENABLED_PROVIDERS = ["google"]

    if all((project_id, api_key, app_id, auth_domain, sender_id)):
        _FIREBASE_WEB_CONFIG = {
            "apiKey": api_key,
            "authDomain": auth_domain,
            "projectId": project_id,
            "appId": app_id,
            "messagingSenderId": sender_id,
        }

    if not (firebase_admin and firebase_auth and firebase_credentials):
        app.logger.info("Firebase sign-in is not configured (firebase-admin is unavailable)")
        return
    if not (project_id and _FIREBASE_WEB_CONFIG and service_account_path and os.path.isfile(service_account_path)):
        app.logger.info("Firebase sign-in is not configured")
        return

    try:
        os.chmod(service_account_path, 0o600)
        try:
            _FIREBASE_APP = firebase_admin.get_app("copy-maker")
        except ValueError:
            certificate = firebase_credentials.Certificate(service_account_path)
            _FIREBASE_APP = firebase_admin.initialize_app(
                certificate,
                {"projectId": project_id},
                name="copy-maker",
            )
        if _FIREBASE_APP.project_id != project_id:
            raise ValueError("Firebase service account project does not match the web configuration")
        _FIREBASE_AUTH_READY = True
    except Exception:
        _FIREBASE_APP = None
        _FIREBASE_AUTH_READY = False
        _FIREBASE_WEB_CONFIG = None
        app.logger.exception("Firebase sign-in could not be initialized")


def initialize_auth(app):
    global _EXTENSION_REQUEST_TOKEN, _TOTP_KEY

    os.makedirs(AUTH_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(AUTH_DIR, 0o700)
    except OSError:
        app.logger.warning("Could not restrict the local Stash data folder")
    app.secret_key = _load_or_create_session_key()
    app.config.update(
        SESSION_COOKIE_NAME="copy_maker_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get(
            "COPY_MAKER_COOKIE_SECURE", "0"
        ).lower() in {"1", "true", "yes"},
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    )
    app.session_interface = ProxyAwareSessionInterface()

    connection = _connect()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(owner_account)").fetchall()
        }
        if "firebase_uid" not in columns:
            connection.execute(
                "ALTER TABLE owner_account ADD COLUMN firebase_uid TEXT"
            )
        if "totp_secret_enc" not in columns:
            connection.execute("ALTER TABLE owner_account ADD COLUMN totp_secret_enc BLOB")
        if "recovery_code_hashes" not in columns:
            connection.execute("ALTER TABLE owner_account ADD COLUMN recovery_code_hashes TEXT NOT NULL DEFAULT '[]'")
        if "totp_last_counter" not in columns:
            connection.execute("ALTER TABLE owner_account ADD COLUMN totp_last_counter INTEGER NOT NULL DEFAULT -1")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_account_firebase_uid ON owner_account(firebase_uid)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS owner_sessions (
                session_id_hash TEXT PRIMARY KEY,
                session_type TEXT NOT NULL DEFAULT 'browser',
                device_label TEXT NOT NULL DEFAULT 'Browser',
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                expires_at INTEGER,
                revoked_at INTEGER
            )"""
        )
        connection.commit()
    finally:
        connection.close()

    try:
        os.chmod(AUTH_DATABASE, 0o600)
        if os.path.exists(SESSION_KEY_FILE):
            os.chmod(SESSION_KEY_FILE, 0o600)
        _TOTP_KEY = _load_or_create_totp_key()
        _EXTENSION_REQUEST_TOKEN = _load_or_create_extension_token()
    except OSError:
        app.logger.exception("Could not secure local authentication files")

    _initialize_firebase_auth(app)


def account_exists():
    connection = _connect()
    try:
        return connection.execute(
            "SELECT 1 FROM owner_account WHERE id = 1"
        ).fetchone() is not None
    finally:
        connection.close()


def has_authenticated_session():
    if session.get("copy_maker_user_id") != 1:
        return False
    session_id = session.get("copy_maker_session_id")
    if not isinstance(session_id, str) or len(session_id) < 32:
        return False
    now = int(time.time())
    key = _session_key_hash(session_id)
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT last_seen_at, expires_at, revoked_at FROM owner_sessions WHERE session_id_hash = ? AND session_type = 'browser'",
            (key,),
        ).fetchone()
        if not row or row["revoked_at"] is not None or int(row["expires_at"] or 0) <= now:
            return False
        if now - int(row["last_seen_at"] or 0) > _SESSION_IDLE_SECONDS:
            connection.execute("DELETE FROM owner_sessions WHERE session_id_hash = ?", (key,))
            connection.commit()
            return False
        last_touch = _SESSION_TOUCH.get(key, 0)
        if now - last_touch >= 60:
            connection.execute(
                "UPDATE owner_sessions SET last_seen_at = ? WHERE session_id_hash = ?",
                (now, key),
            )
            connection.commit()
            _SESSION_TOUCH[key] = now
        return True
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def is_local_host(host=None):
    return (host or request.host).lower() in _LOCAL_HOSTS


def _trusted_proxy_networks():
    values = os.environ.get("COPY_MAKER_TRUSTED_PROXY_IPS", "")
    networks = []
    for value in values.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def trusted_proxy_configured():
    return bool(_trusted_proxy_networks())


def is_trusted_proxy_request():
    try:
        peer = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return any(peer in network for network in _trusted_proxy_networks())


def is_trusted_secure_proxy_request():
    if not is_trusted_proxy_request():
        return False
    forwarded_scheme = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
    if forwarded_scheme == "https":
        return True
    try:
        cloudflare_visitor = json.loads(request.headers.get("CF-Visitor", "{}"))
    except (TypeError, ValueError):
        cloudflare_visitor = {}
    return isinstance(cloudflare_visitor, dict) and cloudflare_visitor.get("scheme") == "https"


def is_local_extension_request():
    eligible = (
        request.method == "POST"
        and
        request.path in _LOCAL_EXTENSION_PATHS
        and is_local_host()
        and request.remote_addr in {"127.0.0.1", "::1"}
        and bool(_EXTENSION_REQUEST_TOKEN)
        and hmac.compare_digest(
            request.headers.get("X-Copy-Maker-Extension-Token", ""),
            _EXTENSION_REQUEST_TOKEN,
        )
    )
    if not eligible:
        return False
    return _touch_extension_device(request.headers.get("X-Copy-Maker-Extension-Token", ""))


def is_local_extension_pair_request():
    return (
        request.path == "/api/auth/local-extension-pair"
        and request.method == "POST"
        and is_local_host()
        and request.remote_addr in {"127.0.0.1", "::1"}
    )


def request_is_same_origin():
    origin = request.headers.get("Origin")
    if not origin:
        return False

    parsed_origin = urlsplit(origin)
    if is_trusted_proxy_request():
        forwarded_scheme = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
        forwarded_host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()
    else:
        forwarded_scheme = ""
        forwarded_host = ""
    expected_scheme = forwarded_scheme or request.scheme
    expected_host = forwarded_host or request.host

    return (
        parsed_origin.scheme.lower() == expected_scheme.lower()
        and parsed_origin.netloc.lower() == expected_host.lower()
    )


def _json_payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _username_from(payload):
    return str(payload.get("username", "")).strip().lower()


def _set_login_session(account):
    now = int(time.time())
    raw_session_id = secrets.token_urlsafe(40)
    session_id_hash = _session_key_hash(raw_session_id)
    connection = _connect()
    try:
        connection.execute(
            "INSERT INTO owner_sessions (session_id_hash, session_type, device_label, created_at, last_seen_at, expires_at) VALUES (?, 'browser', ?, ?, ?, ?)",
            (session_id_hash, _device_label(), now, now, now + _SESSION_ABSOLUTE_SECONDS),
        )
        connection.commit()
    finally:
        connection.close()
    session.clear()
    session.permanent = True
    session["copy_maker_user_id"] = account["id"]
    session["copy_maker_username"] = account["username"]
    session["copy_maker_session_id"] = raw_session_id
    session["copy_maker_session_issued"] = now


def _failure_key(username):
    remote_address = request.remote_addr or "unknown"
    if is_trusted_proxy_request():
        forwarded_address = (
            request.headers.get("CF-Connecting-IP", "").strip()
            or request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        )
        try:
            remote_address = str(ipaddress.ip_address(forwarded_address))
        except ValueError:
            pass
    return remote_address


def _recent_failures(key, now):
    recent = [
        attempt
        for attempt in _LOGIN_FAILURES.get(key, [])
        if now - attempt < _LOGIN_WINDOW_SECONDS
    ]
    _LOGIN_FAILURES[key] = recent
    return recent


@auth_blueprint.get("/api/auth/status")
def auth_status():
    configured = account_exists()
    authenticated = configured and has_authenticated_session()
    pending_two_factor = (
        isinstance(session.get("copy_maker_pending_2fa_user_id"), int)
        and session.get("copy_maker_pending_2fa_expires", 0) > int(time.time())
    )
    connection = _connect()
    try:
        account = connection.execute(
            "SELECT totp_secret_enc FROM owner_account WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()
    response = jsonify({
        "configured": configured,
        "authenticated": authenticated,
        "username": session.get("copy_maker_username") if authenticated else None,
        "two_factor_enabled": bool(account and account["totp_secret_enc"]),
        "two_factor_challenge_pending": pending_two_factor,
        "can_create_account": not configured and is_local_host(),
        "firebase_configured": _FIREBASE_AUTH_READY and bool(_FIREBASE_WEB_CONFIG),
        "firebase_config": _FIREBASE_WEB_CONFIG if _FIREBASE_AUTH_READY else None,
        "firebase_enabled_providers": _FIREBASE_ENABLED_PROVIDERS,
        "firebase_storage_configured": bool(
            _FIREBASE_AUTH_READY and _FIREBASE_STORAGE_BUCKET and firebase_storage
        ),
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_blueprint.post("/api/auth/local-extension-code")
def auth_local_extension_code():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not is_local_host():
        return jsonify({"error": "Open Stash on this Mac to connect a local browser."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401
    retry_after = _rate_limit("extension-code", 5, 600)
    if retry_after:
        return _limited_response(retry_after)

    pairing_code = secrets.token_urlsafe(16)
    try:
        connection = _connect()
        try:
            connection.execute("DELETE FROM owner_sessions WHERE session_type = 'extension'")
            connection.commit()
        finally:
            connection.close()
    except Exception:
        current_app.logger.exception("Could not disconnect the previous Stash extension")
        return jsonify({"error": "Stash could not safely replace the browser connection."}), 500
    if not _rotate_local_extension_token():
        return jsonify({"error": "Stash could not create a secure browser connection."}), 500
    with _LOCAL_PAIRING_LOCK:
        _LOCAL_PAIRING_CODE_HASH = hashlib.sha256(pairing_code.encode("utf-8")).hexdigest()
        _LOCAL_PAIRING_CODE_EXPIRES = int(time.time()) + 600

    return jsonify({"code": pairing_code, "expiresInSeconds": 600})


@auth_blueprint.post("/api/auth/local-extension-pair")
def auth_local_extension_pair():
    global _LOCAL_PAIRING_CODE_HASH, _LOCAL_PAIRING_CODE_EXPIRES

    if not is_local_host() or request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify({"error": "Local browser pairing is available only on this Mac."}), 403
    retry_after = _rate_limit("extension-pair", 10, 600)
    if retry_after:
        return _limited_response(retry_after)
    payload = _json_payload()
    code = payload.get("code")
    if not isinstance(code, str) or len(code) > 128:
        return jsonify({"error": "Enter the one-time code from Stash."}), 400

    candidate_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    with _LOCAL_PAIRING_LOCK:
        valid = (
            bool(_LOCAL_PAIRING_CODE_HASH)
            and int(time.time()) <= _LOCAL_PAIRING_CODE_EXPIRES
            and hmac.compare_digest(candidate_hash, _LOCAL_PAIRING_CODE_HASH)
        )
        if not valid:
            return jsonify({"error": "That code expired or was already used. Create a new code in Stash."}), 401
        _LOCAL_PAIRING_CODE_HASH = ""
        _LOCAL_PAIRING_CODE_EXPIRES = 0
        token = _EXTENSION_REQUEST_TOKEN
    _record_extension_device(token)

    return jsonify({"success": True, "accessToken": token}), 201


def _verify_firebase_payload(payload):
    if not _FIREBASE_AUTH_READY or not firebase_auth:
        return None, (jsonify({"error": "Firebase email and phone sign-in are not configured yet."}), 503)
    id_token = payload.get("id_token")
    if not isinstance(id_token, str) or not id_token or len(id_token) > 12000:
        return None, (jsonify({"error": "The sign-in response was invalid. Please try again."}), 400)
    try:
        claims = firebase_auth.verify_id_token(
            id_token,
            app=_FIREBASE_APP,
            check_revoked=True,
        )
    except Exception:
        return None, (jsonify({"error": "Sign-in could not be verified. Please try again."}), 401)
    if not isinstance(claims.get("uid"), str) or not claims["uid"]:
        return None, (jsonify({"error": "Sign-in could not be verified. Please try again."}), 401)
    return claims, None


def get_firebase_public_config():
    """Return only the Firebase web configuration needed by browser clients."""
    if not _FIREBASE_AUTH_READY or not _FIREBASE_WEB_CONFIG:
        return None
    return dict(_FIREBASE_WEB_CONFIG)


def verify_firebase_id_token(payload):
    """Verify a browser Firebase ID token before creating an app session."""
    return _verify_firebase_payload(payload)


def _firebase_owner_username(uid):
    safe_uid = re.sub(r"[^a-z0-9_-]", "", uid.lower())[:16]
    return f"owner-{safe_uid or secrets.token_hex(4)}"


@auth_blueprint.post("/api/auth/firebase-login")
def auth_firebase_login():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    retry_after = _rate_limit("firebase-login", 5, 600)
    if retry_after:
        return _limited_response(retry_after)
    claims, error = _verify_firebase_payload(_json_payload())
    if error:
        return error

    connection = _connect()
    try:
        account = connection.execute(
            "SELECT id, username, firebase_uid FROM owner_account WHERE id = 1"
        ).fetchone()
        if account is None:
            if not is_local_host():
                return jsonify({"error": "Create the first Stash account on this Mac."}), 403
            username = _firebase_owner_username(claims["uid"])
            generated_password = generate_password_hash(secrets.token_urlsafe(48), method="scrypt")
            connection.execute("BEGIN IMMEDIATE")
            # Recheck after taking the write lock so parallel first sign-ins cannot race.
            account = connection.execute(
                "SELECT id, username, firebase_uid FROM owner_account WHERE id = 1"
            ).fetchone()
            if account is None:
                connection.execute(
                    "INSERT INTO owner_account (id, username, password_hash, firebase_uid) VALUES (1, ?, ?, ?)",
                    (username, generated_password, claims["uid"]),
                )
                connection.commit()
                account = {"id": 1, "username": username, "firebase_uid": claims["uid"]}
            else:
                connection.rollback()

        if account["firebase_uid"] != claims["uid"]:
            return jsonify({
                "error": "This sign-in option is not connected to the Stash account yet. Sign in with your password, then choose Connect sign-in option."
            }), 409
        requires_two_factor = _finish_login(account)
        return jsonify({
            "success": True,
            "username": account["username"],
            "requires_two_factor": requires_two_factor,
        })
    except sqlite3.IntegrityError:
        connection.rollback()
        return jsonify({"error": "The account could not be created. Please try again."}), 409
    finally:
        connection.close()


@auth_blueprint.post("/api/auth/link-firebase")
def auth_link_firebase():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in with your current account first."}), 401
    claims, error = _verify_firebase_payload(_json_payload())
    if error:
        return error

    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        account = connection.execute(
            "SELECT id, username, firebase_uid FROM owner_account WHERE id = 1"
        ).fetchone()
        if not account:
            connection.rollback()
            return jsonify({"error": "The Stash account could not be found."}), 404
        if account["firebase_uid"] not in (None, claims["uid"]):
            connection.rollback()
            return jsonify({"error": "A different Google, Apple, or phone account is already connected."}), 409
        connection.execute(
            "UPDATE owner_account SET firebase_uid = ? WHERE id = 1",
            (claims["uid"],),
        )
        connection.commit()
        return jsonify({"success": True, "username": account["username"]})
    finally:
        connection.close()


@auth_blueprint.post("/api/auth/signup")
def auth_signup():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not is_local_host():
        return jsonify({"error": "Create the first account from this Mac."}), 403
    if account_exists():
        return jsonify({"error": "An account already exists. Please sign in."}), 409
    retry_after = _rate_limit("signup", 5, 600)
    if retry_after:
        return _limited_response(retry_after)

    payload = _json_payload()
    username = _username_from(payload)
    password = payload.get("password")

    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", username):
        return jsonify({
            "error": "Use 3–32 letters, numbers, dots, dashes, or underscores for your username."
        }), 400
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        return jsonify({"error": "Choose a password between 12 and 1024 characters."}), 400

    password_hash = generate_password_hash(password, method="scrypt")
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT id FROM owner_account WHERE id = 1"
        ).fetchone()
        if existing:
            connection.rollback()
            return jsonify({"error": "An account already exists. Please sign in."}), 409
        connection.execute(
            "INSERT INTO owner_account (id, username, password_hash) VALUES (1, ?, ?)",
            (username, password_hash),
        )
        connection.commit()
        account = {"id": 1, "username": username}
    except sqlite3.IntegrityError:
        connection.rollback()
        return jsonify({"error": "That username is already in use."}), 409
    finally:
        connection.close()

    _set_login_session(account)
    return jsonify({"success": True, "username": username}), 201


@auth_blueprint.post("/api/auth/login")
def auth_login():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403

    payload = _json_payload()
    username = _username_from(payload)
    if len(username) > 32 or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", username):
        username = ""
    password = payload.get("password")
    key = _failure_key(username)
    now = time.time()
    with _LOGIN_FAILURE_LOCK:
        failures = _recent_failures(key, now)
        if len(failures) >= _MAX_LOGIN_FAILURES:
            retry_after = max(1, int(_LOGIN_WINDOW_SECONDS - (now - failures[0])))
            response = jsonify({"error": "Too many attempts. Please wait a few minutes and try again."})
            response.headers["Retry-After"] = str(retry_after)
            return response, 429
        failures.append(now)
        if len(_LOGIN_FAILURES) > 4096:
            for failure_key in list(_LOGIN_FAILURES):
                _recent_failures(failure_key, now)
                if not _LOGIN_FAILURES[failure_key]:
                    _LOGIN_FAILURES.pop(failure_key, None)

    account = None
    connection = _connect()
    try:
        account = connection.execute(
            "SELECT id, username, password_hash FROM owner_account WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        connection.close()

    if not account_exists():
        return jsonify({"error": "Create your account on this Mac first."}), 409

    if isinstance(password, str) and len(password) <= 1024:
        stored_hash = account["password_hash"] if account else _DUMMY_PASSWORD_HASH
        matches_hash = check_password_hash(stored_hash, password)
    else:
        matches_hash = False
    password_ok = account is not None and matches_hash
    if not password_ok:
        return jsonify({"error": "Username or password is incorrect."}), 401

    with _LOGIN_FAILURE_LOCK:
        _LOGIN_FAILURES.pop(key, None)
    requires_two_factor = _finish_login(account)
    return jsonify({
        "success": True,
        "username": account["username"],
        "requires_two_factor": requires_two_factor,
    })


@auth_blueprint.post("/api/auth/two-factor/verify")
def auth_two_factor_verify():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    retry_after = _rate_limit("two-factor-verify", 5, 600)
    if retry_after:
        return _limited_response(retry_after)
    account_id = session.get("copy_maker_pending_2fa_user_id")
    expires = session.get("copy_maker_pending_2fa_expires", 0)
    if account_id != 1 or not isinstance(expires, int) or expires < int(time.time()):
        session.clear()
        return jsonify({"error": "That sign-in check expired. Start signing in again."}), 401
    payload = _json_payload()
    code = payload.get("code")
    try:
        valid = _consume_account_totp_code(account_id, code)
        if not valid:
            valid = _verify_recovery_code(account_id, code)
    except Exception as error:
        current_app.logger.warning("Two-step verification failed to load: %s", type(error).__name__)
        return jsonify({"error": "Stash could not check the verification code."}), 500
    if not valid:
        return jsonify({"error": "That verification code is incorrect or already used."}), 401
    connection = _connect()
    try:
        account = connection.execute(
            "SELECT id, username FROM owner_account WHERE id = ?", (account_id,)
        ).fetchone()
    finally:
        connection.close()
    if not account:
        session.clear()
        return jsonify({"error": "The Stash account could not be found."}), 404
    _set_login_session(account)
    return jsonify({"success": True, "username": account["username"]})


@auth_blueprint.post("/api/auth/two-factor/cancel")
def auth_two_factor_cancel():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    session.clear()
    return jsonify({"success": True})


@auth_blueprint.post("/api/auth/two-factor/setup")
def auth_two_factor_setup():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in again to set up two-step verification."}), 401
    if _account_totp_secret():
        return jsonify({"error": "Two-step verification is already on. Enter a current code to turn it off before setting up a new authenticator."}), 409
    secret = _new_totp_secret()
    key = _session_key_hash(session.get("copy_maker_session_id"))
    with _TOTP_SETUP_LOCK:
        _TOTP_SETUP_PENDING[key] = {"secret": secret, "expires": int(time.time()) + 600}
    connection = _connect()
    try:
        account = connection.execute("SELECT username FROM owner_account WHERE id = 1").fetchone()
    finally:
        connection.close()
    username = account["username"] if account else "Stash"
    issuer = "Stash"
    label = f"{issuer}:{username}"
    otpauth_url = (
        f"otpauth://totp/{quote(label)}"
        f"?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )
    response = jsonify({"success": True, "secret": secret, "otpauth_url": otpauth_url})
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_blueprint.post("/api/auth/two-factor/enable")
def auth_two_factor_enable():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in again to set up two-step verification."}), 401
    retry_after = _rate_limit("two-factor-enable", 5, 600)
    if retry_after:
        return _limited_response(retry_after)
    key = _session_key_hash(session.get("copy_maker_session_id"))
    with _TOTP_SETUP_LOCK:
        pending = _TOTP_SETUP_PENDING.get(key)
        if pending and pending["expires"] < int(time.time()):
            _TOTP_SETUP_PENDING.pop(key, None)
            pending = None
    code = _json_payload().get("code")
    counter = _matching_totp_counter(pending["secret"], code) if pending else None
    if counter is None:
        return jsonify({"error": "Enter the current six-digit code from your authenticator app."}), 400
    recovery_codes = [secrets.token_hex(10).upper() for _ in range(_RECOVERY_CODE_COUNT)]
    recovery_hashes = [hashlib.sha256(code.encode("ascii")).hexdigest() for code in recovery_codes]
    encrypted_secret = _encrypt_totp_secret(pending["secret"])
    connection = _connect()
    try:
        connection.execute(
            "UPDATE owner_account SET totp_secret_enc = ?, recovery_code_hashes = ?, totp_last_counter = ? WHERE id = 1",
            (encrypted_secret, json.dumps(recovery_hashes), counter),
        )
        connection.commit()
    finally:
        connection.close()
    with _TOTP_SETUP_LOCK:
        _TOTP_SETUP_PENDING.pop(key, None)
    response = jsonify({"success": True, "recovery_codes": recovery_codes})
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_blueprint.post("/api/auth/two-factor/disable")
def auth_two_factor_disable():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in again to change two-step verification."}), 401
    retry_after = _rate_limit("two-factor-disable", 5, 600)
    if retry_after:
        return _limited_response(retry_after)
    code = _json_payload().get("code")
    try:
        valid = _consume_account_totp_code(1, code)
    except Exception:
        valid = False
    if not valid:
        valid = _verify_recovery_code(1, code)
    if not valid:
        return jsonify({"error": "Enter a current authenticator or unused recovery code to turn off two-step verification."}), 401
    connection = _connect()
    try:
        connection.execute(
            "UPDATE owner_account SET totp_secret_enc = NULL, recovery_code_hashes = '[]' WHERE id = 1"
        )
        connection.commit()
    finally:
        connection.close()
    return jsonify({"success": True})


@auth_blueprint.get("/api/auth/sessions")
def auth_sessions():
    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401
    now = int(time.time())
    current_hash = _session_key_hash(session.get("copy_maker_session_id"))
    connection = _connect()
    try:
        connection.execute(
            "DELETE FROM owner_sessions WHERE (expires_at IS NOT NULL AND expires_at <= ?) OR revoked_at IS NOT NULL",
            (now,),
        )
        rows = connection.execute(
            "SELECT session_id_hash, session_type, device_label, created_at, last_seen_at FROM owner_sessions ORDER BY last_seen_at DESC"
        ).fetchall()
        connection.commit()
    finally:
        connection.close()
    response = jsonify({
        "sessions": [
            {
                "id": row["session_id_hash"],
                "type": row["session_type"],
                "device": row["device_label"],
                "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"],
                "current": row["session_id_hash"] == current_hash,
            }
            for row in rows
        ],
        "idle_timeout_seconds": _SESSION_IDLE_SECONDS,
        "absolute_timeout_seconds": _SESSION_ABSOLUTE_SECONDS,
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_blueprint.post("/api/auth/sessions/revoke")
def auth_revoke_session():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401
    target = _json_payload().get("id")
    if not isinstance(target, str) or not re.fullmatch(r"[a-f0-9]{64}", target):
        return jsonify({"error": "Choose a device from the list."}), 400
    current_hash = _session_key_hash(session.get("copy_maker_session_id"))
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT session_type FROM owner_sessions WHERE session_id_hash = ?", (target,)
        ).fetchone()
        cursor = connection.execute(
            "DELETE FROM owner_sessions WHERE session_id_hash = ?", (target,)
        )
        connection.commit()
    finally:
        connection.close()
    if not cursor.rowcount:
        return jsonify({"error": "That device is no longer connected."}), 404
    if row and row["session_type"] == "extension":
        if not _rotate_local_extension_token():
            return jsonify({"error": "The extension was disconnected, but Stash could not rotate its local access key."}), 500
    if target == current_hash:
        session.clear()
        try:
            from vault_manager import lock_vault

            lock_vault(force=True)
        except Exception:
            current_app.logger.warning("Could not lock Vault after revoking this device session")
    return jsonify({"success": True, "signed_out_current": target == current_hash})


@auth_blueprint.post("/api/auth/sessions/revoke-others")
def auth_revoke_other_sessions():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401
    current_hash = _session_key_hash(session.get("copy_maker_session_id"))
    connection = _connect()
    try:
        extension_was_connected = connection.execute(
            "SELECT 1 FROM owner_sessions WHERE session_type = 'extension' LIMIT 1"
        ).fetchone() is not None
        cursor = connection.execute(
            "DELETE FROM owner_sessions WHERE session_id_hash != ?", (current_hash,)
        )
        connection.commit()
    finally:
        connection.close()
    if extension_was_connected and not _rotate_local_extension_token():
        return jsonify({"error": "Other devices were signed out, but Stash could not rotate the extension access key."}), 500
    return jsonify({"success": True, "revoked": cursor.rowcount})


@auth_blueprint.post("/api/auth/logout")
def auth_logout():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    session_id = session.get("copy_maker_session_id")
    if isinstance(session_id, str):
        connection = _connect()
        try:
            connection.execute(
                "DELETE FROM owner_sessions WHERE session_id_hash = ?",
                (_session_key_hash(session_id),),
            )
            connection.commit()
        finally:
            connection.close()
    session.clear()
    return jsonify({"success": True})


def _cloud_storage_context():
    if not _FIREBASE_AUTH_READY or not firebase_storage or not _FIREBASE_STORAGE_BUCKET:
        return None, None, ("Firebase Cloud Storage is not configured yet.", 503)

    connection = _connect()
    try:
        account = connection.execute(
            "SELECT firebase_uid FROM owner_account WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()

    uid = account["firebase_uid"] if account else None
    if not uid:
        return None, None, (
            "Connect Google sign-in to this Stash account to use cloud storage.",
            409,
        )

    try:
        bucket = firebase_storage.bucket(
            name=_FIREBASE_STORAGE_BUCKET,
            app=_FIREBASE_APP,
        )
    except Exception:
        return None, None, ("Firebase Cloud Storage is not available yet.", 503)
    return uid, bucket, None


def get_firebase_storage_bucket():
    """Return the configured Firebase bucket for the shared Stash service.

    The shared service has its own accounts and metadata database, but uses the
    same server-side Firebase credentials.  Keeping this access point here
    prevents a browser extension from ever receiving Firebase admin
    credentials.
    """
    if not _FIREBASE_AUTH_READY or not firebase_storage or not _FIREBASE_STORAGE_BUCKET:
        return None
    try:
        return firebase_storage.bucket(
            name=_FIREBASE_STORAGE_BUCKET,
            app=_FIREBASE_APP,
        )
    except Exception:
        return None


def _cloud_storage_files(bucket, uid):
    prefix = f"users/{uid}/files/"
    files = []
    used_bytes = 0
    for blob in bucket.list_blobs(prefix=prefix):
        size = int(blob.size or 0)
        used_bytes += size
        metadata = blob.metadata or {}
        files.append({
            "name": blob.name,
            "displayName": metadata.get("copyMakerName") or blob.name.rsplit("/", 1)[-1],
            "sizeBytes": size,
            "contentType": blob.content_type or "application/octet-stream",
            "createdAt": blob.time_created.isoformat() if blob.time_created else None,
        })
    files.sort(key=lambda item: item["createdAt"] or "", reverse=True)
    return files, used_bytes


@auth_blueprint.get("/api/cloud-storage/status")
def cloud_storage_status():
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401

    uid, bucket, error = _cloud_storage_context()
    if error:
        message, status = error
        if status == 409:
            return jsonify({
                "ready": False,
                "linked": False,
                "usedBytes": 0,
                "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
                "error": message,
            })
        return jsonify({
            "ready": False,
            "linked": bool(uid),
            "usedBytes": 0,
            "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
            "error": message,
        }), status

    try:
        _, used_bytes = _cloud_storage_files(bucket, uid)
    except Exception:
        return jsonify({
            "ready": False,
            "linked": True,
            "usedBytes": 0,
            "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
            "error": "Set up the Firebase Storage bucket, then check again.",
        }), 503

    return jsonify({
        "ready": True,
        "linked": True,
        "usedBytes": used_bytes,
        "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
    })


@auth_blueprint.get("/api/cloud-storage/files")
def cloud_storage_list_files():
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401
    uid, bucket, error = _cloud_storage_context()
    if error:
        message, status = error
        return jsonify({"error": message}), status
    try:
        files, used_bytes = _cloud_storage_files(bucket, uid)
    except Exception:
        return jsonify({"error": "Set up the Firebase Storage bucket, then check again."}), 503
    return jsonify({
        "files": files,
        "usedBytes": used_bytes,
        "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
    })


@auth_blueprint.post("/api/cloud-storage/upload")
def cloud_storage_upload():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Choose a file to upload."}), 400
    safe_name = secure_filename(uploaded.filename) or "upload"
    try:
        uploaded.stream.seek(0, os.SEEK_END)
        file_size = uploaded.stream.tell()
        uploaded.stream.seek(0)
    except (AttributeError, OSError):
        return jsonify({"error": "Stash could not read that file."}), 400
    if file_size < 0 or file_size > _CLOUD_STORAGE_LIMIT_BYTES:
        return jsonify({"error": "That file is larger than the 2 GB demo limit."}), 413

    uid, bucket, error = _cloud_storage_context()
    if error:
        message, status = error
        return jsonify({"error": message}), status

    prefix = f"users/{uid}/files/"
    object_name = f"{prefix}{uuid.uuid4().hex}/{safe_name}"
    with _CLOUD_STORAGE_LOCK:
        try:
            _, used_bytes = _cloud_storage_files(bucket, uid)
            if used_bytes + file_size > _CLOUD_STORAGE_LIMIT_BYTES:
                return jsonify({
                    "error": "This upload would exceed the 2 GB demo limit. Remove a cloud file or choose a smaller file.",
                    "usedBytes": used_bytes,
                    "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
                }), 413
            blob = bucket.blob(object_name)
            blob.metadata = {"copyMakerName": safe_name}
            blob.content_disposition = f'attachment; filename="{safe_name}"'
            blob.upload_from_file(
                uploaded.stream,
                rewind=True,
                size=file_size,
                content_type=uploaded.mimetype or "application/octet-stream",
            )
        except Exception:
            return jsonify({"error": "The file could not be saved to Firebase Storage. Check that Storage is set up."}), 503

    return jsonify({
        "success": True,
        "file": {
            "name": object_name,
            "displayName": safe_name,
            "sizeBytes": file_size,
            "contentType": uploaded.mimetype or "application/octet-stream",
        },
        "usedBytes": used_bytes + file_size,
        "limitBytes": _CLOUD_STORAGE_LIMIT_BYTES,
    }), 201


@auth_blueprint.get("/api/cloud-storage/download")
def cloud_storage_download():
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401
    uid, bucket, error = _cloud_storage_context()
    if error:
        message, status = error
        return jsonify({"error": message}), status
    object_name = request.args.get("name", "")
    if not object_name.startswith(f"users/{uid}/files/"):
        return jsonify({"error": "That file is not in your cloud library."}), 404
    try:
        blob = bucket.blob(object_name)
        if not blob.exists():
            return jsonify({"error": "That cloud file could not be found."}), 404
        download_url = blob.generate_signed_url(
            expiration=timedelta(minutes=5),
            method="GET",
            version="v4",
        )
    except Exception:
        return jsonify({"error": "The cloud file could not be opened."}), 503
    return redirect(download_url, code=302)


@auth_blueprint.post("/api/cloud-storage/prepare-for-app")
def cloud_storage_prepare_for_app():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401
    payload = _json_payload()
    object_name = payload.get("name", "")
    app_key = payload.get("app", "")
    app_folders = {
        "capcut": "capcut",
        "davinci": "davinci",
        "cursor": "cursor",
    }
    app_names = {
        "capcut": "/Applications/CapCut.app",
        "davinci": "/Applications/DaVinci Resolve.app",
        "cursor": "/Applications/Cursor.app",
    }
    if not isinstance(object_name, str) or not isinstance(app_key, str) or app_key not in app_folders:
        return jsonify({"error": "Choose a cloud file and a supported app."}), 400

    uid, bucket, error = _cloud_storage_context()
    if error:
        message, status = error
        return jsonify({"error": message}), status
    if not object_name.startswith(f"users/{uid}/files/"):
        return jsonify({"error": "That file is not in your cloud library."}), 404

    folder = os.path.join(STORAGE_DIR, "integrations", app_folders[app_key])
    os.makedirs(folder, exist_ok=True)
    try:
        blob = bucket.blob(object_name)
        if not blob.exists():
            return jsonify({"error": "That cloud file could not be found."}), 404
        blob.reload()
        size = int(blob.size or 0)
        if size > 0 and shutil.disk_usage(folder).free < size:
            return jsonify({"error": "There is not enough free space on this Mac for that file."}), 507
        display_name = (blob.metadata or {}).get("copyMakerName") or object_name.rsplit("/", 1)[-1]
        filename = secure_filename(display_name) or "cloud-file"
        destination = os.path.join(folder, filename)
        if os.path.exists(destination):
            stem, extension = os.path.splitext(filename)
            destination = os.path.join(folder, f"{stem}_{secrets.token_hex(4)}{extension}")
        blob.download_to_filename(destination)
        subprocess.Popen(
            ["open", "-R", destination],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return jsonify({"error": "The cloud file could not be prepared on this Mac."}), 503

    try:
        launched = subprocess.run(
            ["open", "-a", app_names[app_key]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=False,
        )
        app_opened = launched.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        app_opened = False

    next_steps = {
        "capcut": f"In CapCut, choose New project → Import and select {os.path.basename(destination)}.",
        "davinci": f"In Resolve, use Media Pool → Import Media and select {os.path.basename(destination)}.",
        "cursor": f"The copy is ready in Cursor's handoff folder: {os.path.basename(destination)}.",
    }
    return jsonify({
        "success": True,
        "displayName": filename,
        "app": app_key,
        "appOpened": app_opened,
        "nextStep": next_steps[app_key],
    })


@auth_blueprint.delete("/api/cloud-storage/files")
def cloud_storage_delete_file():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "Sign in to Stash first."}), 401
    uid, bucket, error = _cloud_storage_context()
    if error:
        message, status = error
        return jsonify({"error": message}), status
    object_name = _json_payload().get("name", "")
    if not isinstance(object_name, str) or not object_name.startswith(f"users/{uid}/files/"):
        return jsonify({"error": "That file is not in your cloud library."}), 404
    try:
        blob = bucket.blob(object_name)
        if not blob.exists():
            return jsonify({"error": "That cloud file could not be found."}), 404
        with _CLOUD_STORAGE_LOCK:
            blob.delete()
        _, used_bytes = _cloud_storage_files(bucket, uid)
    except Exception:
        return jsonify({"error": "The cloud file could not be removed."}), 503
    return jsonify({"success": True, "usedBytes": used_bytes})
