"""Accounts, extension pairing, and cloud library for shared Stash mode.

This module is deliberately separate from the original Mac-only library.
Set COPY_MAKER_SHARED_MODE=1 only on the public HTTPS server.  Each shared
account gets its own metadata rows and its own Firebase Storage prefix.
"""

import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from app_paths import BASE_DIR, STORAGE_DIR

from auth import (
    get_firebase_public_config,
    get_firebase_storage_bucket,
    request_is_same_origin,
    verify_firebase_id_token,
)


SHARED_STORAGE_DIR = STORAGE_DIR
SHARED_DATABASE = os.path.join(SHARED_STORAGE_DIR, "shared_service.sqlite3")
SHARED_MEDIA_DIR = os.path.join(SHARED_STORAGE_DIR, "shared_media")
SHARED_MODE_ENVIRONMENT_VARIABLE = "COPY_MAKER_SHARED_MODE"
SHARED_LOCAL_STORAGE_ENVIRONMENT_VARIABLE = "COPY_MAKER_SHARED_LOCAL_STORAGE"
PAIRING_LIFETIME_SECONDS = 10 * 60
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
TOKEN_BYTES = 32
LOGIN_WINDOW_SECONDS = 10 * 60
MAX_LOGIN_ATTEMPTS = 5

shared_blueprint = Blueprint("copy_maker_shared", __name__)
_LOGIN_FAILURES = {}


def shared_service_enabled():
    return os.environ.get(SHARED_MODE_ENVIRONMENT_VARIABLE, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def shared_local_storage_enabled():
    return os.environ.get(SHARED_LOCAL_STORAGE_ENVIRONMENT_VARIABLE, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _connect():
    connection = sqlite3.connect(SHARED_DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _now():
    return int(time.time())


def _token_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_text(value, limit=2000):
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _login_key(username):
    return (request.remote_addr or "unknown", username)


def _recent_login_failures(key, now):
    attempts = [
        attempt for attempt in _LOGIN_FAILURES.get(key, [])
        if now - attempt < LOGIN_WINDOW_SECONDS
    ]
    _LOGIN_FAILURES[key] = attempts
    return attempts


def _shared_user_id():
    user_id = session.get("stash_shared_account_id")
    return user_id if isinstance(user_id, int) else None


def _account_for_session():
    user_id = _shared_user_id()
    if user_id is None:
        return None
    connection = _connect()
    try:
        return connection.execute(
            "SELECT id, username, storage_key, firebase_uid, email, phone_number "
            "FROM shared_account WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        connection.close()


def _set_session(account):
    session["stash_shared_account_id"] = account["id"]
    session["stash_shared_username"] = account["username"]
    session.permanent = True


def _clear_session():
    session.pop("stash_shared_account_id", None)
    session.pop("stash_shared_username", None)


def _require_session_account():
    account = _account_for_session()
    if not account:
        return None, (jsonify({"error": "Sign in to Stash first."}), 401)
    return account, None


def _extension_account():
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 1024:
        return None

    connection = _connect()
    try:
        installation = connection.execute(
            """
            SELECT shared_account.id, shared_account.username, shared_account.storage_key,
                   extension_installation.id AS installation_id
            FROM extension_installation
            JOIN shared_account ON shared_account.id = extension_installation.account_id
            WHERE extension_installation.token_hash = ?
              AND extension_installation.revoked_at IS NULL
            """,
            (_token_hash(token),),
        ).fetchone()
        if installation:
            connection.execute(
                "UPDATE extension_installation SET last_used_at = ? WHERE id = ?",
                (_now(), installation["installation_id"]),
            )
            connection.commit()
        return installation
    finally:
        connection.close()


def _bucket_or_error():
    bucket = get_firebase_storage_bucket()
    if not bucket:
        return None, (
            jsonify({
                "error": "Cloud storage is not configured yet. Finish Firebase Storage setup before using shared Stash.",
            }),
            503,
        )
    return bucket, None


def _local_media_path(object_name):
    if not isinstance(object_name, str) or not object_name.startswith("local:"):
        return None
    relative_path = object_name[len("local:"):]
    if not relative_path or os.path.isabs(relative_path):
        return None
    root = os.path.realpath(SHARED_MEDIA_DIR)
    path = os.path.realpath(os.path.join(root, relative_path))
    try:
        if os.path.commonpath((root, path)) != root:
            return None
    except ValueError:
        return None
    return path


def _reserve_storage_space(account_id, size_bytes):
    reservation_id = uuid.uuid4().hex
    now = _now()
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM shared_storage_reservation WHERE expires_at <= ?",
            (now,),
        )
        used_row = connection.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS used FROM shared_library_item "
            "WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        reserved_row = connection.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS reserved "
            "FROM shared_storage_reservation WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        used = int(used_row["used"] or 0) + int(reserved_row["reserved"] or 0)
        if used + size_bytes > MAX_UPLOAD_BYTES:
            connection.rollback()
            return None
        connection.execute(
            "INSERT INTO shared_storage_reservation (id, account_id, size_bytes, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (reservation_id, account_id, size_bytes, now + 86400),
        )
        connection.commit()
        return reservation_id
    finally:
        connection.close()


def _release_storage_space(reservation_id):
    if not reservation_id:
        return
    connection = _connect()
    try:
        connection.execute(
            "DELETE FROM shared_storage_reservation WHERE id = ?",
            (reservation_id,),
        )
        connection.commit()
    finally:
        connection.close()


def _shared_registration_open():
    return os.environ.get("COPY_MAKER_SHARED_REGISTRATION_OPEN", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _insert_library_item(account_id, item_type, name, mime_type, source_url,
                         page_url, content, object_name, size_bytes):
    connection = _connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO shared_library_item
                (account_id, item_type, display_name, mime_type, source_url,
                 page_url, text_content, object_name, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id, item_type, name, mime_type, source_url, page_url,
                content, object_name, size_bytes,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def _delete_library_item(item_id, account_id):
    connection = _connect()
    try:
        item = connection.execute(
            "SELECT * FROM shared_library_item WHERE id = ? AND account_id = ?",
            (item_id, account_id),
        ).fetchone()
        if item:
            connection.execute("DELETE FROM shared_library_item WHERE id = ?", (item_id,))
            connection.commit()
        return item
    finally:
        connection.close()


def _item_response(item):
    try:
        tags = json.loads(item["tags_json"] or "[]")
        if not isinstance(tags, list):
            tags = []
    except (KeyError, TypeError, json.JSONDecodeError):
        tags = []
    response = {
        "id": item["id"],
        "type": item["item_type"],
        "original_name": item["display_name"] or "Untitled copy",
        "title": item["display_name"] or "Untitled copy",
        "mime_type": item["mime_type"] or "text/plain",
        "size": item["size_bytes"] or 0,
        "source_url": item["source_url"] or "",
        "page_url": item["page_url"] or "",
        "content": item["text_content"] or "",
        "created_at": item["created_at"],
        "client_key": item["client_key"] or "",
        "folder_name": item["folder_name"] or "",
        "tags": [str(tag)[:24] for tag in tags if isinstance(tag, str)][:12],
        "favorite": bool(item["is_favorite"]),
        "saved_at": item["saved_at"] or 0,
    }
    if item["object_name"]:
        response["url"] = f"/api/shared/media/{item['id']}"
    elif item["source_url"]:
        response["url"] = item["source_url"]
    else:
        response["url"] = ""
    return response


def _upload_stream(account, stream, name, mime_type, size_bytes, item_type,
                   source_url="", page_url=""):
    if size_bytes <= 0:
        return None, (jsonify({"error": "The uploaded file is empty."}), 400)
    if size_bytes > MAX_UPLOAD_BYTES:
        return None, (
            jsonify({"error": "The file is larger than the 2 GB Stash limit."}),
            413,
        )

    safe_name = secure_filename(name) or "stash-upload"
    bucket = None
    local_path = None
    reservation_id = _reserve_storage_space(account["id"], size_bytes)
    if not reservation_id:
        return None, (
            jsonify({"error": "This account has reached its 2 GB Stash storage limit. Delete an item or choose a smaller file."}),
            413,
        )
    if shared_local_storage_enabled():
        relative_path = os.path.join(
            account["storage_key"], uuid.uuid4().hex, safe_name,
        )
        local_path = _local_media_path("local:" + relative_path)
        if not local_path:
            _release_storage_space(reservation_id)
            return None, (
                jsonify({"error": "Stash could not prepare local storage."}),
                500,
            )
        try:
            os.makedirs(os.path.dirname(local_path), mode=0o700, exist_ok=False)
            with open(local_path, "xb") as output_file:
                shutil.copyfileobj(stream, output_file, length=1024 * 1024)
            if os.path.getsize(local_path) != size_bytes:
                raise OSError("The saved file size did not match the upload.")
            os.chmod(local_path, 0o600)
            object_name = "local:" + relative_path
        except Exception:
            try:
                if local_path and os.path.exists(local_path):
                    os.remove(local_path)
            except OSError:
                pass
            _release_storage_space(reservation_id)
            return None, (
                jsonify({"error": "Stash could not save that file to this Mac."}),
                503,
            )
    else:
        bucket, error = _bucket_or_error()
        if error:
            _release_storage_space(reservation_id)
            return None, error
        object_name = (
            f"shared-users/{account['storage_key']}/"
            f"{uuid.uuid4().hex}/{safe_name}"
        )
        try:
            blob = bucket.blob(object_name)
            blob.metadata = {"stashName": safe_name, "stashAccount": str(account["id"])}
            blob.content_disposition = f'attachment; filename="{safe_name}"'
            blob.upload_from_file(
                stream,
                rewind=False,
                size=size_bytes,
                content_type=mime_type or "application/octet-stream",
            )
        except Exception:
            _release_storage_space(reservation_id)
            return None, (
                jsonify({"error": "Stash could not save that file to cloud storage."}),
                503,
            )

    try:
        item_id = _insert_library_item(
            account["id"], item_type, safe_name,
            mime_type or "application/octet-stream", source_url, page_url, "",
            object_name, size_bytes,
        )
    except Exception:
        if local_path:
            try:
                os.remove(local_path)
            except OSError:
                pass
        else:
            try:
                bucket.delete_blob(object_name)
            except Exception:
                pass
        _release_storage_space(reservation_id)
        return None, (
            jsonify({"error": "Stash could not record the saved file."}),
            500,
        )

    _release_storage_space(reservation_id)

    connection = _connect()
    try:
        item = connection.execute(
            "SELECT * FROM shared_library_item WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        connection.close()
    return _item_response(item), None


def initialize_shared_service(app):
    os.makedirs(SHARED_STORAGE_DIR, exist_ok=True)
    connection = _connect()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS shared_account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extension_pairing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                code_hash TEXT NOT NULL UNIQUE,
                expires_at INTEGER NOT NULL,
                used_at INTEGER,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES shared_account(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS extension_installation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER,
                revoked_at INTEGER,
                FOREIGN KEY(account_id) REFERENCES shared_account(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shared_library_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                display_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                text_content TEXT NOT NULL DEFAULT '',
                object_name TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                client_key TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                is_favorite INTEGER NOT NULL DEFAULT 0,
                saved_at INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(account_id) REFERENCES shared_account(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS shared_storage_reservation (
                id TEXT PRIMARY KEY,
                account_id INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES shared_account(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_shared_library_account_created
                ON shared_library_item(account_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_extension_installation_token
                ON extension_installation(token_hash);
            """
        )
        account_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(shared_account)").fetchall()
        }
        library_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(shared_library_item)").fetchall()
        }
        for name, declaration in (
            ("client_key", "TEXT NOT NULL DEFAULT ''"),
            ("folder_name", "TEXT NOT NULL DEFAULT ''"),
            ("tags_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("is_favorite", "INTEGER NOT NULL DEFAULT 0"),
            ("saved_at", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in library_columns:
                connection.execute(f"ALTER TABLE shared_library_item ADD COLUMN {name} {declaration}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_shared_library_account_client_key "
            "ON shared_library_item(account_id, client_key) WHERE client_key <> ''"
        )
        if "firebase_uid" not in account_columns:
            connection.execute("ALTER TABLE shared_account ADD COLUMN firebase_uid TEXT")
        if "email" not in account_columns:
            connection.execute("ALTER TABLE shared_account ADD COLUMN email TEXT")
        if "phone_number" not in account_columns:
            connection.execute("ALTER TABLE shared_account ADD COLUMN phone_number TEXT")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_shared_account_firebase_uid "
            "ON shared_account(firebase_uid) WHERE firebase_uid IS NOT NULL"
        )
        connection.commit()
    finally:
        connection.close()
    try:
        os.chmod(SHARED_DATABASE, 0o600)
        os.makedirs(SHARED_MEDIA_DIR, mode=0o700, exist_ok=True)
        os.chmod(SHARED_MEDIA_DIR, 0o700)
    except OSError:
        app.logger.warning("Could not restrict Shared Stash local storage permissions")


@shared_blueprint.before_request
def require_shared_mode():
    if not shared_service_enabled():
        return jsonify({
            "error": "Shared Stash is not enabled on this server.",
        }), 404
    if request.method in {"POST", "PUT", "PATCH"}:
        is_upload = request.path in {
            "/api/shared/upload",
            "/api/shared/share",
            "/api/shared/extensions/browser-copy",
            "/api/shared/native-sync",
        }
        body_limit = MAX_UPLOAD_BYTES + 1024 * 1024 if is_upload else 1024 * 1024
        try:
            request.max_content_length = body_limit
        except AttributeError:
            if request.content_length is not None and request.content_length > body_limit:
                return jsonify({"error": "This request is larger than Stash allows."}), 413
    return None


@shared_blueprint.get("/api/shared/status")
def shared_status():
    account = _account_for_session()
    local_storage = shared_local_storage_enabled()
    firebase_config = get_firebase_public_config()
    return jsonify({
        "authenticated": bool(account),
        "username": (account["email"] or account["phone_number"] or account["username"]) if account else None,
        "identity": (account["email"] or account["phone_number"] or account["username"]) if account else None,
        "cloudReady": local_storage or bool(get_firebase_storage_bucket()),
        "storageMode": "local" if local_storage else "cloud",
        "registrationOpen": _shared_registration_open(),
        "sharedMode": shared_service_enabled(),
        "firebaseConfigured": bool(firebase_config),
        "firebaseConfig": firebase_config,
    })


@shared_blueprint.post("/api/shared/signup")
def shared_signup():
    return jsonify({
        "error": "Create or sign in with a verified email address or phone number.",
    }), 410


@shared_blueprint.post("/api/shared/firebase-login")
def shared_firebase_login():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    claims, error = verify_firebase_id_token(payload)
    if error:
        return error

    firebase_claims = claims.get("firebase") or {}
    provider = firebase_claims.get("sign_in_provider")
    email = claims.get("email") if provider == "password" else None
    phone_number = claims.get("phone_number") if provider == "phone" else None
    if provider == "password":
        if not isinstance(email, str) or not email.strip() or claims.get("email_verified") is not True:
            return jsonify({"error": "Verify your email address, then sign in again."}), 403
        email = email.strip().lower()
    elif provider == "phone":
        if not isinstance(phone_number, str) or not re.fullmatch(r"\+[1-9]\d{6,14}", phone_number):
            return jsonify({"error": "Verify your phone number, then try again."}), 403
    else:
        return jsonify({"error": "Use a verified email address or phone number for Shared Stash."}), 403

    if not _shared_registration_open():
        connection = _connect()
        try:
            exists = connection.execute(
                "SELECT 1 FROM shared_account WHERE firebase_uid = ?",
                (claims["uid"],),
            ).fetchone()
        finally:
            connection.close()
        if not exists:
            return jsonify({"error": "New account registration is closed."}), 403

    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        account = connection.execute(
            "SELECT id, username, storage_key, firebase_uid, email, phone_number "
            "FROM shared_account WHERE firebase_uid = ?",
            (claims["uid"],),
        ).fetchone()
        if account:
            connection.execute(
                "UPDATE shared_account SET email = COALESCE(?, email), "
                "phone_number = COALESCE(?, phone_number) WHERE id = ?",
                (email, phone_number, account["id"]),
            )
            connection.commit()
            account = connection.execute(
                "SELECT id, username, storage_key, firebase_uid, email, phone_number "
                "FROM shared_account WHERE id = ?",
                (account["id"],),
            ).fetchone()
            status_code = 200
        else:
            internal_name = "member-" + hashlib.sha256(claims["uid"].encode("utf-8")).hexdigest()[:24]
            cursor = connection.execute(
                "INSERT INTO shared_account "
                "(username, password_hash, storage_key, created_at, firebase_uid, email, phone_number) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    internal_name,
                    generate_password_hash(secrets.token_urlsafe(48), method="scrypt"),
                    uuid.uuid4().hex,
                    datetime.now(timezone.utc).isoformat(),
                    claims["uid"], email, phone_number,
                ),
            )
            connection.commit()
            account = connection.execute(
                "SELECT id, username, storage_key, firebase_uid, email, phone_number "
                "FROM shared_account WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            status_code = 201
    except sqlite3.IntegrityError:
        connection.rollback()
        return jsonify({"error": "This sign-in is already connected to another Stash account."}), 409
    except sqlite3.Error:
        connection.rollback()
        return jsonify({"error": "Stash could not create your private workspace."}), 500
    finally:
        connection.close()

    _set_session(account)
    identity = email or phone_number
    return jsonify({
        "success": True,
        "identity": identity,
        "newWorkspace": status_code == 201,
    }), status_code


@shared_blueprint.post("/api/shared/login")
def shared_login():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    payload = request.get_json(silent=True) or {}
    username = _safe_text(payload.get("username"), 32).lower()
    password = payload.get("password")
    key = _login_key(username)
    now = _now()
    failures = _recent_login_failures(key, now)
    if len(failures) >= MAX_LOGIN_ATTEMPTS:
        retry_after = max(1, LOGIN_WINDOW_SECONDS - (now - failures[0]))
        response = jsonify({"error": "Too many attempts. Please wait a few minutes and try again."})
        response.headers["Retry-After"] = str(retry_after)
        return response, 429
    connection = _connect()
    try:
        account = connection.execute(
            "SELECT id, username, password_hash FROM shared_account WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        connection.close()

    if not account or not isinstance(password, str) or not check_password_hash(
        account["password_hash"], password,
    ):
        failures.append(now)
        return jsonify({"error": "Username or password is incorrect."}), 401
    _LOGIN_FAILURES.pop(key, None)
    _set_session(account)
    return jsonify({"success": True, "username": account["username"]})


@shared_blueprint.post("/api/shared/logout")
def shared_logout():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    _clear_session()
    return jsonify({"success": True})


@shared_blueprint.get("/api/shared/library")
def shared_library():
    account, error = _require_session_account()
    if error:
        return error
    connection = _connect()
    try:
        items = connection.execute(
            "SELECT * FROM shared_library_item WHERE account_id = ? ORDER BY id DESC",
            (account["id"],),
        ).fetchall()
    finally:
        connection.close()
    return jsonify([_item_response(item) for item in items])


@shared_blueprint.route("/api/shared/native-sync", methods=["GET", "POST"])
def shared_native_sync():
    """Authenticated, idempotent sync endpoint for the native Android library."""
    account, error = _require_session_account()
    if error:
        return error
    if request.method == "GET":
        connection = _connect()
        try:
            rows = connection.execute(
                "SELECT * FROM shared_library_item WHERE account_id = ? ORDER BY id DESC",
                (account["id"],),
            ).fetchall()
        finally:
            connection.close()
        return jsonify([_item_response(row) for row in rows])

    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    payload = request.get_json(silent=True) if request.is_json else None
    payload = payload if isinstance(payload, dict) else request.form
    client_key = _safe_text(payload.get("client_key"), 128)
    if not client_key or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", client_key):
        return jsonify({"error": "A valid local item ID is required for sync."}), 400

    try:
        remote_id = int(payload.get("remote_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "The shared item ID is invalid."}), 400
    item_type = _safe_text(payload.get("item_type"), 32).lower()
    if item_type not in {"text", "link", "image", "audio", "video", "file"}:
        return jsonify({"error": "This Stash item type cannot be synced."}), 400
    title = _safe_text(payload.get("title"), 180) or "Untitled copy"
    mime_type = _safe_text(payload.get("mime_type"), 200) or "text/plain"
    content = _safe_text(payload.get("content"), 100000)
    source_url = _safe_text(payload.get("source_url"), 4000)
    folder_name = _safe_text(payload.get("folder_name"), 40)
    if folder_name and not re.fullmatch(r"[\w -]+", folder_name, flags=re.UNICODE):
        return jsonify({"error": "The folder name contains unsupported characters."}), 400
    raw_tags = payload.get("tags")
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except json.JSONDecodeError:
            raw_tags = []
    tags = []
    if isinstance(raw_tags, list):
        tags = list(dict.fromkeys(
            _safe_text(tag, 24) for tag in raw_tags if isinstance(tag, str) and _safe_text(tag, 24)
        ))[:12]
    tags_json = json.dumps(tags, ensure_ascii=False)
    favorite_value = payload.get("favorite", False)
    is_favorite = favorite_value is True or str(favorite_value).lower() in {"1", "true", "yes"}
    try:
        saved_at = max(0, int(payload.get("saved_at") or 0))
    except (TypeError, ValueError):
        saved_at = 0

    connection = _connect()
    try:
        existing = None
        if remote_id:
            existing = connection.execute(
                "SELECT * FROM shared_library_item WHERE id = ? AND account_id = ?",
                (remote_id, account["id"]),
            ).fetchone()
            if not existing:
                return jsonify({"error": "That Shared Stash item no longer exists."}), 404
        else:
            existing = connection.execute(
                "SELECT * FROM shared_library_item WHERE account_id = ? AND client_key = ?",
                (account["id"], client_key),
            ).fetchone()
        collision = connection.execute(
            "SELECT id FROM shared_library_item WHERE account_id = ? AND client_key = ?",
            (account["id"], client_key),
        ).fetchone()
        if collision and (not existing or collision["id"] != existing["id"]):
            return jsonify({"error": "That local item ID is already linked to another shared copy."}), 409
    finally:
        connection.close()

    uploaded = request.files.get("file") if not request.is_json else None
    created = existing is None
    if existing and uploaded and uploaded.filename:
        return jsonify({"error": "Shared file contents cannot be replaced during metadata sync."}), 409

    if existing:
        connection = _connect()
        try:
            connection.execute(
                """UPDATE shared_library_item SET client_key = ?, item_type = ?, display_name = ?,
                   mime_type = ?, source_url = ?, page_url = ?, text_content = ?, folder_name = ?,
                   tags_json = ?, is_favorite = ?, saved_at = ? WHERE id = ? AND account_id = ?""",
                (
                    client_key, item_type, title, mime_type, source_url, source_url, content,
                    folder_name, tags_json, int(is_favorite), saved_at or existing["saved_at"],
                    existing["id"], account["id"],
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM shared_library_item WHERE id = ?", (existing["id"],),
            ).fetchone()
        finally:
            connection.close()
        return jsonify({"success": True, "item": _item_response(row)})

    if uploaded and uploaded.filename:
        try:
            uploaded.stream.seek(0, os.SEEK_END)
            size_bytes = uploaded.stream.tell()
            uploaded.stream.seek(0)
        except (AttributeError, OSError):
            return jsonify({"error": "Stash could not read the shared file."}), 400
        item, upload_error = _upload_stream(
            account, uploaded.stream, title or uploaded.filename, mime_type,
            size_bytes, item_type, source_url, source_url,
        )
        if upload_error:
            return upload_error
        remote_id = int(item["id"])
    else:
        remote_id = _insert_library_item(
            account["id"], item_type, title, mime_type, source_url, source_url,
            content, "", 0,
        )

    connection = _connect()
    try:
        connection.execute(
            """UPDATE shared_library_item SET client_key = ?, folder_name = ?, tags_json = ?,
               is_favorite = ?, saved_at = ? WHERE id = ? AND account_id = ?""",
            (client_key, folder_name, tags_json, int(is_favorite), saved_at, remote_id, account["id"]),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM shared_library_item WHERE id = ?", (remote_id,),
        ).fetchone()
    finally:
        connection.close()
    return jsonify({"success": True, "item": _item_response(row)}), 201 if created else 200


@shared_blueprint.post("/api/shared/upload")
def shared_upload():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    account, error = _require_session_account()
    if error:
        return error
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Choose a file to upload."}), 400
    try:
        uploaded.stream.seek(0, os.SEEK_END)
        size_bytes = uploaded.stream.tell()
        uploaded.stream.seek(0)
    except (AttributeError, OSError):
        return jsonify({"error": "Stash could not read that file."}), 400
    item_type = (
        "video" if (uploaded.mimetype or "").startswith("video/")
        else "audio" if (uploaded.mimetype or "").startswith("audio/")
        else "image" if (uploaded.mimetype or "").startswith("image/")
        else "file"
    )
    item, upload_error = _upload_stream(
        account, uploaded.stream, uploaded.filename, uploaded.mimetype,
        size_bytes, item_type,
    )
    if upload_error:
        return upload_error
    return jsonify({"success": True, "item": item}), 201


@shared_blueprint.post("/api/shared/share")
def shared_receive_share():
    """Save media files or a page link received from a phone share sheet."""
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    account, error = _require_session_account()
    if error:
        return error

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    source_url = _safe_text(payload.get("url") or request.form.get("url"), 4000)
    title = _safe_text(payload.get("title") or request.form.get("title"), 180)
    text_content = _safe_text(payload.get("text") or request.form.get("text"), 100000)
    uploads = request.files.getlist("files") or request.files.getlist("file")
    uploads = [uploaded for uploaded in uploads if uploaded and uploaded.filename]

    if uploads:
        saved_items = []
        for uploaded in uploads:
            name = _safe_text(uploaded.filename, 240)
            mime_type = _safe_text(uploaded.mimetype, 200)
            if not mime_type or mime_type == "application/octet-stream":
                mime_type = mimetypes.guess_type(name)[0] or mime_type
            item_type = (
                "video" if mime_type.startswith("video/")
                else "audio" if mime_type.startswith("audio/")
                else "image" if mime_type.startswith("image/")
                else ""
            )
            if not item_type:
                return jsonify({
                    "error": "Share a video, audio, or image file with Stash.",
                }), 400
            try:
                uploaded.stream.seek(0, os.SEEK_END)
                size_bytes = uploaded.stream.tell()
                uploaded.stream.seek(0)
            except (AttributeError, OSError):
                return jsonify({"error": "Stash could not read that shared file."}), 400

            item, upload_error = _upload_stream(
                account,
                uploaded.stream,
                name,
                mime_type,
                size_bytes,
                item_type,
                source_url,
                source_url,
            )
            if upload_error:
                return upload_error
            saved_items.append(item)

        return jsonify({
            "success": True,
            "kind": "media",
            "count": len(saved_items),
            "items": saved_items,
        }), 201

    if not source_url and text_content:
        match = re.search(r"https?://[^\s<>\"']+", text_content)
        if match:
            source_url = match.group(0).rstrip(".,);]")
    try:
        parsed_url = urlsplit(source_url)
    except ValueError:
        parsed_url = None
    if (
        not parsed_url
        or parsed_url.scheme.lower() not in {"http", "https"}
        or not parsed_url.netloc
    ):
        return jsonify({
            "error": "Share a media file, or provide a full http or https page link.",
        }), 400

    item_name = title or text_content or source_url
    item_id = _insert_library_item(
        account["id"], "link", item_name[:180], "text/uri-list",
        source_url, source_url, text_content, "", 0,
    )
    connection = _connect()
    try:
        item = connection.execute(
            "SELECT * FROM shared_library_item WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        connection.close()
    return jsonify({
        "success": True,
        "kind": "link",
        "item": _item_response(item),
    }), 201


@shared_blueprint.delete("/api/shared/library/<int:item_id>")
def shared_delete_library_item(item_id):
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    account, error = _require_session_account()
    if error:
        return error
    item = _delete_library_item(item_id, account["id"])
    if not item:
        return jsonify({"error": "That saved item could not be found."}), 404
    if item["object_name"]:
        bucket = get_firebase_storage_bucket()
        if bucket:
            try:
                bucket.delete_blob(item["object_name"])
            except Exception:
                pass
    return jsonify({"success": True})


@shared_blueprint.get("/api/shared/media/<int:item_id>")
def shared_media(item_id):
    account, error = _require_session_account()
    if error:
        return error
    connection = _connect()
    try:
        item = connection.execute(
            "SELECT * FROM shared_library_item WHERE id = ? AND account_id = ?",
            (item_id, account["id"]),
        ).fetchone()
    finally:
        connection.close()
    if not item or not item["object_name"]:
        return jsonify({"error": "That saved file could not be found."}), 404
    bucket, bucket_error = _bucket_or_error()
    if bucket_error:
        return bucket_error
    try:
        signed_url = bucket.blob(item["object_name"]).generate_signed_url(
            expiration=timedelta(minutes=5), method="GET", version="v4",
        )
    except Exception:
        return jsonify({"error": "Stash could not open that file."}), 503
    return redirect(signed_url, code=302)


@shared_blueprint.post("/api/shared/pairing-code")
def create_pairing_code():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    account, error = _require_session_account()
    if error:
        return error
    code = secrets.token_urlsafe(24)
    now = _now()
    connection = _connect()
    try:
        connection.execute("DELETE FROM extension_pairing WHERE expires_at < ? OR used_at IS NOT NULL", (now,))
        connection.execute(
            """
            INSERT INTO extension_pairing (account_id, code_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (account["id"], _token_hash(code), now + PAIRING_LIFETIME_SECONDS, now),
        )
        connection.commit()
    finally:
        connection.close()
    return jsonify({
        "code": code,
        "expiresInSeconds": PAIRING_LIFETIME_SECONDS,
        "serverUrl": request.url_root.rstrip("/"),
    })


@shared_blueprint.get("/api/shared/extensions")
def shared_extensions():
    account, error = _require_session_account()
    if error:
        return error
    connection = _connect()
    try:
        installations = connection.execute(
            """
            SELECT id, label, created_at, last_used_at
            FROM extension_installation
            WHERE account_id = ? AND revoked_at IS NULL
            ORDER BY id DESC
            """,
            (account["id"],),
        ).fetchall()
    finally:
        connection.close()
    return jsonify([
        {
            "id": installation["id"],
            "label": installation["label"],
            "createdAt": installation["created_at"],
            "lastUsedAt": installation["last_used_at"],
        }
        for installation in installations
    ])


@shared_blueprint.delete("/api/shared/extensions/<int:installation_id>")
def revoke_shared_extension(installation_id):
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    account, error = _require_session_account()
    if error:
        return error
    connection = _connect()
    try:
        cursor = connection.execute(
            """
            UPDATE extension_installation
            SET revoked_at = ?
            WHERE id = ? AND account_id = ? AND revoked_at IS NULL
            """,
            (_now(), installation_id, account["id"]),
        )
        connection.commit()
    finally:
        connection.close()
    if cursor.rowcount != 1:
        return jsonify({"error": "That connected browser could not be found."}), 404
    return jsonify({"success": True})


@shared_blueprint.post("/api/shared/extensions/pair")
def pair_extension():
    payload = request.get_json(silent=True) or {}
    code = payload.get("code")
    label = _safe_text(payload.get("label"), 80) or "Chrome extension"
    if not isinstance(code, str) or len(code) > 512:
        return jsonify({"error": "Enter the pairing code from Stash."}), 400
    now = _now()
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        pairing = connection.execute(
            """
            SELECT * FROM extension_pairing
            WHERE code_hash = ? AND used_at IS NULL AND expires_at >= ?
            """,
            (_token_hash(code), now),
        ).fetchone()
        if not pairing:
            connection.rollback()
            return jsonify({"error": "That pairing code has expired or was already used."}), 401
        token = secrets.token_urlsafe(TOKEN_BYTES)
        cursor = connection.execute(
            """
            INSERT INTO extension_installation (account_id, label, token_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (pairing["account_id"], label, _token_hash(token), now),
        )
        connection.execute(
            "UPDATE extension_pairing SET used_at = ? WHERE id = ?",
            (now, pairing["id"]),
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        return jsonify({"error": "Stash could not connect this extension."}), 500
    finally:
        connection.close()
    return jsonify({
        "success": True,
        "accessToken": token,
        "installationId": cursor.lastrowid,
    }), 201


@shared_blueprint.post("/api/shared/extensions/video-capture-start")
def shared_video_capture_start():
    account = _extension_account()
    if not account:
        return jsonify({"error": "Connect this extension to Stash first."}), 401
    # A website cannot write to a person's system clipboard. Returning success
    # keeps the extension's existing capture flow working and makes the
    # difference explicit in the final copy response.
    return jsonify({"success": True, "clipboard_change_count": None})


@shared_blueprint.post("/api/shared/extensions/browser-copy")
def shared_extension_browser_copy():
    account = _extension_account()
    if not account:
        return jsonify({"error": "Connect this extension to Stash first."}), 401

    item_type = _safe_text(request.headers.get("X-Copy-Maker-Type"), 20).lower()
    if item_type in {"video", "audio"}:
        content_length = request.content_length
        if content_length is None or content_length <= 0:
            return jsonify({"error": "Stash received an empty media file."}), 400
        name = _safe_text(request.headers.get("X-Copy-Maker-Title"), 180)
        if not name:
            name = f"copied-{item_type}"
        item, upload_error = _upload_stream(
            account,
            request.stream,
            name,
            _safe_text(request.headers.get("Content-Type"), 200) or "application/octet-stream",
            content_length,
            item_type,
            _safe_text(request.headers.get("X-Copy-Maker-URL"), 4000),
            _safe_text(request.headers.get("X-Copy-Maker-Page"), 4000),
        )
        if upload_error:
            return upload_error
        return jsonify({
            "success": True,
            "clipboard_published": False,
            "message": "Saved to your Stash cloud library.",
            "item": item,
        }), 201

    payload = request.get_json(silent=True) or {}
    item_type = _safe_text(payload.get("type"), 20).lower()
    if item_type not in {"text", "image", "link", "file"}:
        return jsonify({"error": "Stash could not identify this item."}), 400
    source_url = _safe_text(payload.get("url"), 4000)
    text_content = _safe_text(payload.get("text"), 100000)
    name = _safe_text(payload.get("title"), 180) or (
        text_content[:80] if text_content else source_url[:180] or "Saved copy"
    )
    item_id = _insert_library_item(
        account["id"], item_type, name, "text/plain", source_url,
        _safe_text(payload.get("page_url"), 4000), text_content, "", 0,
    )
    connection = _connect()
    try:
        item = connection.execute(
            "SELECT * FROM shared_library_item WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        connection.close()
    return jsonify({
        "success": True,
        "clipboard_published": False,
        "message": "Saved to your Stash cloud library.",
        "item": _item_response(item),
    }), 201
