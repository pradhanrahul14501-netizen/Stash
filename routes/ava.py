"""Ava chat, search, and confirmation routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/api/ava/folder-access", methods=["GET", "POST", "OPTIONS"])
def ava_folder_access():
    """Connect or disconnect Ava's single user-approved local folder."""
    if request.method == "OPTIONS":
        return "", 204
    from ava import file_actions
    if request.method == "GET":
        root = file_actions.connected_root(required=False)
        return jsonify({"success": True, "connected": bool(root), "folder_name": root.name if root else None})
    if not request_is_same_origin():
        return jsonify({"success": False, "message": "This request could not be verified."}), 403
    data = request.get_json(silent=True) or {}
    try:
        result = file_actions.disconnect_folder() if data.get("disconnect") is True else file_actions.connect_folder(data.get("folder"))
        return jsonify({"success": True, **result})
    except (OSError, ValueError) as error:
        return jsonify({"success": False, "message": str(error)}), 400


@stash_route("/api/ava/file-action/confirm", methods=["POST", "OPTIONS"])
def ava_confirm_file_action():
    if request.method == "OPTIONS":
        return "", 204
    if not request_is_same_origin():
        return jsonify({"success": False, "message": "This request could not be verified."}), 403
    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")
    if not isinstance(token, str) or not token:
        return jsonify({"success": False, "message": "This file-action preview is missing or expired."}), 400

    result, status = _execute_pending_file_action(token)
    if status < 400:
        import mobile_companion_state
        mobile_companion_state.clear_action_by_confirmation(token)
    return jsonify(result), status


def _execute_pending_file_action(token):
    with _AVA_PENDING_FILE_ACTION_LOCK:
        pending = _AVA_PENDING_FILE_ACTION.get(token)
        if pending is None:
            return {"success": False, "message": "This preview expired or was already used. Ask Ava to preview the action again."}, 400
        if pending["expires_at"] <= time.monotonic():
            _AVA_PENDING_FILE_ACTION.pop(token, None)
            return {"success": False, "message": "This preview expired. No files were changed; ask Ava to preview again."}, 400
        _AVA_PENDING_FILE_ACTION.pop(token, None)
    try:
        from ava import file_actions
        plan = pending["plan"]
        if plan.get("operation") == "undo":
            result = file_actions.undo_last_action(plan.get("action_id"), plan)
        elif plan.get("operation") == "restore_trash":
            result = file_actions.execute_restore_plan(plan)
        elif plan.get("operation") == "empty_trash":
            result = file_actions.empty_trash(plan)
        else:
            result = file_actions.execute_plan(plan)
        return result, 200
    except (OSError, ValueError) as error:
        return {"success": False, "message": str(error)}, 400
    except Exception as error:
        app.logger.warning("Ava file action failed (%s)", type(error).__name__)
        return {"success": False, "message": "Stash could not complete that file action. No additional files were changed."}, 500


@stash_route("/api/ava/file-action/cancel", methods=["POST", "OPTIONS"])
def ava_cancel_file_action():
    if request.method == "OPTIONS":
        return "", 204
    if not request_is_same_origin():
        return jsonify({"success": False, "message": "This request could not be verified."}), 403
    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")
    if not isinstance(token, str) or not token:
        return jsonify({"success": False, "message": "This file-action preview is missing or expired."}), 400
    with _AVA_PENDING_FILE_ACTION_LOCK:
        pending = _AVA_PENDING_FILE_ACTION.pop(token, None)
    if pending is None:
        return jsonify({"success": False, "message": "This preview expired or was already used."}), 400
    import mobile_companion_state
    mobile_companion_state.clear_action_by_confirmation(token)
    return jsonify({"success": True, "cancelled": True, "message": "Cancelled. No files were changed."})


@stash_route("/api/ava/confirm-delete", methods=["POST", "OPTIONS"])
def ava_confirm_delete():

    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")
    if not isinstance(token, str) or not token:
        return jsonify({
            "success": False,
            "message": "The delete confirmation is missing or has expired. Ask Ava to preview the item again.",
        }), 400

    item_id = data.get("item_id")
    if item_id is None:
        item = data.get("item") or data.get("video")
        if isinstance(item, dict):
            item_id = item.get("id")

    cancel = data.get("cancel") is True
    if item_id is None and not cancel:
        return jsonify({
            "success": False,
            "message": "No item selected."
        }), 400

    with _AVA_PENDING_DELETE_LOCK:
        pending = _AVA_PENDING_DELETE.get(token)
        if pending is None:
            return jsonify({
                "success": False,
                "message": "This delete preview has expired or was already used. Ask Ava to preview the item again.",
            }), 400
        if pending["expires_at"] <= time.monotonic():
            _AVA_PENDING_DELETE.pop(token, None)
            return jsonify({
                "success": False,
                "message": "This delete preview has expired. Ask Ava to preview the item again.",
            }), 400
        if not cancel and str(pending["item_id"]) != str(item_id):
            return jsonify({
                "success": False,
                "message": "That item does not match Ava's delete preview.",
            }), 400
        _AVA_PENDING_DELETE.pop(token, None)

    if cancel:
        return jsonify({
            "success": True,
            "cancelled": True,
            "message": "Delete cancelled. Nothing was deleted.",
        })

    try:
        from ava.agent import confirm_delete

        result = confirm_delete(item_id)

        return jsonify(result)

    except Exception as error:
        print("❌ Ava delete confirmation error:", type(error).__name__)

        return jsonify({
            "success": False,
            "message": "Stash could not complete that action."
        }), 500


@stash_route("/api/ava/extract-attachment", methods=["POST"])
def ava_extract_attachment():
    if not request_is_same_origin():
        return jsonify({"success": False, "message": "This request could not be verified."}), 403
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"success": False, "message": "Choose a file to attach."}), 400
    filename = os.path.basename(uploaded.filename.replace("\\", "/"))
    file_bytes = uploaded.stream.read(MAX_AVA_ATTACHMENT_BYTES + 1)
    if len(file_bytes) > MAX_AVA_ATTACHMENT_BYTES:
        return jsonify({"success": False, "message": "That attachment is too large. Choose a file under 20 MB."}), 413
    try:
        extracted, truncated = _extract_ava_attachment_text(filename, file_bytes)
    except RuntimeError as error:
        app.logger.warning("Ava attachment parser unavailable: %s", error)
        return jsonify({"success": False, "message": str(error)}), 503
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 415
    except Exception as error:
        app.logger.warning("Ava could not extract attachment text (%s)", type(error).__name__)
        return jsonify({"success": False, "message": "Stash could not read this attachment. Try another file."}), 422
    return jsonify({
        "success": True,
        "name": filename,
        "text": extracted,
        "truncated": truncated,
        "message": "Attachment ready for Ava.",
    })


@stash_route("/api/ava", methods=["POST", "OPTIONS"])
def ava_api():

    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    command = data.get("command", "").strip()
    raw_history = data.get("history")
    history = []
    if isinstance(raw_history, list):
        total_history_chars = 0
        for item in reversed(raw_history[-12:]):
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                continue
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            content = content.strip()[:1800]
            if total_history_chars + len(content) > 12000:
                break
            history.append({"role": item["role"], "content": content})
            total_history_chars += len(content)
        history.reverse()

    if not command:
        return jsonify({
            "success": False,
            "message": "Ava needs a command."
        }), 400

    try:
        input_mode = "voice" if data.get("input_mode") == "voice" else "text"
        result = ava_run(
            command,
            history=history,
            input_mode=input_mode,
            search_context=data.get("search_context"),
            search_offset=data.get("search_offset", 0),
            conversation_id=data.get("conversation_id"),
        )

        if result.get("cancelled"):
            with _AVA_PENDING_DELETE_LOCK:
                _AVA_PENDING_DELETE.clear()
            with _AVA_PENDING_FILE_ACTION_LOCK:
                _AVA_PENDING_FILE_ACTION.clear()

        if result.get("confirmation_type") == "delete_item":
            item = result.get("item") or result.get("video") or {}
            item_id = item.get("id") if isinstance(item, dict) else None
            if item_id is not None:
                token = secrets.token_urlsafe(24)
                now = time.monotonic()
                with _AVA_PENDING_DELETE_LOCK:
                    for existing_token, pending in list(_AVA_PENDING_DELETE.items()):
                        if pending["expires_at"] <= now:
                            _AVA_PENDING_DELETE.pop(existing_token, None)
                    _AVA_PENDING_DELETE[token] = {
                        "item_id": str(item_id),
                        "expires_at": now + 600,
                    }
                result["confirmation_token"] = token

        if result.get("confirmation_type") == "organize_files":
            preview = result.get("file_organization_preview") or {}
            token = secrets.token_urlsafe(24)
            _AVA_PENDING_FILE_ORGANIZATION[token] = {
                "folder": preview.get("folder"),
                "moves": preview.get("moves", [])
            }
            result["confirmation_token"] = token

        if result.get("confirmation_type") == "copy_files":
            preview = result.get("file_copy_preview") or {}
            token = secrets.token_urlsafe(24)
            _AVA_PENDING_FILE_COPY[token] = {
                "source_folder": preview.get("source_folder"),
                "destination_folder": preview.get("destination_folder"),
                "date": preview.get("date"),
                "files": preview.get("moves", [])
            }
            result["confirmation_token"] = token

        if result.get("confirmation_type") == "file_action":
            plan = result.get("file_action_preview") or {}
            token = secrets.token_urlsafe(24)
            now = time.monotonic()
            with _AVA_PENDING_FILE_ACTION_LOCK:
                for existing_token, pending in list(_AVA_PENDING_FILE_ACTION.items()):
                    if pending["expires_at"] <= now:
                        _AVA_PENDING_FILE_ACTION.pop(existing_token, None)
                _AVA_PENDING_FILE_ACTION[token] = {"plan": plan, "expires_at": now + 300}
            result["confirmation_token"] = token
            import mobile_companion_state
            result["mobile_action_id"] = mobile_companion_state.enqueue_action(token, plan)
            result["file_action_preview"] = {
                key: value for key, value in plan.items()
                if key in {"operation", "by", "count", "message"}
            }
            result["file_action_preview"]["items"] = [
                {
                    key: value for key, value in item.items()
                    if key in {"path", "destination", "size", "collision_suffix"}
                }
                for item in plan.get("items", [])
                if isinstance(item, dict)
            ]

        return jsonify(result)

    except Exception as error:
        print("❌ Ava error:", type(error).__name__)

        if isinstance(error, AvaServiceError):
            return jsonify({
                "success": False,
                "message": str(error),
                "error_code": error.code,
                "retryable": error.retryable,
            }), 503

        return jsonify({
            "success": False,
            "message": "Stash could not complete that request."
        }), 500


@stash_route("/api/ava/search-action", methods=["POST"])
def ava_search_action():
    """Run an explicit action on a result returned by Ava's read-only search."""
    if not request_is_same_origin():
        return jsonify({"success": False, "message": "This request could not be verified."}), 403
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    source = data.get("source")
    if action not in {"open", "reveal", "copy", "save"}:
        return jsonify({"success": False, "message": "Choose a supported action."}), 400

    try:
        if source == "mac":
            source_path = resolve_safe_mac_file(data.get("path"))
            if action == "open":
                subprocess.Popen(["open", source_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return jsonify({"success": True, "message": "Opened the file."})
            if action == "reveal":
                subprocess.Popen(["open", "-R", source_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return jsonify({"success": True, "message": "Revealed the file in Finder."})
            if action == "copy":
                expected_count = get_clipboard_change_count()
                copied, _ = set_file_on_system_clipboard(source_path, expected_count)
                if not copied:
                    return jsonify({"success": False, "message": "The file could not be copied to the Mac clipboard."}), 503
                return jsonify({"success": True, "message": "Copied the file to the clipboard."})
            item_type = get_item_category({"type": "file", "file": source_path})
            item_type = {"videos": "video", "images": "image", "links": "link", "files": "file"}.get(item_type, item_type)
            saved = save_file(item_type, source_path)
            return jsonify({"success": True, "message": f"Saved {os.path.basename(source_path)} to Stash.", "saved_item_id": saved.get("id")})

        if source != "stash":
            return jsonify({"success": False, "message": "Choose a result from Ava's search."}), 400
        item_id = data.get("item_id")
        if item_id is None:
            return jsonify({"success": False, "message": "Choose a saved Stash item first."}), 400
        item = next((saved for saved in load_items() if str(saved.get("id")) == str(item_id)), None)
        if item is None:
            return jsonify({"success": False, "message": "That Stash item is no longer available."}), 404

        raw_path = item.get("file")
        media_path = None
        if isinstance(raw_path, str) and raw_path.strip():
            candidate = raw_path if os.path.isabs(raw_path) else os.path.join(os.path.dirname(__file__), raw_path)
            media_path = os.path.realpath(candidate)
            storage_root = os.path.realpath(storage_manager.STORAGE_DIR)
            managed_roots = [os.path.realpath(os.path.join(storage_root, name)) for name in ("media", "videos")]
            try:
                in_stash_media = any(os.path.commonpath((root, media_path)) == root and media_path != root for root in managed_roots)
            except ValueError:
                in_stash_media = False
            if not in_stash_media:
                media_path = None
        if action == "open":
            item_url = item.get("url") or item.get("page_url") or item.get("source_url")
            if isinstance(item_url, str) and urlparse(item_url).scheme in {"http", "https"}:
                return jsonify({"success": True, "open_url": item_url})
            if not media_path or not os.path.isfile(media_path):
                text_content = item.get("content")
                if isinstance(text_content, str) and text_content:
                    return jsonify({"success": True, "open_text": text_content, "message": "Opened the saved text in Ava."})
                return jsonify({"success": False, "message": "This Stash item has no openable file or link."}), 404
            media_root = os.path.realpath(os.path.join(storage_manager.STORAGE_DIR, "media"))
            video_root = os.path.realpath(os.path.join(storage_manager.STORAGE_DIR, "videos"))
            root = video_root if os.path.commonpath((video_root, media_path)) == video_root else media_root
            relative = os.path.relpath(media_path, root)
            route = "/videos/" if root == video_root else "/media/"
            return jsonify({"success": True, "open_url": route + quote(relative, safe="/")})
        if action == "reveal":
            if not media_path or not os.path.isfile(media_path):
                return jsonify({"success": False, "message": "This Stash item has no local media file."}), 404
            subprocess.Popen(["open", "-R", media_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return jsonify({"success": True, "message": "Revealed the Stash file in Finder."})
        if action == "copy":
            copy_text = item.get("content") or item.get("url") or item.get("page_url") or item.get("source_url") or item.get("title") or item.get("original_name")
            if not copy_text and media_path and os.path.isfile(media_path):
                media_root = os.path.realpath(os.path.join(storage_manager.STORAGE_DIR, "media"))
                video_root = os.path.realpath(os.path.join(storage_manager.STORAGE_DIR, "videos"))
                root = video_root if os.path.commonpath((video_root, media_path)) == video_root else media_root
                route = "/videos/" if root == video_root else "/media/"
                copy_text = request.host_url.rstrip("/") + route + quote(os.path.relpath(media_path, root), safe="/")
            if not isinstance(copy_text, str) or not copy_text:
                return jsonify({"success": False, "message": "There is no text or link to copy from this Stash item."}), 400
            return jsonify({"success": True, "copy_text": copy_text, "message": "Copied the Stash item to the clipboard."})
        return jsonify({"success": False, "message": "Save to Stash is available for files on your Mac."}), 400
    except (ValueError, OSError) as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        app.logger.warning("Ava search action failed: %s", type(error).__name__)
        return jsonify({"success": False, "message": "Stash could not complete that file action."}), 500


@stash_route("/api/ava/cancel-organize-files", methods=["POST", "OPTIONS"])
def ava_cancel_organize_files():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")

    if not isinstance(token, str) or not token:
        return jsonify({"success": False, "message": "The file-organization confirmation is missing."}), 400

    pending = _AVA_PENDING_FILE_ORGANIZATION.pop(token, None)
    if pending is None:
        return jsonify({
            "success": False,
            "message": "This preview has expired or was already used. Please request a new preview."
        }), 400

    return jsonify({"success": True, "message": "File organization cancelled. No files were moved."})


@stash_route("/api/ava/confirm-organize-files", methods=["POST", "OPTIONS"])
def ava_confirm_organize_files():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")

    if not isinstance(token, str) or not token:
        return jsonify({"success": False, "message": "The file-organization confirmation is missing."}), 400

    pending = _AVA_PENDING_FILE_ORGANIZATION.pop(token, None)
    if pending is None:
        return jsonify({
            "success": False,
            "message": "This preview has expired or was already used. Please request a new preview."
        }), 400

    try:
        from ava.file_organizer import organize_files
        result = organize_files(pending["folder"], pending["moves"])
        return jsonify(result)
    except Exception as error:
        print("Ava file-organization confirmation error:", type(error).__name__)
        return jsonify({"success": False, "message": "Stash could not organize those files."}), 500


@stash_route("/api/ava/cancel-copy-files", methods=["POST", "OPTIONS"])
def ava_cancel_copy_files():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")
    if not isinstance(token, str) or not token:
        return jsonify({"success": False, "message": "The file-copy confirmation is missing."}), 400

    pending = _AVA_PENDING_FILE_COPY.pop(token, None)
    if pending is None:
        return jsonify({"success": False, "message": "This preview has expired or was already used. Please request a new preview."}), 400

    return jsonify({"success": True, "message": "File copying cancelled. No files were copied."})


@stash_route("/api/ava/confirm-copy-files", methods=["POST", "OPTIONS"])
def ava_confirm_copy_files():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    token = data.get("confirmation_token")
    if not isinstance(token, str) or not token:
        return jsonify({"success": False, "message": "The file-copy confirmation is missing."}), 400

    pending = _AVA_PENDING_FILE_COPY.pop(token, None)
    if pending is None:
        return jsonify({"success": False, "message": "This preview has expired or was already used. Please request a new preview."}), 400

    try:
        from ava.file_organizer import copy_today_files
        result = copy_today_files(
            pending["source_folder"],
            pending["destination_folder"],
            pending["date"],
            pending["files"]
        )
        return jsonify(result)
    except Exception as error:
        print("Ava file-copy confirmation error:", type(error).__name__)
        return jsonify({"success": False, "message": "Stash could not copy those files."}), 500


@stash_route("/api/ava/confirm-arrange", methods=["POST", "OPTIONS"])
def ava_confirm_arrange():

    if request.method == "OPTIONS":
        return "", 204

    try:

        data = request.get_json(silent=True) or {}
        filters = data.get("filters", data)

        from ava.agent import confirm_arrange_today

        result = confirm_arrange_today(filters)

        return jsonify(result)

    except Exception as error:

        print("❌ Ava arrange confirmation error:", type(error).__name__)

        return jsonify({
            "success": False,
            "message": "Stash could not arrange those items."
        }), 500
