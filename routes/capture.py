"""Browser, clipboard, and media capture routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/api/browser-copy/import-audio-download", methods=["POST", "OPTIONS"])
def import_audio_download():

    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    download_id = data.get("download_id")
    source_path = data.get("filename")

    if download_id is None or not isinstance(source_path, str) or not os.path.isabs(source_path):
        return jsonify({
            "success": False,
            "error": "A completed browser download is required."
        }), 400

    downloads_root = os.path.realpath(
        os.path.join(os.path.expanduser("~"), "Downloads")
    )
    source_path = os.path.realpath(source_path)

    try:
        is_download_file = os.path.commonpath((downloads_root, source_path)) == downloads_root
    except ValueError:
        is_download_file = False

    if not is_download_file:
        return jsonify({
            "success": False,
            "error": "Only audio files saved in your Downloads folder can be imported."
        }), 403

    if not os.path.isfile(source_path):
        return jsonify({
            "success": False,
            "error": "The downloaded audio file is no longer available."
        }), 404

    original_name = os.path.basename(source_path)
    extension = os.path.splitext(original_name)[1].lower()
    audio_extensions = {
        ".aac", ".aif", ".aiff", ".amr", ".flac", ".m4a", ".mid",
        ".midi", ".mp2", ".mp3", ".mpga", ".oga", ".ogg", ".opus",
        ".wav", ".wma"
    }
    provided_mime = str(data.get("mime_type") or "").split(";", 1)[0].strip().lower()
    guessed_mime = (mimetypes.guess_type(original_name)[0] or "").lower()

    if not (
        provided_mime.startswith("audio/")
        or guessed_mime.startswith("audio/")
        or extension in audio_extensions
    ):
        return jsonify({
            "success": False,
            "error": "The completed download is not recognized as an audio file."
        }), 415

    mime_type = provided_mime if provided_mime.startswith("audio/") else guessed_mime
    if not mime_type.startswith("audio/"):
        mime_type = "audio/octet-stream"

    size = os.path.getsize(source_path)
    if size <= 0:
        return jsonify({
            "success": False,
            "error": "The downloaded audio file is empty."
        }), 400

    download_key = str(download_id)
    items = load_items()
    duplicate = next((
        item for item in items
        if item.get("type") == "audio"
        and str(item.get("browser_download_id")) == download_key
    ), None)
    if duplicate:
        return jsonify({
            "success": True,
            "duplicate": True,
            "message": "This audio download is already in Stash.",
            "item": duplicate
        })

    audio_dir = os.path.join(LOCAL_STORAGE_DIR, "media", "audio")
    os.makedirs(audio_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(audio_dir, 0o700)
    except OSError:
        pass

    stored_extension = extension if extension in audio_extensions else (
        mimetypes.guess_extension(mime_type, strict=False) or ".audio"
    )
    filename = f"copied_audio_{secrets.token_hex(12)}{stored_extension}"
    destination = os.path.join(audio_dir, filename)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".audio-import-",
        suffix=stored_extension,
        dir=audio_dir,
    )
    os.close(descriptor)
    try:
        shutil.copyfile(source_path, temporary_path)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)
    except OSError as error:
        for path in (temporary_path, destination):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        app.logger.warning("Could not stage downloaded audio: %s", type(error).__name__)
        return jsonify({"success": False, "error": "Stash could not securely save this audio file."}), 500

    item = {
        "type": "audio",
        "content": "",
        "file": os.path.relpath(destination, os.path.dirname(__file__)),
        "url": f"/media/audio/{filename}",
        "original_name": original_name,
        "title": original_name,
        "size": size,
        "mime_type": mime_type,
        "source_url": str(data.get("url") or ""),
        "page_url": str(data.get("page_url") or ""),
        "browser_download_id": download_key,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    try:
        item = save_metadata_with_next_id(item)
    except Exception as error:
        try:
            if os.path.exists(destination):
                os.remove(destination)
        except OSError:
            pass
        app.logger.warning("Could not save downloaded audio metadata: %s", type(error).__name__)
        return jsonify({"success": False, "error": "Stash could not securely save this audio file."}), 500

    return jsonify({
        "success": True,
        "message": "Downloaded audio copied into Stash.",
        "type": "audio",
        "item": item
    })


@stash_route("/api/browser-copy", methods=["POST", "OPTIONS"])
def browser_copy():

    # Handle browser CORS preflight request
    if request.method == "OPTIONS":
        return "", 204

    if (
        request.headers.get("X-Copy-Maker-Type") == "video"
        and not _browser_video_copy_allowed()
    ):
        return jsonify({
            "success": False,
            "code": "video_copy_disabled",
            "error": "Video copying is off in Stash Settings. Turn on Allow video copying to use Copy with Stash.",
        }), 403

    # =========================================================
    # =========================================================
    # DIRECT BINARY AUDIO UPLOAD
    # =========================================================

    if request.headers.get("X-Copy-Maker-Type") == "audio":
        mime_type = (
            request.headers.get("Content-Type")
            or "application/octet-stream"
        ).split(";", 1)[0].strip().lower()

        media_url = request.headers.get("X-Copy-Maker-URL", "")[:4000]
        page_url = request.headers.get("X-Copy-Maker-Page", "")[:4000]
        title = request.headers.get("X-Copy-Maker-Title", "")[:240]

        if request.content_length == 0:
            return jsonify({
                "success": False,
                "error": "Empty audio received."
            }), 400
        if request.content_length is not None and request.content_length > MAX_UPLOAD_BYTES:
            return jsonify({"success": False, "error": "This audio file is larger than Stash allows."}), 413

        allowed_extensions = {
            ".aac", ".aif", ".aiff", ".amr", ".flac", ".m4a",
            ".mid", ".midi", ".mp2", ".mp3", ".mpga", ".oga",
            ".ogg", ".opus", ".wav", ".wma"
        }

        url_path = media_url.split("?", 1)[0].split("#", 1)[0]
        url_extension = os.path.splitext(url_path)[1].lower()

        if (
            not mime_type.startswith("audio/")
            and url_extension not in allowed_extensions
        ):
            return jsonify({
                "success": False,
                "error": "The response is not recognized as audio."
            }), 415

        extension = url_extension
        if extension not in allowed_extensions:
            extension = mimetypes.guess_extension(
                mime_type, strict=False
            ) or ""

        if extension not in allowed_extensions:
            mime_extensions = {
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/x-m4a": ".m4a",
                "audio/wav": ".wav",
                "audio/x-wav": ".wav",
                "audio/ogg": ".ogg",
                "audio/flac": ".flac",
                "audio/aac": ".aac",
                "audio/opus": ".opus",
                "audio/midi": ".mid"
            }
            extension = mime_extensions.get(mime_type, "")

        if extension not in allowed_extensions:
            return jsonify({
                "success": False,
                "error": "Could not determine a supported audio format."
            }), 415

        audio_dir = os.path.join(LOCAL_STORAGE_DIR, "media", "audio")
        os.makedirs(audio_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(audio_dir, 0o700)
        except OSError:
            pass

        filename = f"copied_audio_{secrets.token_hex(12)}{extension}"
        destination = os.path.join(audio_dir, filename)
        temporary_path = os.path.join(audio_dir, f".upload-{secrets.token_hex(16)}.tmp")
        try:
            audio_size, _ = _save_request_body(temporary_path)
            if not audio_size:
                return jsonify({"success": False, "error": "Empty audio received."}), 400
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, destination)
        except OverflowError:
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass
            return jsonify({"success": False, "error": "This audio file is larger than Stash allows."}), 413
        except OSError:
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass
            return jsonify({"success": False, "error": "Stash could not save this audio file."}), 500

        item = {
            "type": "audio",
            "content": "",
            "file": os.path.relpath(
                destination, os.path.dirname(__file__)
            ),
            "url": "/media/audio/" + filename,
            "original_name": title or filename,
            "title": title or filename,
            "size": audio_size,
            "mime_type": mime_type,
            "source_url": media_url,
            "page_url": page_url,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }

        try:
            item = save_metadata_with_next_id(item)
        except Exception as error:
            for path in (temporary_path, destination):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            app.logger.warning("Could not save uploaded audio metadata: %s", type(error).__name__)
            return jsonify({"success": False, "error": "Stash could not securely save this audio file."}), 500

        return jsonify({
            "success": True,
            "message": "Audio copied directly into Stash.",
            "type": "audio",
            "item": item
        })

    # DIRECT BINARY VIDEO UPLOAD
    # =========================================================
    # Browser sends video Blob directly instead of Base64 JSON.

    if (
        request.method == "POST"
        and request.headers.get("X-Copy-Maker-Type") == "video"
    ):
        mime_type = (
            request.headers.get("Content-Type")
            or "video/webm"
        )[:200]

        media_url = request.headers.get(
            "X-Copy-Maker-URL",
            ""
        )[:4000]

        page_url = request.headers.get(
            "X-Copy-Maker-Page",
            ""
        )[:4000]

        title = request.headers.get(
            "X-Copy-Maker-Title",
            ""
        )[:240]

        expected_clipboard_change_count = request.headers.get(
            "X-Copy-Maker-Clipboard-Change-Count"
        )
        pending_item_id = request.headers.get("X-Copy-Maker-Item-ID") or None
        pending_item = None
        if pending_item_id:
            try:
                pending_item_id = int(pending_item_id)
            except (TypeError, ValueError, OverflowError):
                return jsonify({"success": False, "error": "This video capture is invalid."}), 400
            pending_item = next(
                (item for item in load_items() if str(item.get("id")) == str(pending_item_id)),
                None,
            )
            if (
                pending_item is None
                or pending_item.get("type") != "video"
                or pending_item.get("capture_status") not in {"downloading", "capturing", "saving"}
            ):
                return jsonify({"success": False, "error": "This pending video is no longer in Stash."}), 409

        print("\n🌐 BROWSER MEDIA COPIED")
        print("------------------------")
        print("Type: video")
        # Media URLs can contain signed credentials and page titles may be
        # sensitive, so keep those values out of local logs.

        print("\n🎬 DIRECT VIDEO PIPELINE")
        print("------------------------")
        if request.content_length == 0:
            return jsonify({
                "success": False,
                "error": "Empty video received"
            }), 400
        if request.content_length is not None and request.content_length > MAX_UPLOAD_BYTES:
            return jsonify({"success": False, "error": "This video file is larger than Stash allows."}), 413

        # Older extension copies may upload a video without sending the
        # pre-capture clipboard snapshot. Since this endpoint is reached by
        # the user's explicit Stash copy action, use the clipboard state at
        # upload arrival as a fallback, then keep the normal change-count
        # check while the saved file is added to the clipboard.
        if not expected_clipboard_change_count:
            try:
                expected_clipboard_change_count = get_clipboard_change_count()
            except Exception as error:
                expected_clipboard_change_count = None
                print(
                    "⚠️ Could not read clipboard state at video upload:",
                    type(error).__name__
                )

            if expected_clipboard_change_count is not None:
                print(
                    "📋 No pre-capture snapshot was supplied; "
                    "recorded clipboard state when upload arrived."
                )

        video_dir = os.path.join(LOCAL_STORAGE_DIR, "videos")

        os.makedirs(video_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(video_dir, 0o700)
        except OSError:
            pass

        temporary_path = os.path.join(video_dir, f".upload-{secrets.token_hex(16)}.tmp")
        try:
            total, incoming_hash = _save_request_body(temporary_path)
        except OverflowError:
            return jsonify({"success": False, "error": "This video file is larger than Stash allows."}), 413
        except OSError:
            app.logger.exception("Could not write incoming browser video to Stash storage.")
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass
            return jsonify({"success": False, "error": "Stash could not save this video file."}), 500
        if not total:
            return jsonify({"success": False, "error": "Empty video received"}), 400

        if request.headers.get("X-Copy-Maker-Direct-Source") == "1":
            try:
                expected_duration = float(request.headers.get("X-Copy-Maker-Expected-Duration", ""))
            except (TypeError, ValueError):
                expected_duration = 0
            actual_duration = get_video_duration_seconds(temporary_path)
            duration_is_valid = math.isfinite(expected_duration) and expected_duration > 0
            minimum_complete_size = (
                max(8 * 1024, int(expected_duration * 8 * 1024))
                if duration_is_valid
                else 0
            )
            duration_mismatch = (
                not duration_is_valid
                or actual_duration is None
                or abs(actual_duration - expected_duration) > max(1.5, expected_duration * 0.08)
            )
            if duration_mismatch or total < minimum_complete_size:
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass
                return jsonify({
                    "success": False,
                    "code": "incomplete_video_source",
                    "error": "That source did not contain a complete, playable video.",
                }), 422

        print("Browser video bytes received.")
        print("MIME:", mime_type)
        print("Size:", total, "bytes")

        # =========================================================
        # DUPLICATE VIDEO CHECK
        # =========================================================
        # Identify an exact byte-for-byte duplicate before creating
        # another file or another clipboard-library item.

        items = load_items()

        for existing_item in items:
            if not isinstance(existing_item, dict) or existing_item.get("type") != "video":
                continue
            if (
                pending_item_id is not None
                and str(existing_item.get("id")) == str(pending_item_id)
            ):
                continue

            existing_file = existing_item.get("file")

            if not existing_file:
                continue

            existing_path = os.path.join(
                os.path.dirname(__file__),
                existing_file
            )

            if not os.path.isfile(existing_path):
                continue

            is_duplicate, calculated_hash = _existing_video_match(
                existing_item,
                existing_path,
                incoming_hash,
            )
            current_item = existing_item
            if existing_item.get("id") is not None and calculated_hash is not None:
                updated = update_item(
                    existing_item.get("id"),
                    {"source_sha256": calculated_hash},
                )
                if updated is not None:
                    current_item = updated
            if not is_duplicate:
                continue

            print("♻️ DUPLICATE VIDEO DETECTED")
            print("Existing Item ID:", existing_item.get("id"))

            clipboard_published = publish_video_file_to_clipboard(
                existing_path,
                expected_clipboard_change_count
            )

            if pending_item_id is not None:
                delete_item(pending_item_id)

            try:
                os.remove(temporary_path)
            except OSError:
                pass

            return jsonify({
                "success": True,
                "duplicate": True,
                "clipboard_published": clipboard_published,
                "message": "Video already exists in Stash",
                "type": "video",
                "url": current_item.get("url", ""),
                "file": current_item.get("file", existing_file),
                "size": current_item.get("size", total),
                "mime_type": current_item.get("mime_type", mime_type),
                "item": current_item,
                "compatibility_warning": None,
            })

        extension = ".webm"
        source_extension = os.path.splitext(urlparse(media_url).path)[1].lower()
        if source_extension in {".mp4", ".m4v", ".mov", ".webm"}:
            extension = source_extension
        elif "mp4" in mime_type:
            extension = ".mp4"
        elif "quicktime" in mime_type:
            extension = ".mov"

        filename = (
            "copied_video_"
            + str(int(time.time() * 1000))
            + "_"
            + secrets.token_hex(4)
            + extension
        )

        destination = os.path.join(
            video_dir,
            filename
        )

        encrypted_temporary_path = destination + ".encrypted.tmp"
        try:
            encrypt_media_file(temporary_path, encrypted_temporary_path)
            os.replace(encrypted_temporary_path, destination)
            os.remove(temporary_path)
        except Exception:
            for candidate in (temporary_path, encrypted_temporary_path):
                try:
                    os.remove(candidate)
                except OSError:
                    pass
            return jsonify({"success": False, "error": "Stash could not finish saving this video."}), 500

        stored_mime_type = mime_type
        stored_size = total

        # ==========================================
        # ADD VIDEO TO CLIPBOARD LIBRARY
        # ==========================================

        browser_url = "/videos/" + os.path.basename(destination)

        item = {
            "type": "video",
            "content": "",
            "file": os.path.relpath(
                destination,
                os.path.dirname(__file__)
            ),
            "url": browser_url,
            "original_name": title or filename,
            "size": stored_size,
            "mime_type": stored_mime_type,
            "source_sha256": incoming_hash,
            "source_url": media_url,
            "page_url": page_url,
            "title": title,
            "capture_status": "ready",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }

        if pending_item_id is not None:
            item["id"] = pending_item_id
            item = update_item(pending_item_id, item)
            if item is None:
                try:
                    os.remove(destination)
                except OSError:
                    pass
                return jsonify({"success": False, "error": "This pending video was removed before it finished saving."}), 409
        else:
            item = save_metadata_with_next_id(item)
            item_id = item["id"]

        clipboard_published = publish_video_file_to_clipboard(
            destination,
            expected_clipboard_change_count
        )

        print("✅ VIDEO SAVED")
        print("Size:", total, "bytes")
        print("📋 VIDEO ADDED TO CLIPBOARD LIBRARY")
        print("Item ID:", item_id)

        return jsonify({
            "success": True,
            "clipboard_published": clipboard_published,
            "message": "Browser video captured successfully",
            "type": "video",
            "url": browser_url,
            "file": destination,
            "size": stored_size,
            "mime_type": stored_mime_type,
            "compatibility_warning": None,
            "item": item
        })

    # =========================================================
    # EXISTING JSON PIPELINE
    # =========================================================

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "error": "No data received"
        }), 400

    media_type = data.get("type") if isinstance(data.get("type"), str) else ""
    media_url = data.get("url") if isinstance(data.get("url"), str) else ""
    page_url = data.get("page_url") if isinstance(data.get("page_url"), str) else ""
    title = data.get("title") if isinstance(data.get("title"), str) else ""
    media_url = media_url[:4000]
    page_url = page_url[:4000]
    title = title[:240]

    print("\n🌐 BROWSER MEDIA COPIED")
    print("------------------------")
    print("Type:", media_type or "unknown")
    print("Browser copy metadata received; sensitive URLs and titles are not written to logs.")

    # =================================
    # VIDEO PIPELINE
    # =================================

    if media_type == "video":

        print("\n🎬 VIDEO PIPELINE")
        print("------------------------")

        # ---------------------------------
        # PATH 1: Browser-captured video
        # ---------------------------------

        video_bytes = data.get("video_bytes")
        mime_type = data.get("mime_type") or "video/webm"

        if video_bytes:

            print("Browser video bytes received.")
            print("MIME:", mime_type)

            try:
                video_dir = os.path.join(LOCAL_STORAGE_DIR, "videos")

                os.makedirs(video_dir, exist_ok=True)

                # Browser sends captured video as Base64 text.
                # Decode it back into real binary video bytes.
                import base64

                if isinstance(video_bytes, str):
                    raw_bytes = base64.b64decode(video_bytes)
                elif isinstance(video_bytes, list):
                    raw_bytes = bytes(video_bytes)
                else:
                    raw_bytes = bytes(video_bytes)

                extension = ".webm"

                if "mp4" in mime_type:
                    extension = ".mp4"
                elif "quicktime" in mime_type:
                    extension = ".mov"

                filename = "copied_video_" + str(int(time.time() * 1000))
                filename += extension

                destination = os.path.join(
                    video_dir,
                    filename
                )

                with open(destination, "wb") as video_file:
                    video_file.write(raw_bytes)

                encrypt_file_in_place(destination)

                total = len(raw_bytes)

                print("✅ VIDEO SAVED")
                print("Size:", total, "bytes")

                return jsonify({
                    "success": True,
                    "message": "Browser video captured successfully",
                    "type": "video",
                    "url": media_url,
                    "file": destination,
                    "size": total,
                    "mime_type": mime_type
                })

            except Exception as error:

                print("❌ VIDEO SAVE ERROR:", type(error).__name__)

                return jsonify({
                    "success": False,
                    "error": "Stash could not save this video."
                }), 500

        # ---------------------------------
        # PATH 2: Direct video URL
        # ---------------------------------

        if media_url and not media_url.startswith("blob:"):

            print("Direct video URL detected.")
            print("Downloading media into Stash storage...")

            if not _is_public_http_url(media_url):
                return jsonify({
                    "success": False,
                    "error": "Only public HTTP or HTTPS media links can be downloaded."
                }), 400

            session = None
            response = None
            destination = None
            try:

                video_dir = os.path.join(LOCAL_STORAGE_DIR, "videos")

                os.makedirs(video_dir, mode=0o700, exist_ok=True)
                try:
                    os.chmod(video_dir, 0o700)
                except OSError:
                    pass

                parsed = urlparse(media_url)

                filename = os.path.basename(parsed.path)

                if not filename:
                    filename = "copied_video.mp4"

                filename = "".join(
                    c for c in filename
                    if c.isalnum() or c in "._-"
                )

                if not filename:
                    filename = "copied_video.mp4"

                # Prevent accidental overwrite.
                name, ext = os.path.splitext(filename)

                if not ext:
                    ext = ".mp4"

                filename = (
                    name + "_" +
                    str(int(time.time() * 1000)) +
                    "_" + secrets.token_hex(4) +
                    ext
                )

                destination = os.path.join(
                    video_dir,
                    filename
                )

                session, response = _open_public_media_url(media_url, page_url)

                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type and not (
                    content_type.startswith("video/")
                    or content_type == "application/octet-stream"
                ):
                    raise ValueError("The public link did not return a video file.")
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_UPLOAD_BYTES:
                    raise OverflowError("The video file is larger than Stash allows.")

                total = 0

                with open(destination, "xb") as video_file:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):

                        if chunk:
                            total += len(chunk)
                            if total > MAX_UPLOAD_BYTES:
                                raise OverflowError("The video file is larger than Stash allows.")
                            video_file.write(chunk)

                encrypt_file_in_place(destination)

                if total == 0:
                    raise ValueError("The media link returned an empty file.")

                print("✅ VIDEO SAVED")
                print("Size:", total, "bytes")

                return jsonify({
                    "success": True,
                    "message": "Direct video copied successfully",
                    "type": "video",
                    "url": media_url,
                    "file": destination,
                    "size": total
                })

            except OverflowError:
                if destination and os.path.exists(destination):
                    os.remove(destination)
                return jsonify({"success": False, "error": "The video file is larger than Stash allows."}), 413
            except (ValueError, requests.RequestException) as error:
                if destination and os.path.exists(destination):
                    os.remove(destination)
                print("⚠️ Video download rejected or unavailable:", type(error).__name__)
                return jsonify({"success": False, "error": "Stash could not safely download that public video link."}), 502
            except Exception as error:
                if destination and os.path.exists(destination):
                    os.remove(destination)
                print("❌ VIDEO DOWNLOAD ERROR:", type(error).__name__)

                return jsonify({
                    "success": False,
                    "error": "Stash could not save that video."
                }), 500
            finally:
                if response is not None:
                    response.close()
                if session is not None:
                    session.close()

        # ---------------------------------
        # Unsupported blob/stream
        # ---------------------------------

        print("⚠️ Video has no usable captured bytes.")

        return jsonify({
            "success": False,
            "error": "Video stream requires browser capture",
            "url": media_url
        }), 400

    # =================================
    # OTHER BROWSER MEDIA
    # =================================

    return jsonify({
        "success": True,
        "message": "Media received by Stash",
        "type": media_type,
        "url": media_url
    })


@stash_route("/api/clipboard", methods=["GET"])
def get_clipboard_items():
    try:
        items = load_items()

        # Add inferred sections to older copies in the API response without
        # rewriting the user's saved clipboard history.
        if isinstance(items, list):
            enriched_items = []
            for item in items:
                if isinstance(item, dict) and item.get("trashed_at"):
                    continue
                mode = (
                    infer_workspace_mode(item)
                    if isinstance(item, dict)
                    and not item.get("workspace_mode")
                    and not item.get("workspace_mode_checked")
                    else None
                )
                if mode and not item.get("workspace_mode"):
                    item = {**item, "workspace_mode": mode}
                enriched_items.append(item)
            items = enriched_items

        return jsonify(items)

    except Exception as error:
        return jsonify({
            "success": False,
            "error": "Stash could not read the saved clipboard items."
        }), 500


@stash_route("/api/clipboard/mobile", methods=["POST", "OPTIONS"])
def import_mobile_clipboard_text():

    if request.method == "OPTIONS":
        return "", 204

    if request.content_length and request.content_length > 1_048_576:
        return jsonify({
            "success": False,
            "error": "Clipboard text is too large to save."
        }), 413

    data = request.get_json(silent=True)
    text_content = data.get("text") if isinstance(data, dict) else None

    if not isinstance(text_content, str) or not text_content.strip():
        return jsonify({
            "success": False,
            "error": "Copy some text before saving it to Stash."
        }), 400

    if len(text_content.encode("utf-8")) > 1_048_576:
        return jsonify({
            "success": False,
            "error": "Clipboard text is too large to save."
        }), 413

    destination = route_copied_text(text_content, source="phone clipboard")
    if destination == "blocked":
        text_content = ""
        return jsonify({
            "success": False,
            "destination": "vault",
            "message": "This looks sensitive, but the Vault is locked or unavailable. Stash discarded it. Unlock the Vault, then copy it again.",
        }), 423
    if destination == "vault":
        return jsonify({
            "success": True,
            "destination": "vault",
            "message": "Sensitive copy saved in the encrypted Vault.",
        }), 201

    item = save_item("text", text_content)

    return jsonify({
        "success": True,
        "message": "Copied text saved to Stash.",
        "item": item
    }), 201


@stash_route("/api/video-capture-start", methods=["POST", "OPTIONS"])
def video_capture_start():

    if request.method == "OPTIONS":
        return "", 204

    if not _browser_video_copy_allowed():
        return jsonify({
            "success": False,
            "code": "video_copy_disabled",
            "error": "Video copying is off in Stash Settings. Turn on Allow video copying to use Copy with Stash.",
        }), 403

    data = request.get_json(silent=True)
    if isinstance(data, dict):
        if data.get("create_pending") is True:
            try:
                change_count = get_clipboard_change_count()
            except Exception:
                change_count = None

            title = str(data.get("title") or "Video copy")[:240]
            media_url = str(data.get("url") or "")[:4000]
            page_url = str(data.get("page_url") or "")[:4000]
            mime_type = str(data.get("mime_type") or "")[:200]
            item = {
                "type": "video",
                "content": "",
                "original_name": title,
                "title": title,
                "source_url": media_url,
                "page_url": page_url,
                "mime_type": mime_type,
                "capture_status": "downloading",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            item = save_metadata_with_next_id(item)
            return jsonify({
                "success": True,
                "item_id": item["id"],
                "clipboard_change_count": change_count,
            })

        if data.get("item_id") is not None:
            try:
                item_id = int(data.get("item_id"))
            except (TypeError, ValueError, OverflowError):
                return jsonify({"success": False, "error": "This video capture is invalid."}), 400
            status = str(data.get("status") or "")
            if status not in {"downloading", "capturing", "saving"}:
                return jsonify({"success": False, "error": "This video status is invalid."}), 400
            current = next(
                (item for item in load_items() if str(item.get("id")) == str(item_id)),
                None,
            )
            if current is None or current.get("type") != "video" or current.get("capture_status") not in {
                "downloading", "capturing", "saving"
            }:
                return jsonify({"success": False, "error": "This pending video is no longer in Stash."}), 404
            update_item(item_id, {"capture_status": status})
            return jsonify({"success": True, "item_id": item_id, "status": status})

        if data.get("cancel_item_id") is not None:
            try:
                item_id = int(data.get("cancel_item_id"))
            except (TypeError, ValueError, OverflowError):
                return jsonify({"success": False, "error": "This video capture is invalid."}), 400
            current = next(
                (item for item in load_items() if str(item.get("id")) == str(item_id)),
                None,
            )
            if current and current.get("type") == "video" and current.get("capture_status") in {
                "downloading", "capturing", "saving"
            }:
                delete_item(item_id)
            return jsonify({"success": True})

    change_count = get_clipboard_change_count()

    if change_count is None:
        return jsonify({
            "success": False,
            "error": "The macOS clipboard is unavailable."
        }), 503

    return jsonify({
        "success": True,
        "clipboard_change_count": change_count
    })
