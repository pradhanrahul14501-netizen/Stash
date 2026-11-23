"""Security controls and encrypted backup routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


def _backup_request_is_local():
    try:
        return (
            ipaddress.ip_address(request.remote_addr or "").is_loopback
            and not request.headers.get("X-Forwarded-Host")
            and is_local_host()
        )
    except ValueError:
        return False


def _backup_rate_limit(bucket, limit, window_seconds):
    retry_after = rate_limit_auth_attempt(bucket, limit, window_seconds)
    if not retry_after:
        return None
    response = jsonify({"error": "Too many backup attempts. Wait a while and try again."})
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


@stash_route("/api/security/status", methods=["GET"])
def security_status():
    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401
    trusted_proxies = trusted_proxy_configured()
    return jsonify({
        "remote_access": "https_proxy_only" if trusted_proxies else "local_network_only",
        "trusted_proxy_configured": trusted_proxies,
        "backup_max_bytes": MAX_BACKUP_BYTES,
    })


@stash_route("/api/security/backup", methods=["POST"])
def download_encrypted_backup():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401
    if not _backup_request_is_local():
        return jsonify({"error": "Create or restore encrypted backups from Stash on this Mac, not from a phone or other device."}), 403
    limited = _backup_rate_limit("security-backup-create", 3, 3600)
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    password = payload.get("password") if isinstance(payload, dict) else None
    try:
        backup_path = create_encrypted_backup(password)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not create encrypted Stash backup: %s", type(error).__name__)
        return jsonify({"error": "Stash could not create the encrypted backup. Check available disk space and try again."}), 500

    response = send_file(
        backup_path,
        as_attachment=True,
        download_name=f"Stash-backup-{time.strftime('%Y-%m-%d')}.stashbackup",
        mimetype="application/octet-stream",
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    response.call_on_close(lambda: _remove_temporary_backup(backup_path))
    return response


def _remove_temporary_backup(path):
    try:
        os.remove(path)
    except OSError:
        pass


@stash_route("/api/security/backup/restore", methods=["POST"])
def stage_encrypted_backup_restore():
    if not request_is_same_origin():
        return jsonify({"error": "This request could not be verified."}), 403
    if not has_authenticated_session():
        return jsonify({"error": "login_required"}), 401
    if not _backup_request_is_local():
        return jsonify({"error": "Create or restore encrypted backups from Stash on this Mac, not from a phone or other device."}), 403
    limited = _backup_rate_limit("security-backup-restore", 3, 3600)
    if limited:
        return limited
    uploaded = request.files.get("backup")
    password = request.form.get("password", "")
    if uploaded is None:
        return jsonify({"error": "Choose a Stash backup file."}), 400
    try:
        result = stage_restore(uploaded.stream, password)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not prepare Stash backup restore: %s", type(error).__name__)
        return jsonify({"error": "Stash could not prepare this restore. Check that the backup and password are correct."}), 500
    return jsonify(result), 202
