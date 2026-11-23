"""Media streaming and clipboard handoff routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/media/<path:filename>")
def media_files(filename):
    root = os.path.realpath(os.path.join(LOCAL_STORAGE_DIR, "media"))
    path = os.path.realpath(os.path.join(root, filename))
    try:
        allowed = os.path.commonpath((root, path)) == root and path != root
    except ValueError:
        allowed = False
    if not allowed or not os.path.isfile(path):
        return "Not found", 404
    if is_encrypted_media(path):
        return _encrypted_media_response(path, filename)
    return send_from_directory(
        root,
        filename
    )


@stash_route("/videos/<path:filename>")
def video_files(filename):
    root = os.path.realpath(os.path.join(LOCAL_STORAGE_DIR, "videos"))
    path = os.path.realpath(os.path.join(root, filename))
    try:
        allowed = os.path.commonpath((root, path)) == root and path != root
    except ValueError:
        allowed = False
    if not allowed or not os.path.isfile(path):
        return "Not found", 404
    if is_encrypted_media(path):
        return _encrypted_media_response(path, filename)
    return send_from_directory(
        root,
        filename
    )


@stash_route("/api/videos/<int:item_id>/copy-to-clipboard", methods=["POST"])
def copy_video_to_clipboard(item_id):
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403

    item = next(
        (
            saved for saved in load_items()
            if str(saved.get("id")) == str(item_id)
            and saved.get("type") == "video"
        ),
        None,
    )
    if item is None:
        return jsonify({"error": "Video not found in Stash."}), 404

    base_dir = os.path.dirname(os.path.abspath(__file__))
    video_dir = os.path.realpath(os.path.join(LOCAL_STORAGE_DIR, "videos"))
    source_value = item.get("file") or ""
    source_path = source_value if os.path.isabs(source_value) else os.path.join(base_dir, source_value)
    source_path = os.path.realpath(source_path)
    try:
        if os.path.commonpath((video_dir, source_path)) != video_dir:
            return jsonify({"error": "This video is outside Stash's video library."}), 400
    except ValueError:
        return jsonify({"error": "This video is outside Stash's video library."}), 400
    if not os.path.isfile(source_path):
        return jsonify({"error": "Stash could not find this saved video."}), 404

    share_path = None
    cached_share_value = item.get("shareable_mp4_file")
    if cached_share_value:
        cached_share_path = (
            cached_share_value
            if os.path.isabs(cached_share_value)
            else os.path.join(base_dir, cached_share_value)
        )
        cached_share_path = os.path.realpath(cached_share_path)
        try:
            if (
                os.path.commonpath((video_dir, cached_share_path)) == video_dir
                and os.path.isfile(cached_share_path)
            ):
                share_path = cached_share_path
        except ValueError:
            pass

    if share_path is None:
        converted_path = None
        share_path = None
        plain_share_size = None
        try:
            with decrypted_temp_file(source_path, suffix=os.path.splitext(source_path)[1]) as plain_source:
                converted_path, converted, conversion_error = convert_video_to_shareable_mp4(plain_source)
                if conversion_error and not converted:
                    if conversion_error == "ffmpeg_not_found":
                        return jsonify({"error": "Stash needs ffmpeg installed to convert this video for the clipboard."}), 503
                    if conversion_error == "conversion_too_large":
                        return jsonify({"error": "This video is too large to convert safely for the clipboard."}), 413
                    if conversion_error == "conversion_busy":
                        return jsonify({"error": "Stash is preparing other videos. Try copying again shortly."}), 503
                    return jsonify({
                        "error": "Stash could not convert this video to MP4. The saved original is unchanged."
                    }), 503
                if not converted or converted_path == plain_source:
                    if converted_path == plain_source:
                        # A compatible source can be published directly from its encrypted library path.
                        share_path = source_path
                    else:
                        return jsonify({
                            "error": "Stash could not prepare this video for the clipboard."
                        }), 503
                else:
                    share_path = os.path.join(
                        os.path.dirname(source_path),
                        f"shareable_{item_id}_{secrets.token_hex(4)}.mp4",
                    )
                    plain_share_size = os.path.getsize(converted_path)
                    encrypt_media_file(converted_path, share_path)
        except Exception:
            for path in (converted_path, share_path):
                if path:
                    cleanup_video_conversion(path)
                    if path != converted_path:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except OSError:
                            pass
            return jsonify({"error": "Stash could not prepare this video securely."}), 503
        finally:
            if converted_path:
                cleanup_video_conversion(converted_path)
        if plain_share_size is not None:
            item = update_item(
                item_id,
                {
                    "shareable_mp4_file": os.path.relpath(share_path, base_dir),
                    "shareable_mp4_size": plain_share_size,
                    "shareable_mp4_mime_type": "video/mp4",
                },
            ) or item

    try:
        expected_clipboard_change_count = get_clipboard_change_count()
    except Exception:
        expected_clipboard_change_count = None
    if expected_clipboard_change_count is None:
        return jsonify({"error": "Stash could not access the Mac clipboard."}), 503

    if not publish_video_file_to_clipboard(
        share_path,
        expected_clipboard_change_count,
    ):
        return jsonify({"error": "Stash could not copy the MP4 to the Mac clipboard."}), 503

    return jsonify({
        "success": True,
        "message": "MP4 copied. Paste it into WhatsApp or another app.",
        "item": item,
        "mime_type": "video/mp4",
    })
