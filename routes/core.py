"""Health, library views, settings, and organization routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/health", methods=["GET"])
@stash_route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


@stash_route("/api/settings/browser-video-copy", methods=["GET", "POST"])
def browser_video_copy_setting():
    if request.method == "GET":
        return jsonify({"enabled": _browser_video_copy_allowed()})
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    payload = request.get_json(silent=True)
    enabled = payload.get("enabled") if isinstance(payload, dict) else None
    if not isinstance(enabled, bool):
        return jsonify({"error": "Choose whether Copy with Stash may save browser videos."}), 400
    try:
        _set_browser_video_copy_allowed(enabled)
    except OSError:
        app.logger.exception("Could not save the browser video copy setting")
        return jsonify({"error": "Stash could not save this setting."}), 500
    return jsonify({"success": True, "enabled": enabled})


@stash_route("/api/settings/privacy", methods=["GET", "POST"])
def privacy_settings():
    if request.method == "GET":
        settings = get_privacy_settings()
        return jsonify({
            **settings,
            "library_encryption": "mac_keychain",
            "shared_mode": shared_service_enabled(),
            "shared_registration_open": os.environ.get(
                "COPY_MAKER_SHARED_REGISTRATION_OPEN", "0"
            ).strip().lower() in {"1", "true", "yes", "on"},
        })

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Choose a valid privacy setting."}), 400
    capture_enabled = payload.get("capture_enabled") if "capture_enabled" in payload else None
    retention_days = payload.get("retention_days") if "retention_days" in payload else None
    excluded_app_bundle_ids = payload.get("excluded_app_bundle_ids") if "excluded_app_bundle_ids" in payload else None
    excluded_sites = payload.get("excluded_sites") if "excluded_sites" in payload else None
    try:
        settings = set_privacy_settings(
            capture_enabled,
            retention_days,
            excluded_app_bundle_ids,
            excluded_sites,
        )
        removed_count = purge_expired_items() if retention_days is not None else 0
        return jsonify({"success": True, **settings, "removed_count": removed_count})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not save Stash privacy settings: %s", type(error).__name__)
        return jsonify({"error": "Stash could not save this privacy setting."}), 500


@stash_route("/api/settings/workspace-modes", methods=["GET", "POST"])
def workspace_mode_settings():
    if request.method == "GET":
        return jsonify({"modes": get_workspace_mode_settings()})
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403

    payload = request.get_json(silent=True)
    mode = payload.get("mode") if isinstance(payload, dict) else None
    enabled = payload.get("enabled") if isinstance(payload, dict) else None
    try:
        modes = set_workspace_mode_setting(mode, enabled)
    except ValueError:
        return jsonify({"error": "Choose a valid Stash section and on/off setting."}), 400
    except OSError:
        app.logger.exception("Could not save the workspace section setting")
        return jsonify({"error": "Stash could not save this setting."}), 500
    return jsonify({"success": True, "modes": modes})


@stash_route("/api/bin", methods=["GET"])
def get_bin():
    with _bin_lock:
        return jsonify({
            "items": get_bin_items(),
            "settings": get_bin_settings(),
        })


@stash_route("/api/bin/move", methods=["POST"])
def move_items_to_bin():
    data = request.get_json(silent=True) or {}
    try:
        item_ids = normalize_bin_item_ids(data)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    moved = []
    trashed_at = datetime.now().astimezone().isoformat()
    with _bin_lock:
        for item_id in item_ids:
            item = update_item(item_id, {
                "trashed_at": trashed_at,
            })
            if item:
                moved.append(item)

    return jsonify({
        "success": True,
        "moved_count": len(moved),
        "items": moved,
        "settings": get_bin_settings(),
    })


@stash_route("/api/bin/restore", methods=["POST"])
def restore_bin_items():
    data = request.get_json(silent=True) or {}
    try:
        item_ids = normalize_bin_item_ids(data)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    restored = []
    with _bin_lock:
        trashed_ids = {
            int(item.get("id"))
            for item in get_bin_items()
            if item.get("id") is not None
        }
        for item_id in item_ids:
            if item_id not in trashed_ids:
                continue
            item = update_item(item_id, {"trashed_at": None})
            if item:
                restored.append(item)

    return jsonify({"success": True, "restored_count": len(restored)})


@stash_route("/api/bin/schedule", methods=["POST"])
def schedule_bin_empty():
    data = request.get_json(silent=True) or {}
    empty_at = data.get("empty_at")

    if empty_at:
        try:
            scheduled = datetime.fromisoformat(str(empty_at).replace("Z", "+00:00"))
            if scheduled.timestamp() <= time.time():
                return jsonify({"success": False, "error": "Choose a future date and time."}), 400
        except (TypeError, ValueError, OverflowError):
            return jsonify({"success": False, "error": "Choose a valid date and time."}), 400
    else:
        empty_at = None

    with _bin_lock:
        settings = {
            "empty_at": empty_at,
            "reminder_sent_for": None,
            "review_notified_for": None,
        }
        save_bin_settings(settings)

    return jsonify({"success": True, "settings": settings})


@stash_route("/api/bin/empty", methods=["POST"])
def empty_bin_endpoint():
    with _bin_lock:
        deleted = empty_bin_now()
    if deleted:
        enqueue_bin_notification(
            f"You permanently deleted {len(deleted)} { 'copy' if len(deleted) == 1 else 'copies' } from the Stash Bin."
        )
    return jsonify({"success": True, "deleted_count": len(deleted)})


@stash_route("/api/notifications", methods=["GET"])
def get_notifications():

    with notification_lock:

        notifications = list(
            stash_notifications
        )

        stash_notifications.clear()

    return jsonify(notifications)


@stash_route("/")
def home():
    if shared_service_enabled():
        return send_from_directory(
            os.path.join(os.path.dirname(__file__), "ui"),
            "shared.html"
        )
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "ui"),
        "index.html"
    )


@stash_route("/shared")
def shared_home():
    if not shared_service_enabled():
        return jsonify({"error": "Shared Stash is not enabled on this server."}), 404
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "ui"),
        "shared.html"
    )


@stash_route("/ui/<path:filename>")
def ui_files(filename):
    if filename not in PUBLIC_UI_ASSETS:
        return "Not found", 404
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "ui"),
        filename
    )


@stash_route("/integrations/<path:filename>")
def integration_files(filename):
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "integrations"),
        filename,
    )


@stash_route("/api/folders", methods=["GET", "POST"])
def stash_folders():
    if request.method == "GET":
        return jsonify({"folders": load_stash_folders()})

    data = request.get_json(silent=True)
    name = data.get("name") if isinstance(data, dict) else None
    try:
        folders = create_stash_folder(name)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except OSError:
        app.logger.exception("Could not save Stash folders")
        return jsonify({"success": False, "error": "Stash could not save this folder."}), 500

    return jsonify({"success": True, "folders": folders})


@stash_route("/api/folders/move", methods=["POST"])
def move_stash_items_to_folder():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "folder_name" not in data:
        return jsonify({"success": False, "error": "Choose a destination folder."}), 400
    try:
        item_ids = normalize_bin_item_ids(data)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    folder_name = data.get("folder_name") if isinstance(data, dict) else None
    if folder_name is not None:
        if not isinstance(folder_name, str) or not folder_name.strip():
            return jsonify({"success": False, "error": "Choose a folder."}), 400
        folder_name = next(
            (folder for folder in load_stash_folders() if folder == folder_name),
            None,
        )
        if folder_name is None:
            return jsonify({"success": False, "error": "That folder no longer exists."}), 404

    moved = move_items_to_stash_folder(item_ids, folder_name)
    return jsonify({"success": True, "moved_count": len(moved)})
