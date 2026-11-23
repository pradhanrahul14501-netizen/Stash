"""Desktop routes for pairing and reviewing Android companion sync state."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/api/mobile-companion/pair-code", methods=["POST"])
def create_mobile_companion_pair_code():
    if not request_is_same_origin():
        return jsonify({"success": False, "error": "This request could not be verified."}), 403
    from device_transfer_receiver import TRANSFER_PORT
    import mobile_companion_state
    import device_transfer_state

    status = device_transfer_state.receiver_status()
    if not status["ready"]:
        return jsonify({"success": False, "error": status["error"] or "Stash's local Wi-Fi link is not ready."}), 503
    addresses = _receiver_addresses()
    if not addresses:
        return jsonify({"success": False, "error": "Connect this computer to private Wi-Fi and try again."}), 503
    code, expires = mobile_companion_state.create_pair_code()
    return jsonify({
        "success": True,
        "code": code,
        "addresses": [f"http://{address}:{TRANSFER_PORT}" for address in addresses],
        "expires_at": expires,
        "expires_in_seconds": mobile_companion_state.PAIR_CODE_TTL_SECONDS,
        "replaces_existing_phone": mobile_companion_state.is_paired(),
    })


@stash_route("/api/mobile-companion/status", methods=["GET"])
def mobile_companion_status():
    import mobile_companion_state

    return jsonify({"success": True, "paired": mobile_companion_state.is_paired()})


@stash_route("/api/mobile-companion/unpair", methods=["POST"])
def revoke_mobile_companion_pairing():
    if not request_is_same_origin():
        return jsonify({"success": False, "error": "This request could not be verified."}), 403
    import mobile_companion_state

    was_paired = mobile_companion_state.revoke_pairing()
    return jsonify({"success": True, "was_paired": was_paired})


@stash_route("/api/mobile-companion/action-status/<action_id>", methods=["GET"])
def mobile_companion_action_status(action_id):
    if not request_is_same_origin():
        return jsonify({"success": False, "error": "This request could not be verified."}), 403
    import mobile_companion_state

    result = mobile_companion_state.action_status(action_id)
    if not result:
        return jsonify({"success": False, "error": "This phone preview expired."}), 404
    return jsonify({"success": True, **result})


@stash_route("/api/mobile-companion/follow-ups", methods=["GET"])
def get_desktop_mobile_follow_ups():
    import mobile_companion_state

    follow_ups = mobile_companion_state.get_follow_ups()
    return jsonify({
        "success": True,
        "follow_ups": [entry for entry in follow_ups if not entry.get("deletedAt")],
        "paired": mobile_companion_state.is_paired(),
    })
