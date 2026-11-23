"""One-time local-network transfer routes for selected Stash copies."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())

import base64
import ipaddress
import json
import os
import socket
import threading
from urllib.parse import urlsplit

import device_transfer_state


TRANSFER_PORT = 5052
MAX_TRANSFER_ITEM_BYTES = 2 * 1024 * 1024 * 1024
MAX_TRANSFER_ITEMS = 100
MAX_TRANSFER_BYTES = 4 * 1024 * 1024 * 1024
_TRANSFERABLE_FILE_TYPES = {"image", "audio", "video", "file"}
_TRANSFERABLE_FIELDS = {
    "title",
    "url",
    "source_url",
    "page_url",
    "mime_type",
    "created_at",
    "folder",
    "duration",
}
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def _private_lan_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if (
        address.version != 4
        or not any(address in network for network in _RFC1918_NETWORKS)
    ):
        return None
    return address


def _receiver_addresses():
    addresses = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            address = _private_lan_address(info[4][0])
            if address:
                addresses.add(str(address))
    except OSError:
        pass
    preferred_address = None
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        address = _private_lan_address(probe.getsockname()[0])
        if address:
            preferred_address = str(address)
            addresses.add(preferred_address)
    except OSError:
        pass
    finally:
        probe.close()
    return ([preferred_address] if preferred_address else []) + sorted(addresses - {preferred_address})


@stash_route("/api/local-network/addresses", methods=["GET"])
def get_local_network_addresses():
    addresses = _receiver_addresses()
    if not addresses:
        return jsonify({
            "error": "Connect this Mac to Wi-Fi, then refresh to create the phone link.",
        }), 503
    urls = [f"http://{address}:5050/" for address in addresses]
    return jsonify({"success": True, "url": urls[0], "urls": urls})


def _validated_receiver_url(value):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError("Enter the receiving laptop's address shown in Stash Settings.")
    try:
        parts = urlsplit(value.strip())
        address = _private_lan_address(parts.hostname or "")
        port = parts.port
    except ValueError as error:
        raise ValueError("Enter the receiving laptop's address shown in Stash Settings.") from error
    if (
        parts.scheme.lower() != "http"
        or address is None
        or port != TRANSFER_PORT
        or parts.username
        or parts.password
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Use the private Wi-Fi address and port shown on the receiving laptop.")
    return f"http://{address}:{TRANSFER_PORT}"


def _transferable_items(item_ids):
    if not isinstance(item_ids, list) or not item_ids or len(item_ids) > MAX_TRANSFER_ITEMS:
        raise ValueError(f"Select between 1 and {MAX_TRANSFER_ITEMS} copies to send.")
    normalized_ids = []
    for value in item_ids:
        try:
            item_id = int(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("One or more selected copies are invalid.") from error
        if item_id not in normalized_ids:
            normalized_ids.append(item_id)

    available = {
        int(item["id"]): item
        for item in load_items()
        if isinstance(item, dict)
        and item.get("id") is not None
        and not item.get("trashed_at")
        and not item.get("capture_status")
    }
    selected = []
    total_bytes = 0
    base_dir = os.path.realpath(os.path.dirname(__file__))
    allowed_roots = [
        os.path.realpath(os.path.join(LOCAL_STORAGE_DIR, folder))
        for folder in ("media", "videos", "shared_media")
    ]

    for item_id in normalized_ids:
        item = available.get(item_id)
        if not item:
            raise ValueError("A selected copy is no longer available in this Stash.")
        item_type = item.get("type")
        file_value = item.get("file")
        if isinstance(file_value, str) and file_value.strip():
            source_path = file_value if os.path.isabs(file_value) else os.path.join(base_dir, file_value)
            source_path = os.path.realpath(source_path)
            try:
                allowed = any(
                    os.path.commonpath((root, source_path)) == root and source_path != root
                    for root in allowed_roots
                )
            except ValueError:
                allowed = False
            if not allowed or not os.path.isfile(source_path):
                raise ValueError("A selected file is outside the Stash library or is no longer available.")
            if item_type not in _TRANSFERABLE_FILE_TYPES:
                raise ValueError("Stash cannot transfer this file type yet.")
            size = media_plaintext_size(source_path)
            if size > MAX_TRANSFER_ITEM_BYTES:
                raise ValueError("A selected file is larger than Stash's 2 GB transfer limit.")
            item_copy = dict(item)
            item_copy["_transfer_path"] = source_path
            item_copy["_transfer_size"] = size
        elif item_type == "text":
            content = item.get("content", item.get("text", item.get("value", "")))
            if not isinstance(content, str):
                content = str(content or "")
            raw = content.encode("utf-8")
            if len(raw) > 1024 * 1024:
                raise ValueError("A selected text copy is larger than Stash allows.")
            item_copy = dict(item)
            item_copy["_transfer_text"] = content
            item_copy["_transfer_size"] = len(raw)
        else:
            raise ValueError("Stash can transfer saved text, images, audio, video, and files.")

        total_bytes += item_copy["_transfer_size"]
        if total_bytes > MAX_TRANSFER_BYTES:
            raise ValueError("This selection is larger than Stash's 4 GB transfer limit.")
        selected.append(item_copy)

    return selected, total_bytes


def _metadata_for_item(item):
    item_type = item.get("type")
    filename = os.path.basename(str(
        item.get("original_name")
        or item.get("filename")
        or (item.get("_transfer_path") and os.path.basename(item["_transfer_path"]))
        or f"stash-{item_type}"
    ))[:240]
    metadata = {
        "kind": "text" if "_transfer_text" in item else "file",
        "type": item_type,
        "filename": filename,
        "fields": {},
    }
    for key in _TRANSFERABLE_FIELDS:
        value = item.get(key)
        if isinstance(value, (str, int, float)):
            if isinstance(value, str):
                max_chars = 1200 if key in {"url", "source_url", "page_url"} else 400
                metadata["fields"][key] = value[:max_chars]
            else:
                metadata["fields"][key] = value
    return base64.urlsafe_b64encode(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def _send_transfer(job_id, items, total_bytes, receiver_url, code):
    transfer_token = ""
    try:
        response = requests.post(
            receiver_url + "/device-transfer/start",
            json={"code": code, "item_count": len(items), "total_bytes": total_bytes},
            timeout=15,
            allow_redirects=False,
        )
        result = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else {}
        if not response.ok or not result.get("transfer_token"):
            raise ValueError(result.get("error") or "The receiving laptop did not accept this code.")
        transfer_token = result["transfer_token"]

        sent_bytes = 0
        for index, item in enumerate(items, start=1):
            filename = os.path.basename(str(
                item.get("original_name")
                or item.get("filename")
                or (item.get("_transfer_path") and os.path.basename(item["_transfer_path"]))
                or f"Stash {item.get('type', 'copy')}"
            ))
            device_transfer_state.update_send_job(
                job_id,
                status="sending",
                current_name=filename,
                completed_items=index - 1,
                sent_bytes=sent_bytes,
                message=f"Sending {index} of {len(items)}: {filename}",
            )
            headers = {
                "Authorization": "Bearer " + transfer_token,
                "X-Stash-Item-Metadata": _metadata_for_item(item),
                "Content-Type": "application/octet-stream",
                "Content-Length": str(item["_transfer_size"]),
            }

            if "_transfer_text" in item:
                raw = item["_transfer_text"].encode("utf-8")
                response = requests.post(
                    receiver_url + "/device-transfer/item",
                    data=raw,
                    headers=headers,
                    timeout=60,
                    allow_redirects=False,
                )
                sent_bytes += len(raw)
                device_transfer_state.update_send_job(job_id, sent_bytes=sent_bytes)
            else:
                source_path = item["_transfer_path"]
                with decrypted_temp_file(source_path, suffix=os.path.splitext(source_path)[1]) as plain_path:
                    actual_size = os.path.getsize(plain_path)
                    if actual_size != item["_transfer_size"]:
                        raise ValueError("A selected copy changed before it could be sent.")
                    item_base = sent_bytes
                    with open(plain_path, "rb") as source:
                        def chunks():
                            nonlocal sent_bytes
                            while True:
                                chunk = source.read(1024 * 1024)
                                if not chunk:
                                    break
                                sent_bytes += len(chunk)
                                device_transfer_state.update_send_job(
                                    job_id,
                                    sent_bytes=sent_bytes,
                                    current_name=filename,
                                    completed_items=index - 1,
                                )
                                yield chunk

                        response = requests.post(
                            receiver_url + "/device-transfer/item",
                            data=chunks(),
                            headers=headers,
                            timeout=(15, 600),
                            allow_redirects=False,
                        )
                    if sent_bytes - item_base != item["_transfer_size"]:
                        raise ValueError("A selected copy did not finish sending completely.")

            result = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else {}
            if not response.ok or result.get("success") is not True:
                raise ValueError(result.get("error") or f"Stash could not send {filename}.")
            device_transfer_state.update_send_job(
                job_id,
                completed_items=index,
                sent_bytes=sent_bytes,
            )

        response = requests.post(
            receiver_url + "/device-transfer/finish",
            headers={"Authorization": "Bearer " + transfer_token},
            timeout=15,
            allow_redirects=False,
        )
        result = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else {}
        if not response.ok or result.get("success") is not True:
            raise ValueError(result.get("error") or "Stash could not complete the transfer.")
        device_transfer_state.update_send_job(
            job_id,
            status="complete",
            completed_items=len(items),
            sent_bytes=total_bytes,
            current_name="",
            message=f"{len(items)} { 'copy' if len(items) == 1 else 'copies' } saved on the receiving laptop.",
        )
    except Exception as error:
        message = str(error)
        if isinstance(error, requests.RequestException):
            message = "Could not reach the receiving laptop. Keep both laptops on the same Wi-Fi and check that Stash is open there."
        device_transfer_state.update_send_job(
            job_id,
            status="error",
            error=message[:300],
            current_name="",
            message=message[:300],
        )


@stash_route("/api/device-transfer/code", methods=["POST"])
def create_device_transfer_code():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    status = device_transfer_state.receiver_status()
    if not status["ready"]:
        return jsonify({
            "error": status["error"] or "Stash's Wi-Fi transfer service is not ready. Restart Stash and try again.",
        }), 503
    addresses = _receiver_addresses()
    if not addresses:
        return jsonify({"error": "Stash could not find this laptop's Wi-Fi address. Connect it to Wi-Fi and try again."}), 503
    code, expires = device_transfer_state.create_pair_code()
    return jsonify({
        "success": True,
        "code": code,
        "address": f"http://{addresses[0]}:{TRANSFER_PORT}",
        "addresses": [f"http://{address}:{TRANSFER_PORT}" for address in addresses],
        "expires_at": expires,
        "expires_in_seconds": device_transfer_state.PAIR_CODE_TTL_SECONDS,
    })


@stash_route("/api/device-transfer/send", methods=["POST"])
def start_device_transfer():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Choose copies and enter the receiving laptop details."}), 400
    code = payload.get("code")
    if not isinstance(code, str) or not code.strip():
        return jsonify({"error": "Enter the one-time code shown on the receiving laptop."}), 400
    try:
        receiver_url = _validated_receiver_url(payload.get("receiver_url"))
        items, total_bytes = _transferable_items(payload.get("item_ids"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    job_id = device_transfer_state.create_send_job(len(items), total_bytes)
    worker = threading.Thread(
        target=_send_transfer,
        args=(job_id, items, total_bytes, receiver_url, code.strip().upper()),
        name="stash-send-copies",
        daemon=True,
    )
    worker.start()
    return jsonify({"success": True, "job_id": job_id}), 202


@stash_route("/api/device-transfer/status/<job_id>", methods=["GET"])
def get_device_transfer_status(job_id):
    job = device_transfer_state.get_send_job(job_id)
    if not job:
        return jsonify({"error": "This transfer status expired. Check the receiving library."}), 404
    return jsonify({"success": True, **job})
