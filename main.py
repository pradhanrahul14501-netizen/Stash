from flask import Blueprint, Flask, Response, request, jsonify, send_file, send_from_directory, stream_with_context
import threading
import time
import os
import secrets
import json
import io
import zipfile
import xml.etree.ElementTree as ET
import plistlib
import tempfile
from datetime import datetime

_AVA_PENDING_FILE_ORGANIZATION = {}
_AVA_PENDING_FILE_COPY = {}
_AVA_PENDING_DELETE = {}
_AVA_PENDING_DELETE_LOCK = threading.Lock()
_AVA_PENDING_FILE_ACTION = {}
_AVA_PENDING_FILE_ACTION_LOCK = threading.Lock()
import base64
import hashlib
import ipaddress
import math
import mimetypes
import re
import shutil
import socket
import subprocess
import requests
from urllib.parse import quote, urljoin, urlparse
from werkzeug.utils import secure_filename
from ava.agent import AvaServiceError, run as ava_run
from ava.tools import get_item_category
from ava.unified_search import resolve_safe_mac_file
import storage_manager

from clipboard import (
    get_clipboard_content,
    get_clipboard_change_count,
    get_frontmost_app_bundle_id,
    set_file_on_system_clipboard
)
from storage_manager import (
    save_item,
    save_file,
    save_bytes,
    load_items,
    update_item,
    delete_item,
    save_metadata,
    save_metadata_with_next_id,
    get_workspace_mode_settings,
    set_workspace_mode_setting,
    infer_workspace_mode,
    clear_legacy_auto_delete_schedules,
    load_stash_folders,
    create_stash_folder,
    move_items_to_stash_folder,
    ensure_encrypted_media_storage,
    STORAGE_DIR as LOCAL_STORAGE_DIR,
    get_privacy_settings,
    set_privacy_settings,
    purge_expired_items,
)
from auth import (
    auth_blueprint,
    has_authenticated_session,
    initialize_auth,
    is_local_host,
    is_local_extension_pair_request,
    is_local_extension_request,
    is_trusted_proxy_request,
    is_trusted_secure_proxy_request,
    request_is_same_origin,
    rate_limit_auth_attempt,
    trusted_proxy_configured,
)
from shared_service import (
    initialize_shared_service,
    shared_blueprint,
    shared_service_enabled,
)
from secure_backup import (
    MAX_BACKUP_BYTES,
    apply_pending_restore,
    create_encrypted_backup,
    stage_restore,
)
from vault_manager import (
    VaultLockedError,
    add_entry as add_vault_entry,
    create_vault,
    delete_entry as delete_vault_entry,
    get_entry as get_vault_entry,
    get_vault_status,
    list_entries as list_vault_entries,
    lock_vault,
    route_copied_text,
    set_capture_all_text,
    set_idle_lock_minutes,
    unlock_vault,
)
from library_security import (
    LibraryEncryptionError,
    decrypt_media_file,
    decrypted_temp_file,
    encrypt_file_in_place,
    encrypt_media_file,
    is_encrypted_media,
    iter_decrypted_media,
    media_plaintext_size,
)


MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_VIDEO_CONVERSION_BYTES = 2 * 1024 * 1024 * 1024
MAX_HANDOFF_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
_VIDEO_CONVERSION_SLOTS = threading.BoundedSemaphore(2)
_HANDOFF_CAPACITY_LOCK = threading.Lock()
MAX_JSON_BODY_BYTES = 1024 * 1024
MAX_AVA_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_AVA_ATTACHMENT_TEXT_CHARS = 100_000
PUBLIC_UI_ASSETS = {
    "app.js",
    "ava-pet.js",
    "ava-attachments.js",
    "companions.js",
    "auth-providers.js",
    "finder-files.css",
    "finder-files.js",
    "settings.js",
    "qrcodegen.js",
    "vault.js",
    "shared.css",
    "shared.js",
    "stash-icon-192.png",
    "stash-icon-512.png",
    "stash-logo.svg",
    # STASH-SPLASH: standalone launch splash assets.
    "splash.css",
    "splash.js",
    "stash-sw.js",
    "stash.webmanifest",
    "style.css",
    # PETS-5: additive pet layer assets served by the existing UI route.
    "pet5.css",
    "pet5-engine.js",
    "pet5-components.js",
    "pet5.js",
}
def handle_video_upload_too_large(error):
    if request.path == "/api/ava/extract-attachment":
        return jsonify({
            "success": False,
            "message": "That attachment is too large. Choose a file under 20 MB.",
        }), 413
    if (
        request.path == "/api/browser-copy"
        and request.headers.get("X-Copy-Maker-Type") == "video"
    ):
        return jsonify({
            "success": False,
            "code": "video_too_large",
            "error": "This video is larger than Stash's 2 GB upload limit.",
        }), 413
    return error


_ROUTE_BLUEPRINTS = {
    "core": Blueprint("stash_core", __name__),
    "capture": Blueprint("stash_capture", __name__),
    "media": Blueprint("stash_media", __name__),
    "ava": Blueprint("stash_ava", __name__),
    "vault": Blueprint("stash_vault", __name__),
    "handoff": Blueprint("stash_handoff", __name__),
}


def _route_blueprint(path):
    if path.startswith(("/api/browser-copy", "/api/video-capture", "/api/clipboard")):
        return _ROUTE_BLUEPRINTS["capture"]
    if path.startswith(("/media/", "/videos/", "/api/videos/")):
        return _ROUTE_BLUEPRINTS["media"]
    if path.startswith("/api/ava"):
        return _ROUTE_BLUEPRINTS["ava"]
    if path.startswith("/api/vault"):
        return _ROUTE_BLUEPRINTS["vault"]
    if path.startswith(("/api/integrations", "/api/cloud-storage/prepare-for-app")):
        return _ROUTE_BLUEPRINTS["handoff"]
    return _ROUTE_BLUEPRINTS["core"]


def stash_route(path, *args, **kwargs):
    """Register a route on its domain blueprint without changing its URL."""
    return _route_blueprint(path).route(path, *args, **kwargs)


def _excluded_capture_site(page_url):
    if not isinstance(page_url, str) or not page_url.strip():
        return False
    try:
        hostname = (urlparse(page_url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if not hostname:
        return False
    return any(
        hostname == site or hostname.endswith("." + site)
        for site in get_privacy_settings().get("excluded_sites", [])
    )


def _excluded_capture_app(bundle_id):
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        return False
    excluded = {
        value.casefold()
        for value in get_privacy_settings().get("excluded_app_bundle_ids", [])
    }
    return bundle_id.strip().casefold() in excluded








_CAPTURE_REQUEST_PATHS = {
    "/api/browser-copy",
    "/api/browser-copy/import-audio-download",
    "/api/video-capture-start",
    "/api/clipboard/mobile",
    "/api/shared/extensions/browser-copy",
    "/api/shared/extensions/video-capture-start",
}
_RETENTION_LAST_CHECK = 0.0
_RETENTION_LOCK = threading.Lock()


def _maybe_purge_expired_items():
    global _RETENTION_LAST_CHECK
    now = time.monotonic()
    if now - _RETENTION_LAST_CHECK < 3600:
        return
    with _RETENTION_LOCK:
        now = time.monotonic()
        if now - _RETENTION_LAST_CHECK < 3600:
            return
        try:
            purge_expired_items()
            _RETENTION_LAST_CHECK = now
        except Exception as error:
            app.logger.warning("Could not apply Stash retention: %s", type(error).__name__)


def _privacy_maintenance_worker():
    _cleanup_expired_exports()
    while True:
        _maybe_purge_expired_items()
        _cleanup_expired_exports()
        time.sleep(60)


_privacy_worker = threading.Thread(
    target=_privacy_maintenance_worker,
    name="stash-privacy-maintenance",
    daemon=True,
)
_PRIVACY_WORKER_START_LOCK = threading.Lock()
_PRIVACY_WORKER_STARTED = False
_LOCAL_RUNTIME_LOCK = threading.Lock()
_LOCAL_RUNTIME_INITIALIZED = False


def _start_privacy_worker():
    global _PRIVACY_WORKER_STARTED
    with _PRIVACY_WORKER_START_LOCK:
        if _PRIVACY_WORKER_STARTED:
            return
        _privacy_worker.start()
        _PRIVACY_WORKER_STARTED = True


def _cleanup_expired_exports():
    base_dir = os.path.join(LOCAL_STORAGE_DIR, "integrations")
    lifetimes = {
        os.path.join(base_dir, "clipboard"): 20 * 60,
        os.path.join(base_dir, "handoff"): 60 * 60,
    }
    now = time.time()
    for root, lifetime in lifetimes.items():
        if not os.path.isdir(root):
            continue
        for current_root, _, filenames in os.walk(root):
            for filename in filenames:
                path = os.path.join(current_root, filename)
                try:
                    if now - os.path.getmtime(path) >= lifetime:
                        os.remove(path)
                except OSError:
                    pass


_BROWSER_VIDEO_COPY_SETTING_FILE = os.path.join(
    LOCAL_STORAGE_DIR,
    "browser_video_copy_setting.json",
)
_BROWSER_VIDEO_COPY_SETTING_LOCK = threading.RLock()


def _browser_video_copy_allowed():
    with _BROWSER_VIDEO_COPY_SETTING_LOCK:
        try:
            with open(_BROWSER_VIDEO_COPY_SETTING_FILE, "r", encoding="utf-8") as setting_file:
                settings = json.load(setting_file)
        except (OSError, ValueError):
            return False
        return isinstance(settings, dict) and settings.get("enabled") is True


def _set_browser_video_copy_allowed(enabled):
    storage_dir = os.path.dirname(_BROWSER_VIDEO_COPY_SETTING_FILE)
    os.makedirs(storage_dir, mode=0o700, exist_ok=True)
    with _BROWSER_VIDEO_COPY_SETTING_LOCK:
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".browser-video-copy-",
            suffix=".tmp",
            dir=storage_dir,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as setting_file:
                json.dump({"enabled": enabled}, setting_file)
                setting_file.flush()
                os.fsync(setting_file.fileno())
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, _BROWSER_VIDEO_COPY_SETTING_FILE)
        finally:
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass


@_ROUTE_BLUEPRINTS["core"].before_app_request
def require_copy_maker_login():
    remote_address = request.remote_addr or ""
    if (
        is_trusted_proxy_request()
        and (request.headers.get("X-Forwarded-Proto") or request.headers.get("CF-Visitor"))
        and not is_trusted_secure_proxy_request()
    ):
        return jsonify({"error": "Remote Stash access requires HTTPS through the configured proxy."}), 403
    if remote_address not in {"127.0.0.1", "::1"}:
        trusted_https_proxy = is_trusted_secure_proxy_request()
        try:
            client_ip = ipaddress.ip_address(remote_address)
        except ValueError:
            if not trusted_https_proxy:
                return jsonify({"error": "This Stash server accepts local Wi-Fi connections only. Remote access needs an allowlisted HTTPS proxy."}), 403
            client_ip = None
        private_networks = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        )
        if client_ip is not None and not any(client_ip.version == 4 and client_ip in network for network in private_networks) and not trusted_https_proxy:
            return jsonify({"error": "This Stash server accepts local Wi-Fi connections only. Remote access needs an allowlisted HTTPS proxy."}), 403

    if request.path in {"/health", "/healthz"}:
        return None
    try:
        initialize_local_runtime()
    except Exception:
        app.logger.exception("Stash could not initialize local storage")
        return jsonify({"error": "Stash could not initialize its encrypted storage."}), 503

    if request.method in {"POST", "PUT", "PATCH"}:
        is_backup_restore = request.path == "/api/security/backup/restore"
        is_binary_upload = (
            request.path == "/api/cloud-storage/upload"
            or request.path == "/api/ava/extract-attachment"
            or request.path in {
                "/api/shared/upload",
                "/api/shared/share",
                "/api/shared/extensions/browser-copy",
                "/api/security/backup/restore",
            }
            or (
                request.path == "/api/browser-copy"
                and request.headers.get("X-Copy-Maker-Type") in {"audio", "video"}
            )
        )
        body_limit = (
            MAX_AVA_ATTACHMENT_BYTES
            if request.path == "/api/ava/extract-attachment"
            else MAX_BACKUP_BYTES + 1024 * 1024 if is_backup_restore
            else MAX_UPLOAD_BYTES if is_binary_upload else MAX_JSON_BODY_BYTES
        )
        try:
            request.max_content_length = body_limit
        except AttributeError:
            if request.content_length is not None and request.content_length > body_limit:
                return jsonify({"error": "This request is larger than Stash allows."}), 413

    is_capture_request = (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.path in _CAPTURE_REQUEST_PATHS
    )
    if is_capture_request:
        settings = get_privacy_settings()
        if not settings["capture_enabled"]:
            return jsonify({
                "success": False,
                "error": "Stash capture is paused. Resume capture in Settings before saving new copies.",
            }), 423
        page_url = request.headers.get("X-Copy-Maker-Page", "")
        if not page_url and request.is_json:
            payload = request.get_json(silent=True)
            if isinstance(payload, dict):
                page_url = payload.get("page_url") or payload.get("pageUrl") or ""
        if _excluded_capture_site(page_url):
            return jsonify({
                "success": False,
                "error": "Capture is disabled for this website in Stash privacy settings.",
            }), 423

    public_paths = {
        "/",
        "/shared",
        "/api/auth/status",
        "/api/auth/signup",
        "/api/auth/login",
        "/api/auth/firebase-login",
        "/api/auth/logout",
        "/api/auth/two-factor/verify",
        "/api/auth/two-factor/cancel",
    }
    if request.path in public_paths or request.path.startswith("/ui/"):
        return None

    # Local extension pairing is authorized by a short-lived, one-use code.
    if is_local_extension_pair_request():
        return None

    # The shared service owns its own account checks. It stays disabled until
    # the public server explicitly sets COPY_MAKER_SHARED_MODE=1.
    if request.path.startswith("/api/shared/"):
        return None

    # The browser extension imports into the local app. Keep those routes
    # available on this Mac only; requests through a public hostname must log in.
    if is_local_extension_request():
        return None

    if request.method == "OPTIONS":
        return None

    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401

    if request.method not in {"GET", "HEAD", "OPTIONS"} and not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403

    _maybe_purge_expired_items()

    return None


@_ROUTE_BLUEPRINTS["core"].after_app_request
def lock_vault_after_sign_out(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.is_secure or is_trusted_secure_proxy_request():
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.path == "/api/auth/logout" and request.method == "POST":
        # The Vault key is process-wide for the local clipboard monitor. Clear
        # it whenever the owner signs out, including the clipboard monitor's process-wide key.
        try:
            lock_vault(force=True)
        except Exception as error:
            app.logger.warning("Could not lock Vault after sign-out: %s", type(error).__name__)
    return response












































































def _existing_video_match(existing_item, existing_path, incoming_hash):
    saved_hash = existing_item.get("source_sha256")
    has_saved_hash = isinstance(saved_hash, str) and re.fullmatch(r"[0-9a-fA-F]{64}", saved_hash)
    if has_saved_hash and saved_hash.lower() != incoming_hash:
        return False, None

    digest = hashlib.sha256()
    try:
        for chunk in iter_decrypted_media(existing_path):
            digest.update(chunk)
    except (OSError, LibraryEncryptionError) as error:
        app.logger.warning(
            "Skipping unreadable video during duplicate check: %s",
            type(error).__name__,
        )
        return False, None

    calculated_hash = digest.hexdigest()
    if has_saved_hash and calculated_hash == saved_hash.lower():
        return calculated_hash == incoming_hash, None
    return calculated_hash == incoming_hash, calculated_hash


def _save_request_body(destination):
    total_bytes = 0
    digest = hashlib.sha256()
    try:
        with open(destination, "xb") as output_file:
            while True:
                chunk = request.stream.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise OverflowError("Upload exceeds the Stash size limit.")
                digest.update(chunk)
                output_file.write(chunk)
        if total_bytes == 0:
            os.remove(destination)
        return total_bytes, digest.hexdigest()
    except Exception:
        try:
            if os.path.exists(destination):
                os.remove(destination)
        except OSError:
            pass
        raise


def _is_public_http_url(value):
    try:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or port not in (None, 80 if parsed.scheme.lower() == "http" else 443)
        or parsed.username is not None
        or parsed.password is not None
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal", ".lan"))
    ):
        return False
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0].split("%", 1)[0])
                for result in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


def _open_public_media_url(media_url, page_url):
    initial = urlparse(media_url)
    initial_host = (initial.hostname or "").lower()
    try:
        page = urlparse(page_url) if page_url else None
        if page:
            _ = page.port
    except (TypeError, ValueError):
        page = None
    referer = ""
    if (
        page
        and page.scheme in {"http", "https"}
        and page.username is None
        and page.password is None
        and (page.hostname or "").lower() == initial_host
        and page.port == initial.port
    ):
        referer_host = page.hostname
        if ":" in referer_host and not referer_host.startswith("["):
            referer_host = f"[{referer_host}]"
        referer_port = f":{page.port}" if page.port else ""
        referer = f"{page.scheme}://{referer_host}{referer_port}/"

    headers = {
        "User-Agent": "Stash/1.0 media import",
        "Accept": "video/*;q=0.9,application/octet-stream;q=0.8,*/*;q=0.5",
    }
    if referer:
        headers["Referer"] = referer

    current_url = media_url
    session = requests.Session()
    session.trust_env = False
    try:
        for _ in range(4):
            if not _is_public_http_url(current_url):
                raise ValueError("Only public HTTP or HTTPS media links can be downloaded.")
            response = session.get(
                current_url,
                headers=headers,
                stream=True,
                timeout=(10, 30),
                allow_redirects=False,
            )
            if response.is_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("The media link could not be opened.")
                current_url = urljoin(current_url, location)
                current = urlparse(current_url)
                if (
                    (current.hostname or "").lower() != initial_host
                    or current.port != initial.port
                ):
                    headers.pop("Referer", None)
                continue
            response.raise_for_status()
            return session, response
        raise ValueError("The media link redirected too many times.")
    except Exception:
        session.close()
        raise

last_content = None


def publish_video_file_to_clipboard(file_path, expected_change_count):

    global last_content

    temporary_exports = []
    temporary_export = None
    try:
        if is_encrypted_media(file_path):
            extension = os.path.splitext(file_path)[1]
            export_dir = os.path.join(LOCAL_STORAGE_DIR, "integrations", "clipboard")
            os.makedirs(export_dir, mode=0o700, exist_ok=True)
            try:
                os.chmod(export_dir, 0o700)
            except OSError:
                pass
            descriptor, temporary_export = tempfile.mkstemp(
                prefix="stash-clipboard-", suffix=extension, dir=export_dir
            )
            os.close(descriptor)
            temporary_exports.append(temporary_export)
            decrypt_media_file(file_path, temporary_export)
        clipboard_path = temporary_export or file_path

        # MediaRecorder fallback produces WebM. Put a broadly playable MP4 on
        # the system clipboard so pasting into QuickTime and chat apps works.
        if os.path.splitext(clipboard_path)[1].lower() == ".webm":
            if temporary_export is None:
                export_dir = os.path.join(LOCAL_STORAGE_DIR, "integrations", "clipboard")
                os.makedirs(export_dir, mode=0o700, exist_ok=True)
                descriptor, temporary_export = tempfile.mkstemp(
                    prefix="stash-clipboard-", suffix=".webm", dir=export_dir
                )
                os.close(descriptor)
                temporary_exports.append(temporary_export)
                shutil.copy2(file_path, temporary_export)
                clipboard_path = temporary_export
            converted_path, converted, conversion_error = convert_video_to_shareable_mp4(clipboard_path)
            if not converted or conversion_error or converted_path == clipboard_path:
                for path in temporary_exports:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                print("⚠️ Could not prepare a shareable MP4 for the clipboard:", conversion_error or "conversion failed")
                return False
            clipboard_path = converted_path
            temporary_exports.append(converted_path)

        published, new_change_count = set_file_on_system_clipboard(
            clipboard_path,
            expected_change_count
        )
    except Exception as error:
        for path in temporary_exports:
            try:
                os.remove(path)
            except OSError:
                pass
        print("⚠️ Could not publish video to macOS clipboard:", type(error).__name__)
        return False

    if not published:
        for path in temporary_exports:
            try:
                os.remove(path)
            except OSError:
                pass
        return False

    absolute_path = os.path.abspath(clipboard_path)
    last_content = (
        "file",
        new_change_count,
        (absolute_path,)
    )
    if temporary_exports:
        def remove_temporary_exports(paths=tuple(temporary_exports)):
            for path in paths:
                try:
                    os.remove(path)
                except OSError:
                    pass

        def schedule_temporary_cleanup():
            try:
                remove_temporary_exports()
            except OSError:
                pass

        cleanup = threading.Timer(20 * 60, schedule_temporary_cleanup)
        cleanup.daemon = True
        cleanup.start()

    print("📋 Saved video is now on the macOS clipboard")
    return True


def _encrypted_media_response(path, filename):
    size = media_plaintext_size(path)
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    range_header = request.headers.get("Range", "")
    start, end = 0, max(0, size - 1)
    status = 200
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or size == 0:
            return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        first, last = match.groups()
        if not first:
            suffix_length = int(last or 0)
            if suffix_length <= 0:
                return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
            start = max(0, size - suffix_length)
        else:
            start = int(first)
            end = min(size - 1, int(last)) if last else size - 1
        if start >= size or end < start:
            return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        status = 206
    response = Response(
        stream_with_context(iter_decrypted_media(path, start, end)),
        status=status,
        mimetype=mime_type,
        direct_passthrough=True,
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = str(end - start + 1 if size else 0)
    response.headers["Cache-Control"] = "private, no-store"
    if status == 206:
        response.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response


def convert_video_to_shareable_mp4(file_path):
    """Return an MP4 that uses codecs supported by QuickTime and common apps."""
    if (
        os.path.splitext(file_path)[1].lower() == ".mp4"
        and _is_quicktime_compatible_mp4(file_path)
    ):
        return file_path, False, None

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return file_path, False, "ffmpeg_not_found"

    conversion_dir = tempfile.mkdtemp(prefix=".stash-video-convert-")
    try:
        os.chmod(conversion_dir, 0o700)
    except OSError:
        pass
    output_path = os.path.join(conversion_dir, "shareable.mp4")
    temporary_path = os.path.join(conversion_dir, "converted.tmp.mp4")

    command = [
        ffmpeg_path,
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-i", file_path,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "1400k",
        "-maxrate", "1700k",
        "-bufsize", "3400k",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-fs", str(MAX_VIDEO_CONVERSION_BYTES),
        temporary_path,
    ]

    keep_conversion = False
    if not _VIDEO_CONVERSION_SLOTS.acquire(timeout=30):
        shutil.rmtree(conversion_dir, ignore_errors=True)
        return file_path, False, "conversion_busy"
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=600,
            check=False,
        )
        if result.returncode != 0 or not os.path.isfile(temporary_path):
            return file_path, False, "conversion_failed"
        if os.path.getsize(temporary_path) <= 0:
            return file_path, False, "conversion_failed"
        if os.path.getsize(temporary_path) >= MAX_VIDEO_CONVERSION_BYTES:
            return file_path, False, "conversion_too_large"

        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, output_path)
        keep_conversion = True
        return output_path, True, None
    except subprocess.TimeoutExpired:
        return file_path, False, "conversion_timed_out"
    except OSError:
        return file_path, False, "conversion_failed"
    finally:
        _VIDEO_CONVERSION_SLOTS.release()
        if not keep_conversion:
            shutil.rmtree(conversion_dir, ignore_errors=True)


def cleanup_video_conversion(path):
    if not path:
        return
    directory = os.path.dirname(os.path.abspath(path))
    if os.path.basename(directory).startswith(".stash-video-convert-"):
        shutil.rmtree(directory, ignore_errors=True)
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _handoff_directory_size(folder):
    total = 0
    for current_root, _, filenames in os.walk(folder):
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(current_root, filename))
            except OSError:
                continue
    return total


def _cleanup_stale_video_conversions():
    temporary_root = tempfile.gettempdir()
    now = time.time()
    try:
        entries = os.scandir(temporary_root)
    except OSError:
        return
    with entries:
        for entry in entries:
            if not entry.name.startswith(".stash-video-convert-"):
                continue
            try:
                if (
                    entry.is_dir(follow_symlinks=False)
                    and now - entry.stat(follow_symlinks=False).st_mtime >= 60 * 60
                ):
                    shutil.rmtree(entry.path, ignore_errors=True)
            except OSError:
                continue


def _is_quicktime_compatible_mp4(file_path):
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return False

    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "stream=codec_type,codec_name,pix_fmt",
                "-of", "json",
                file_path,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return False
        streams = json.loads(result.stdout).get("streams", [])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False

    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        return False
    video = video_streams[0]
    return (
        video.get("codec_name") == "h264"
        and video.get("pix_fmt") == "yuv420p"
        and all(stream.get("codec_name") == "aac" for stream in audio_streams)
    )


def get_video_duration_seconds(file_path):
    """Read a video duration with ffprobe or ffmpeg, when either is installed."""
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        try:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=15,
                check=False,
            )
            duration = float(result.stdout.strip())
            if result.returncode == 0 and duration > 0 and math.isfinite(duration):
                return duration
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return None
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-i", file_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        match = re.search(
            r"\bDuration:\s*(\d+):(\d+):([\d.]+)",
            result.stderr or "",
        )
        if not match:
            return None
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return duration if duration > 0 and math.isfinite(duration) else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# ==========================================
# BIN NOTIFICATIONS AND SCHEDULE
# ==========================================

stash_notifications = []
notification_lock = threading.Lock()
_bin_lock = threading.RLock()
_bin_settings_file = os.path.join(LOCAL_STORAGE_DIR, "bin_settings.json")


def get_bin_settings():
    try:
        with open(_bin_settings_file, "r", encoding="utf-8") as file:
            saved = json.load(file)
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    empty_at = saved.get("empty_at")
    if isinstance(empty_at, str):
        try:
            datetime.fromisoformat(empty_at.replace("Z", "+00:00"))
        except ValueError:
            empty_at = None
    else:
        empty_at = None
    return {
        "empty_at": empty_at,
        "reminder_sent_for": saved.get("reminder_sent_for") if isinstance(saved.get("reminder_sent_for"), str) else None,
        "review_notified_for": saved.get("review_notified_for") if isinstance(saved.get("review_notified_for"), str) else None,
    }


def save_bin_settings(settings):
    directory = os.path.dirname(_bin_settings_file)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".bin-settings-", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(settings, file)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, _bin_settings_file)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass


def enqueue_bin_notification(message):
    notification = {
        "id": int(time.time() * 1000),
        "message": message,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with notification_lock:
        stash_notifications.append(notification)
    try:
        subprocess.Popen([
            "osascript", "-e",
            'display notification "Check the Stash Bin before its scheduled empty date." with title "Stash"',
        ])
    except Exception:
        pass


def enqueue_ava_followup_notification(follow_up):
    title = str(follow_up.get("sourceTitle") or "saved item")[:160]
    label = str(follow_up.get("eventLabel") or "follow-up")[:100]
    notification = {
        "id": int(time.time() * 1000),
        "message": f"Ava reminder: {label} for {title} is due. Open Stash to review it.",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with notification_lock:
        stash_notifications.append(notification)
    try:
        subprocess.Popen([
            "osascript", "-e",
            'display notification "An Ava follow-up reminder is due. Open Stash to review it." with title "Stash"',
        ])
    except Exception:
        pass


def get_bin_items():
    return [item for item in load_items() if isinstance(item, dict) and item.get("trashed_at")]


def normalize_bin_item_ids(data):
    raw_ids = data.get("item_ids") if isinstance(data, dict) else None
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("Choose at least one copy.")
    normalized = []
    for value in raw_ids:
        try:
            item_id = int(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("One or more selected copies are invalid.")
        if item_id not in normalized:
            normalized.append(item_id)
    return normalized


def empty_bin_now():
    deleted = []
    for item in get_bin_items():
        result = delete_item(item.get("id"))
        if result:
            deleted.append(result)
    settings = get_bin_settings()
    settings["empty_at"] = None
    settings["reminder_sent_for"] = None
    settings["review_notified_for"] = None
    save_bin_settings(settings)
    return deleted


def bin_empty_worker():

    print("🗑 Bin empty scheduler: ON")

    while True:

        try:

            now = time.time()

            import mobile_companion_state
            for follow_up in mobile_companion_state.pop_due_follow_ups():
                enqueue_ava_followup_notification(follow_up)

            with _bin_lock:
                bin_settings = get_bin_settings()
                empty_at = bin_settings.get("empty_at")
                if empty_at:
                    try:
                        scheduled_bin_empty = datetime.fromisoformat(
                            empty_at.replace("Z", "+00:00")
                        ).timestamp()
                    except (TypeError, ValueError, OverflowError):
                        scheduled_bin_empty = None

                    if (
                        scheduled_bin_empty is not None
                        and now >= scheduled_bin_empty
                        and bin_settings.get("review_notified_for") != empty_at
                    ):
                        enqueue_bin_notification(
                            "Your Stash Bin review is ready. Open the Bin to restore items or empty it yourself. Nothing was deleted."
                        )
                        bin_settings["review_notified_for"] = empty_at
                        bin_settings["empty_at"] = None
                        save_bin_settings(bin_settings)
                    elif (
                        scheduled_bin_empty is not None
                        and 0 < scheduled_bin_empty - now <= 24 * 60 * 60
                        and bin_settings.get("reminder_sent_for") != empty_at
                    ):
                        enqueue_bin_notification(
                            f"Your Stash Bin review is coming up on {empty_at}. Stash will not delete anything automatically."
                        )
                        bin_settings["reminder_sent_for"] = empty_at
                        save_bin_settings(bin_settings)

        except Exception as error:

            print(
                "⚠️ Bin scheduler error:",
                type(error).__name__
            )

        time.sleep(2)



































































































@_ROUTE_BLUEPRINTS["core"].after_app_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    if request.is_secure or is_trusted_secure_proxy_request():
        response.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
    if request.path.startswith(("/api/", "/media/", "/videos/")):
        response.headers["Cache-Control"] = "no-store"
    return response

















# ==========================================
# STASH UI
# ==========================================






























































































































































































































































































































































































































































































# ==========================================
# AVA AI API
# ==========================================




































_AVA_TEXT_ATTACHMENT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".log",
    ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css",
    ".scss", ".less", ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".kt",
    ".swift", ".go", ".rs", ".rb", ".php", ".sh", ".zsh", ".bash", ".sql",
    ".vue", ".svelte", ".ipynb", ".makefile", ".dockerfile",
}
_AVA_SENSITIVE_ATTACHMENT_NAMES = {
    ".env", ".env.local", ".env.production", "credentials", "secrets",
}


def _extract_ava_attachment_text(filename, file_bytes):
    suffix = os.path.splitext(filename.lower())[1]
    base_name = os.path.basename(filename).lower()
    if base_name in _AVA_SENSITIVE_ATTACHMENT_NAMES or base_name.endswith((".pem", ".key", ".p12", ".pfx")):
        raise ValueError("This file may contain credentials or key material, so Stash will not send it to Ava.")

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("PDF reading is unavailable. Install Stash's listed PDF support and try again.") from error
        reader = PdfReader(io.BytesIO(file_bytes), strict=False)
        if reader.is_encrypted:
            raise ValueError("This PDF is password-protected. Unlock it and choose an unprotected copy.")
        pieces = []
        remaining = MAX_AVA_ATTACHMENT_TEXT_CHARS
        try:
            for page in reader.pages[:250]:
                text = page.extract_text() or ""
                piece = text[:remaining]
                pieces.append(piece)
                remaining -= len(piece)
                if remaining <= 0:
                    break
        except Exception as error:
            raise ValueError("Stash could not read text from this PDF. It may be damaged or image-only.") from error
        extracted = "\n".join(pieces).strip()
        if not extracted:
            raise ValueError("This PDF has no selectable text. Ava can still use its file name and size as context.")
        return extracted, len(extracted) >= MAX_AVA_ATTACHMENT_TEXT_CHARS

    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > 32 * 1024 * 1024:
                    raise ValueError("This document expands too large to read safely.")
                root = ET.fromstring(archive.read(info))
        except (KeyError, zipfile.BadZipFile, ET.ParseError, OSError) as error:
            raise ValueError("Stash could not read this Word document. Try saving a fresh .docx copy.") from error
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(f"{namespace}p"):
            line = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
            if line:
                paragraphs.append(line)
        extracted = "\n".join(paragraphs)[:MAX_AVA_ATTACHMENT_TEXT_CHARS].strip()
        if not extracted:
            raise ValueError("This Word document contains no readable text.")
        return extracted, len(extracted) >= MAX_AVA_ATTACHMENT_TEXT_CHARS

    if suffix not in _AVA_TEXT_ATTACHMENT_EXTENSIONS:
        raise ValueError("Ava can read text, code, PDF, and Word files. For images or video, attach them for file details only.")
    try:
        extracted = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("This file does not look like readable UTF-8 text or code.") from error
    return extracted[:MAX_AVA_ATTACHMENT_TEXT_CHARS], len(extracted) > MAX_AVA_ATTACHMENT_TEXT_CHARS













































































































































































































# ==========================================
# BROWSER COPY API
# ==========================================














































































































































































































































































































































































































































































































































































































































































































































































































































































































# ==========================================
# CLIPBOARD LIBRARY API
# ==========================================























































































































































































































































































































































































# ==========================================





















# ==========================================







































































# START FLASK SERVER
# ==========================================

def start_server():
    initialize_local_runtime()
    from device_transfer_receiver import start_device_transfer_receiver

    start_device_transfer_receiver()
    app.run(
        host="0.0.0.0",
        port=5050,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def initialize_local_runtime():
    """Initialize auth, encrypted storage, and maintenance before serving a request."""
    global _LOCAL_RUNTIME_INITIALIZED
    with _LOCAL_RUNTIME_LOCK:
        if _LOCAL_RUNTIME_INITIALIZED:
            return
        apply_pending_restore()
        initialize_auth(app)
        if shared_service_enabled():
            initialize_shared_service(app)
        ensure_encrypted_media_storage()
        _cleanup_stale_video_conversions()
        canceled_schedules = clear_legacy_auto_delete_schedules()
        if canceled_schedules:
            app.logger.info(
                "Canceled %s retired per-copy deletion schedules; kept the copies.",
                canceled_schedules,
            )
        if os.environ.get("STASH_DISABLE_BACKGROUND_WORKERS") != "1":
            _start_privacy_worker()
        _LOCAL_RUNTIME_INITIALIZED = True


def _clipboard_identity(content):
    if not isinstance(content, dict):
        return None
    content_type = content.get("type")
    change_count = content.get("change_count")
    if content_type == "text":
        content_hash = hashlib.sha256(str(content.get("content") or "").encode("utf-8")).hexdigest()
        return (content_type, change_count, content_hash)
    if content_type in {"image", "audio"}:
        raw_bytes = content.get("raw_bytes") or b""
        return (content_type, change_count, hashlib.sha256(raw_bytes).hexdigest())
    if content_type == "file":
        return (content_type, change_count, tuple(content.get("files") or ()))
    return (content_type, change_count)


def clipboard_monitor():
    global last_content

    print("================================")
    print("       STASH")
    print("================================")
    print("Local server: http://127.0.0.1:5050")
    print("Clipboard monitoring: ON")
    print("Browser media API: ON")
    print("--------------------------------")


    # ==========================================
    # CLIPBOARD MONITOR
    # ==========================================

    while True:

        try:

            content = get_clipboard_content()

            if not get_privacy_settings()["capture_enabled"]:
                # Remember the current clipboard state while paused so copies
                # made during the pause are not silently imported on resume.
                last_content = _clipboard_identity(content)
                if isinstance(content, dict) and content.get("type") == "text":
                    content["content"] = ""
                time.sleep(0.5)
                continue

            frontmost_app = get_frontmost_app_bundle_id()
            if _excluded_capture_app(frontmost_app):
                last_content = _clipboard_identity(content)
                if isinstance(content, dict) and content.get("type") == "text":
                    content["content"] = ""
                time.sleep(0.5)
                continue

            if content:

                # -------------------------
                # TEXT
                # -------------------------

                if content["type"] == "text":

                    current = (
                        content["type"],
                        content["change_count"],
                        hashlib.sha256(content["content"].encode("utf-8")).hexdigest(),
                    )

                    if current != last_content:

                        destination = route_copied_text(
                            content["content"],
                            source="desktop clipboard",
                        )
                        if destination == "library":
                            print("\n📋 TEXT COPIED")
                            print("----------------")
                            print("Saved copied text to Stash (content hidden in logs).")
                            save_item("text", content["content"])
                        elif destination == "vault":
                            print("\n🔒 Sensitive text saved to the encrypted Vault.")
                        else:
                            content["content"] = ""
                            print("\n🔒 Sensitive text was discarded because the Vault is locked or unavailable.")

                        last_content = current


                # -------------------------
                # IMAGE
                # -------------------------

                elif content["type"] == "image":

                    current = (
                        content["type"],
                        content["change_count"],
                        hashlib.sha256(
                            content["raw_bytes"]
                        ).hexdigest()
                    )

                    if current != last_content:

                        print("\n🖼️ IMAGE COPIED")
                        print("----------------")
                        print(
                            "Size:",
                            len(content["raw_bytes"]),
                            "bytes"
                        )

                        print(
                            "Format:",
                            content["format"]
                        )

                        print(
                            "Resolution:",
                            content["content"].size
                        )

                        extension = ".png"

                        if content["format"]:
                            fmt = str(content["format"]).lower()

                            if "jpeg" in fmt or "jpg" in fmt:
                                extension = ".jpg"

                            elif "tiff" in fmt:
                                extension = ".tiff"

                        saved = save_bytes(
                            "image",
                            content["raw_bytes"],
                            extension
                        )

                        print("Saved image to Stash (path hidden in logs).")

                        last_content = current


                # -------------------------
                # AUDIO
                # -------------------------

                elif content["type"] == "audio":

                    current = (
                        content["type"],
                        content["change_count"],
                        hashlib.sha256(
                            content["raw_bytes"]
                        ).hexdigest()
                    )

                    if current != last_content:

                        print("\n🎵 AUDIO COPIED")
                        print("----------------")
                        print(
                            "Size:",
                            len(content["raw_bytes"]),
                            "bytes"
                        )

                        audio_type = str(
                            content.get("format", "")
                        ).lower()

                        extension = ".audio"

                        if "mp3" in audio_type:
                            extension = ".mp3"

                        elif "mpeg-4" in audio_type or "m4a" in audio_type:
                            extension = ".m4a"

                        elif "wav" in audio_type:
                            extension = ".wav"

                        saved = save_bytes(
                            "audio",
                            content["raw_bytes"],
                            extension
                        )

                        print("Saved audio to Stash (path hidden in logs).")

                        last_content = current


                # -------------------------
                # FILE
                # -------------------------

                elif content["type"] == "file":

                    current = (
                        content["type"],
                        content["change_count"],
                        tuple(content["files"])
                    )

                    if current != last_content:

                        print("\n📁 FILE COPIED")
                        print("----------------")

                        for file_path in content["files"]:

                            print("File copied to Stash (source path hidden in logs).")

                            extension = file_path.lower()

                            if extension.endswith((
                                ".mp4",
                                ".mov",
                                ".m4v",
                                ".avi",
                                ".mkv",
                                ".webm"
                            )):

                                print("🎬 VIDEO DETECTED")

                                saved = save_file(
                                    "video",
                                    file_path
                                )

                                print("Saved video to Stash (path hidden in logs).")

                            else:

                                saved = save_file(
                                    "file",
                                    file_path
                                )

                                print("Saved file to Stash (path hidden in logs).")

                        last_content = current


        except Exception as error:

            print(
                "\n⚠️ Clipboard error:",
                type(error).__name__
            )

        time.sleep(0.5)


# ==========================================
# AVA ARRANGE CONFIRMATION API
# ==========================================































def _export_route_functions(route_module):
    for route_name, route_handler in vars(route_module).items():
        if getattr(route_handler, "__module__", None) == route_module.__name__:
            globals()[route_name] = route_handler


from routes import media as _media_routes
from routes import handoff as _handoff_routes
from routes import vault as _vault_routes
from routes import ava as _ava_routes
from routes import capture as _capture_routes
from routes import core as _core_routes
from routes import device_transfer as _device_transfer_routes
from routes import mobile_companion as _mobile_companion_routes
from routes import security as _security_routes

_export_route_functions(_media_routes)
_export_route_functions(_handoff_routes)
_export_route_functions(_vault_routes)
_export_route_functions(_ava_routes)
_export_route_functions(_capture_routes)
_export_route_functions(_core_routes)
_export_route_functions(_device_transfer_routes)
_export_route_functions(_mobile_companion_routes)
_export_route_functions(_security_routes)


def create_app(config=None):
    """Build the local Stash Flask app and mount route-domain blueprints."""
    flask_app = Flask(__name__)
    flask_app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    if config:
        flask_app.config.update(config)
    flask_app.register_blueprint(auth_blueprint)
    flask_app.register_blueprint(shared_blueprint)
    for blueprint in _ROUTE_BLUEPRINTS.values():
        flask_app.register_blueprint(blueprint)
    flask_app.register_error_handler(413, handle_video_upload_too_large)
    return flask_app


app = create_app()


if __name__ == "__main__":
    try:
        initialize_local_runtime()
    except Exception as error:
        raise SystemExit(
            "Stash startup failed while preparing local storage. "
            f"Check the configured Python dependencies and macOS Keychain access: {error}"
        ) from error

    if os.environ.get("STASH_DISABLE_CLIPBOARD_MONITOR") != "1":
        threading.Thread(target=clipboard_monitor, name="stash-clipboard-monitor", daemon=True).start()
    if os.environ.get("STASH_DISABLE_BACKGROUND_WORKERS") != "1":
        threading.Thread(target=bin_empty_worker, name="stash-bin-maintenance", daemon=True).start()
    start_server()
