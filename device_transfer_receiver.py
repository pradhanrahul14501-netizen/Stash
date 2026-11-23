"""A small LAN-only receiver for one-time Stash copy transfers."""

import base64
import json
import os
import sys
import threading
import tempfile

from flask import Flask, jsonify, request
from werkzeug.serving import make_server
from werkzeug.utils import secure_filename

import device_transfer_state
import mobile_companion_state
from storage_manager import save_file, save_item, update_item


TRANSFER_PORT = 5052
MAX_ITEM_BYTES = 2 * 1024 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
_ALLOWED_TYPES = {"image", "audio", "video", "file", "text"}
_ALLOWED_METADATA_FIELDS = {
    "title",
    "url",
    "source_url",
    "page_url",
    "mime_type",
    "created_at",
    "folder",
    "duration",
}

receiver_app = Flask("stash_device_transfer_receiver")
receiver_app.config["MAX_CONTENT_LENGTH"] = MAX_ITEM_BYTES
_RFC1918_NETWORKS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
)


def _private_lan_request():
    try:
        import ipaddress

        address = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return (
        address.version == 4
        and any(address in ipaddress.ip_network(network) for network in _RFC1918_NETWORKS)
    )


@receiver_app.before_request
def restrict_receiver_to_private_lan():
    if not _private_lan_request():
        return jsonify({"error": "Stash transfers are available only to devices on a private Wi-Fi network."}), 403


@receiver_app.errorhandler(413)
def upload_too_large(_error):
    return jsonify({"error": "This copy is larger than Stash's 2 GB transfer limit."}), 413


@receiver_app.get("/healthz")
def receiver_health():
    return jsonify({"status": "ok", "service": "stash-device-transfer"})


@receiver_app.post("/device-transfer/start")
def start_transfer():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "The transfer details are invalid."}), 400
    try:
        token = device_transfer_state.begin_transfer(
            payload.get("code"),
            payload.get("item_count"),
            payload.get("total_bytes"),
            request.remote_addr,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"success": True, "transfer_token": token})


def _item_metadata():
    encoded = request.headers.get("X-Stash-Item-Metadata", "")
    if not encoded or len(encoded) > 32_000:
        return None
    try:
        raw = base64.b64decode(encoded, altchars=b"-_", validate=True)
        metadata = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(metadata, dict):
        return None
    return metadata


def _safe_metadata_fields(metadata):
    fields = {}
    for key in _ALLOWED_METADATA_FIELDS:
        value = metadata.get(key)
        if isinstance(value, str):
            fields[key] = value[:4000]
        elif key == "duration" and isinstance(value, (int, float)):
            fields[key] = value
    original_name = metadata.get("filename")
    if isinstance(original_name, str):
        fields["original_name"] = os.path.basename(original_name)[:240]
    return fields


@receiver_app.post("/device-transfer/item")
def receive_item():
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    metadata = _item_metadata()
    if not metadata or metadata.get("type") not in _ALLOWED_TYPES:
        return jsonify({"error": "Stash could not read this copy's details."}), 400
    content_length = request.content_length
    if content_length is None or content_length < 0 or content_length > MAX_ITEM_BYTES:
        return jsonify({"error": "Stash could not read the copy size."}), 413
    if not device_transfer_state.authorize_transfer(token, content_length):
        return jsonify({"error": "This transfer expired. Create a new code on the receiving laptop."}), 401

    item_type = metadata["type"]
    if metadata.get("kind") == "text" and item_type == "text":
        if content_length > MAX_TEXT_BYTES:
            return jsonify({"error": "This text copy is larger than Stash allows."}), 413
        raw = request.get_data(cache=False)
        if len(raw) != content_length:
            return jsonify({"error": "The copy did not arrive completely."}), 400
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "Stash could not read this text copy."}), 400
        saved = save_item("text", content)
        fields = _safe_metadata_fields(metadata)
        if fields:
            update_item(saved["id"], fields)
        if not device_transfer_state.record_received_item(token, len(raw)):
            return jsonify({"error": "The transfer session is no longer active."}), 401
        return jsonify({"success": True, "type": "text"})

    if metadata.get("kind") != "file" or item_type == "text":
        return jsonify({"error": "This copy could not be transferred."}), 400
    filename = secure_filename(os.path.basename(str(metadata.get("filename") or ""))) or f"stash-copy.{item_type}"
    extension = os.path.splitext(filename)[1][:20]
    descriptor, temporary_path = tempfile.mkstemp(prefix=".stash-incoming-", suffix=extension)
    received_bytes = 0
    try:
        with os.fdopen(descriptor, "wb") as destination:
            while True:
                chunk = request.stream.read(1024 * 1024)
                if not chunk:
                    break
                received_bytes += len(chunk)
                if received_bytes > content_length or received_bytes > MAX_ITEM_BYTES:
                    return jsonify({"error": "This copy exceeded its declared size."}), 413
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if received_bytes != content_length:
            return jsonify({"error": "The video or file did not arrive completely."}), 400
        saved = save_file(item_type, temporary_path)
        fields = _safe_metadata_fields(metadata)
        if fields:
            update_item(saved["id"], fields)
        if not device_transfer_state.record_received_item(token, received_bytes):
            return jsonify({"error": "The transfer session is no longer active."}), 401
        return jsonify({"success": True, "type": item_type})
    finally:
        try:
            os.remove(temporary_path)
        except OSError:
            pass


@receiver_app.post("/device-transfer/finish")
def finish_transfer():
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not device_transfer_state.finish_transfer(token):
        return jsonify({"error": "The transfer did not finish completely. Check the sending Stash and try again."}), 400
    return jsonify({"success": True})


def _mobile_token():
    authorization = request.headers.get("Authorization", "")
    return authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""


def _require_mobile_pairing():
    if not mobile_companion_state.is_authorized(_mobile_token()):
        return jsonify({"error": "Connect this phone again from desktop Stash Settings."}), 401
    return None


@receiver_app.post("/mobile-companion/pair")
def pair_mobile_companion():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Enter the one-time code shown in desktop Stash Settings."}), 400
    try:
        token = mobile_companion_state.exchange_pair_code(payload.get("code"), request.remote_addr)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"success": True, "token": token})


@receiver_app.get("/mobile-companion/actions")
def mobile_companion_actions():
    denied = _require_mobile_pairing()
    if denied:
        return denied
    return jsonify({"success": True, "actions": mobile_companion_state.list_actions()})


@receiver_app.get("/mobile-companion/actions/<action_id>")
def get_mobile_companion_action_status(action_id):
    denied = _require_mobile_pairing()
    if denied:
        return denied
    result = mobile_companion_state.action_status(action_id)
    if not result:
        return jsonify({"error": "This Ava preview expired."}), 404
    return jsonify({"success": True, **result})


@receiver_app.post("/mobile-companion/actions/<action_id>/decision")
def decide_mobile_companion_action(action_id):
    denied = _require_mobile_pairing()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    decision = payload.get("decision") if isinstance(payload, dict) else None
    result = mobile_companion_state.decide_action(action_id, decision)
    if not result:
        return jsonify({"error": "This preview expired or was already handled on desktop Stash."}), 409
    if decision == "approved":
        confirmation_token = mobile_companion_state.claim_approved_action(action_id)
        if not confirmation_token:
            mobile_companion_state.finish_action(action_id, False, "This preview expired before desktop Stash could run it.")
            return jsonify({"error": "This preview expired before desktop Stash could run it."}), 409
        threading.Thread(
            target=_execute_mobile_approved_action,
            args=(action_id, confirmation_token),
            name="stash-mobile-approved-action",
            daemon=True,
        ).start()
        result["status"] = "executing"
    return jsonify({"success": True, **result})


def _execute_mobile_approved_action(action_id, confirmation_token):
    try:
        app_module = sys.modules.get("main") or sys.modules.get("__main__")
        executor = getattr(app_module, "_execute_pending_file_action", None)
        if not callable(executor):
            mobile_companion_state.finish_action(
                action_id,
                False,
                "Desktop Stash could not find the action runner. Ask Ava to preview it again.",
            )
            return
        result, status = executor(confirmation_token)
        success = status < 400 and result.get("success") is not False
        message = result.get("message") or (
            "The approved action is complete." if success else "Desktop Stash could not complete the approved action."
        )
        mobile_companion_state.finish_action(action_id, success, message)
    except Exception:
        mobile_companion_state.finish_action(
            action_id,
            False,
            "Desktop Stash could not complete the approved action. Ask Ava to preview it again.",
        )


@receiver_app.get("/mobile-companion/follow-ups")
def get_mobile_companion_follow_ups():
    denied = _require_mobile_pairing()
    if denied:
        return denied
    return jsonify({"success": True, "follow_ups": mobile_companion_state.get_follow_ups()})


@receiver_app.put("/mobile-companion/follow-ups")
def sync_mobile_companion_follow_ups():
    denied = _require_mobile_pairing()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    values = payload.get("follow_ups") if isinstance(payload, dict) else None
    try:
        merged = mobile_companion_state.merge_follow_ups(values)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"success": True, "follow_ups": merged})


@receiver_app.post("/mobile-companion/unpair")
def unpair_mobile_companion():
    if not mobile_companion_state.unpair(_mobile_token()):
        return jsonify({"error": "This phone is no longer paired."}), 401
    return jsonify({"success": True})


def start_device_transfer_receiver():
    try:
        server = make_server("0.0.0.0", TRANSFER_PORT, receiver_app, threaded=True)
    except OSError as error:
        device_transfer_state.set_receiver_status(False, "Stash's transfer listener could not start on port 5052.")
        print(f"Stash device transfer listener could not start: {type(error).__name__}")
        return None
    device_transfer_state.set_receiver_status(True)

    def serve():
        try:
            server.serve_forever()
        finally:
            server.server_close()

    import threading

    threading.Thread(target=serve, name="stash-device-transfer", daemon=True).start()
    print(f"Stash device transfer receiver: port {TRANSFER_PORT} (private LAN only)")
    return server
