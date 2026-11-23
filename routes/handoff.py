"""Desktop app and Finder handoff routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/api/integrations/open-folder", methods=["POST"])
def open_integration_folder():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    data = request.get_json(silent=True) or {}
    app_key = data.get("app") if isinstance(data, dict) else None
    allowed_apps = {
        "capcut": ("CapCut", "capcut", "/Applications/CapCut.app"),
        "davinci": ("DaVinci Resolve", "davinci", "/Applications/DaVinci Resolve.app"),
        "cursor": ("Cursor", "cursor", "/Applications/Cursor.app"),
    }
    if not isinstance(app_key, str) or app_key not in allowed_apps:
        return jsonify({"error": "Choose a supported app folder."}), 400
    label, folder_name, application_name = allowed_apps[app_key]
    if app_key == "cursor":
        folder = os.path.join(os.path.dirname(__file__), "integrations", "cursor")
    else:
        folder = os.path.join(LOCAL_STORAGE_DIR, "integrations", "handoff", folder_name)
    os.makedirs(folder, exist_ok=True)
    try:
        subprocess.Popen(
            ["open", folder],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return jsonify({"error": f"Could not open the {label} folder on this Mac."}), 500

    try:
        launched = subprocess.run(
            ["open", "-a", application_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=False,
        )
        app_opened = launched.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        app_opened = False

    return jsonify({"success": True, "label": label, "appOpened": app_opened})


@stash_route("/api/integrations/open-library-item", methods=["POST"])
def open_library_item_in_app():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403

    data = request.get_json(silent=True) or {}
    item_id = data.get("itemId") if isinstance(data, dict) else None
    app_key = data.get("app") if isinstance(data, dict) else None
    allowed_apps = {
        "capcut": ("CapCut", "/Applications/CapCut.app"),
        "davinci": ("DaVinci Resolve", "/Applications/DaVinci Resolve.app"),
        "cursor": ("Cursor", "/Applications/Cursor.app"),
        "notes": ("Notes", "/System/Applications/Notes.app"),
        "preview": ("Preview", "/System/Applications/Preview.app"),
        "default": ("the default app", None),
        "quicktime": ("QuickTime Player", "/System/Applications/QuickTime Player.app"),
    }
    if not isinstance(app_key, str) or app_key not in allowed_apps or item_id is None:
        return jsonify({"error": "Choose a saved file and a supported app."}), 400

    try:
        saved_items = load_items()
    except Exception:
        app.logger.exception("Stash could not read the library for an app handoff")
        return jsonify({"error": "Stash could not read the saved library item. Check that the library is unlocked, then try again."}), 503
    item = next(
        (saved for saved in saved_items if str(saved.get("id")) == str(item_id)),
        None,
    )
    if not item:
        return jsonify({"error": "That saved Stash item could not be found."}), 404
    if app_key == "quicktime" and item.get("type") != "video":
        return jsonify({"error": "QuickTime Player can open saved videos only."}), 400

    relative_path = item.get("file")
    text_content = None
    link_url = None
    base_dir = os.path.realpath(os.path.dirname(__file__))
    source_path = None
    if isinstance(relative_path, str) and relative_path.strip():
        source_path = relative_path if os.path.isabs(relative_path) else os.path.join(base_dir, relative_path)
        source_path = os.path.realpath(source_path)
        allowed_source_roots = [
            os.path.realpath(os.path.join(LOCAL_STORAGE_DIR, "videos")),
            os.path.realpath(os.path.join(LOCAL_STORAGE_DIR, "media")),
        ]
        try:
            source_is_allowed = any(
                os.path.commonpath((root, source_path)) == root
                and source_path != root
                for root in allowed_source_roots
            )
        except ValueError:
            source_is_allowed = False
        if not source_is_allowed:
            return jsonify({"error": "Only media saved inside the Stash library can be sent to an app."}), 400
        if not os.path.isfile(source_path):
            return jsonify({"error": "The saved media file is no longer available."}), 404
    else:
        text_content = item.get("text") or item.get("content") or item.get("value")
        candidate_url = item.get("url") or text_content
        link_url = None
        if app_key == "default" and isinstance(candidate_url, str):
            parsed_url = urlparse(candidate_url.strip())
            if parsed_url.scheme in {"http", "https"} and parsed_url.hostname:
                link_url = candidate_url.strip()
        if link_url:
            text_content = None
        elif app_key not in {"notes", "cursor"} or not isinstance(text_content, str):
            return jsonify({"error": "This saved item does not have a local file copy to open."}), 400
        if text_content is not None and len(text_content.encode("utf-8")) > 1_048_576:
            return jsonify({"error": "This text copy is too large to prepare for another app."}), 413

    label, application_path = allowed_apps[app_key]
    folder = os.path.join(LOCAL_STORAGE_DIR, "integrations", "handoff", app_key)
    if app_key == "quicktime":
        _cleanup_expired_exports()
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        os.chmod(folder, 0o700)
    except OSError:
        return jsonify({"error": "Stash could not secure the temporary app handoff folder."}), 500

    display_name = (
        item.get("original_name")
        or item.get("filename")
        or item.get("name")
        or (os.path.basename(source_path) if source_path else "stash-link" if link_url else "stash-note")
    )
    filename = secure_filename(os.path.basename(str(display_name))) or "stash-media"
    if not os.path.splitext(filename)[1]:
        filename += os.path.splitext(source_path)[1] if source_path else ".webloc" if link_url else ".txt"
    quicktime_conversion_path = None
    if app_key == "quicktime":
        filename = os.path.splitext(filename)[0] + ".mp4"
    destination_path = os.path.join(folder, filename)
    if os.path.exists(destination_path):
        stem, extension = os.path.splitext(filename)
        counter = 2
        while os.path.exists(destination_path):
            destination_path = os.path.join(folder, f"{stem}_{counter}{extension}")
            counter += 1

    try:
        generated_text = text_content or ""
        generated_bytes = plistlib.dumps({"URL": link_url}, fmt=plistlib.FMT_XML) if link_url else generated_text.encode("utf-8")
        source_size = os.path.getsize(source_path) if source_path else len(generated_bytes)
        if shutil.disk_usage(folder).free < source_size:
            return jsonify({"error": "There is not enough free space on this Mac for another copy."}), 507
        if app_key == "quicktime":
            if _handoff_directory_size(folder) + source_size > MAX_HANDOFF_TOTAL_BYTES:
                return jsonify({"error": "QuickTime handoff storage is full. Remove older handoff copies and try again."}), 507
            conversion_reserve = min(
                MAX_VIDEO_CONVERSION_BYTES,
                max(source_size * 2, 64 * 1024 * 1024),
            )
            if shutil.disk_usage(tempfile.gettempdir()).free < conversion_reserve:
                return jsonify({"error": "There is not enough free space to prepare this video for QuickTime."}), 507
        if source_path is None:
            with open(destination_path, "xb") as handoff_file:
                handoff_file.write(generated_bytes)
        else:
            with decrypted_temp_file(source_path, suffix=os.path.splitext(source_path)[1]) as plain_source:
                source_for_handoff = plain_source
                if app_key == "quicktime":
                    quicktime_conversion_path, converted, conversion_error = convert_video_to_shareable_mp4(plain_source)
                    if conversion_error == "ffmpeg_not_found":
                        return jsonify({"error": "Stash needs ffmpeg installed to prepare this video for QuickTime."}), 503
                    if conversion_error == "conversion_too_large":
                        return jsonify({"error": "This video is too large to prepare safely for QuickTime."}), 413
                    if conversion_error == "conversion_busy":
                        return jsonify({"error": "Stash is preparing other videos. Try QuickTime again shortly."}), 503
                    if conversion_error:
                        return jsonify({"error": "Stash could not prepare this video for QuickTime."}), 503
                    if converted:
                        source_for_handoff = quicktime_conversion_path
                    elif quicktime_conversion_path != plain_source:
                        return jsonify({"error": "Stash could not prepare this video for QuickTime."}), 503
                if app_key == "quicktime":
                    with _HANDOFF_CAPACITY_LOCK:
                        if (
                            _handoff_directory_size(folder) + os.path.getsize(source_for_handoff)
                            > MAX_HANDOFF_TOTAL_BYTES
                        ):
                            return jsonify({"error": "QuickTime handoff storage is full. Remove older handoff copies and try again."}), 507
                        shutil.copy2(source_for_handoff, destination_path)
                else:
                    shutil.copy2(source_for_handoff, destination_path)
        os.chmod(destination_path, 0o600)
    except Exception:
        try:
            if os.path.exists(destination_path):
                os.remove(destination_path)
        except OSError:
            pass
        return jsonify({"error": "The media could not be copied to the app handoff folder."}), 500
    finally:
        if quicktime_conversion_path:
            cleanup_video_conversion(quicktime_conversion_path)

    def remove_handoff_copy(path=destination_path):
        try:
            os.remove(path)
        except OSError:
            pass

    handoff_cleanup = threading.Timer(60 * 60, remove_handoff_copy)
    handoff_cleanup.daemon = True
    handoff_cleanup.start()

    try:
        if app_key == "quicktime":
            launched = subprocess.run(
                ["open", "-a", application_path, destination_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
        elif app_key in {"notes", "preview", "cursor"}:
            launched = subprocess.run(
                ["open", "-a", application_path, destination_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
        elif app_key == "default":
            launched = subprocess.run(
                ["open", destination_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
        else:
            subprocess.Popen(
                ["open", "-R", destination_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            launched = subprocess.run(
                ["open", "-a", application_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                check=False,
            )
        app_opened = launched.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        app_opened = False

    next_steps = {
        "capcut": f"In CapCut, choose New project → Import and select {os.path.basename(destination_path)}.",
        "davinci": f"In Resolve, use Media Pool → Import Media and select {os.path.basename(destination_path)}.",
        "cursor": f"The copy is in Cursor's handoff folder: {os.path.basename(destination_path)}.",
        "notes": "The temporary text copy is in Stash's private handoff folder and will be removed after one hour. Your saved copy stays in Stash.",
        "preview": "The temporary image copy is in Stash's private handoff folder and will be removed after one hour. Your saved copy stays in Stash.",
        "default": "Stash opened a temporary copy with your Mac's default app. The saved copy stays in Stash.",
        "quicktime": "The temporary playable copy is in Stash's QuickTime handoff folder and will be removed after one hour. Your encrypted original stays in Stash.",
    }
    return jsonify({
        "success": True,
        "label": label,
        "displayName": os.path.basename(destination_path),
        "appOpened": app_opened,
        "nextStep": next_steps[app_key],
    })
