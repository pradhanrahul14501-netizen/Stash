"""Encrypted Vault routes."""

from routes._shared import bind_routes

stash_route = bind_routes(globals())


@stash_route("/api/vault/status", methods=["GET"])
def vault_status():
    try:
        return jsonify(get_vault_status())
    except Exception as error:
        app.logger.warning("Could not read Vault status: %s", type(error).__name__)
        return jsonify({"error": "Stash could not read the Vault status."}), 500


@stash_route("/api/vault/setup", methods=["POST"])
def vault_setup():
    data = request.get_json(silent=True) or {}
    password = data.get("password") if isinstance(data, dict) else None
    confirmation = data.get("confirmation") if isinstance(data, dict) else None
    if not isinstance(password, str) or password != confirmation:
        return jsonify({"error": "Enter the same Vault password twice."}), 400
    try:
        result = create_vault(password)
        return jsonify({"success": True, **result})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not create Vault: %s", type(error).__name__)
        return jsonify({"error": "Stash could not create the encrypted Vault."}), 500


@stash_route("/api/vault/unlock", methods=["POST"])
def vault_unlock():
    data = request.get_json(silent=True) or {}
    password = data.get("password") if isinstance(data, dict) else None
    try:
        result = unlock_vault(password)
        return jsonify({"success": True, **result})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not unlock Vault: %s", type(error).__name__)
        return jsonify({"error": "Stash could not unlock the Vault."}), 500


@stash_route("/api/vault/lock", methods=["POST"])
def vault_lock():
    try:
        lock_vault()
        return jsonify({"success": True})
    except Exception as error:
        app.logger.warning("Could not lock Vault: %s", type(error).__name__)
        return jsonify({"error": "Stash could not lock the Vault."}), 500


@stash_route("/api/vault/settings", methods=["POST"])
def vault_settings():
    data = request.get_json(silent=True) or {}
    minutes = data.get("idle_lock_minutes") if isinstance(data, dict) else None
    try:
        saved_minutes = set_idle_lock_minutes(minutes)
        return jsonify({"success": True, "idle_lock_minutes": saved_minutes})
    except VaultLockedError as error:
        return jsonify({"error": str(error)}), 423
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not update Vault lock setting: %s", type(error).__name__)
        return jsonify({"error": "Stash could not save the Vault lock setting."}), 500


@stash_route("/api/vault/entries", methods=["GET", "POST"])
def vault_entries():
    if request.method == "GET":
        try:
            return jsonify({"entries": list_vault_entries()})
        except VaultLockedError as error:
            return jsonify({"error": str(error)}), 423
        except Exception as error:
            app.logger.warning("Could not read Vault entries: %s", type(error).__name__)
            return jsonify({"error": "Stash could not read the encrypted Vault."}), 500

    data = request.get_json(silent=True) or {}
    title = data.get("title") if isinstance(data, dict) else None
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, str) or len(content.encode("utf-8")) > 1_048_576:
        return jsonify({"error": "Add text under 1 MB to save in the Vault."}), 400
    try:
        entry_id = add_vault_entry(title, content, source="manual")
        return jsonify({"success": True, "id": entry_id}), 201
    except VaultLockedError as error:
        return jsonify({"error": str(error)}), 423
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not save Vault entry: %s", type(error).__name__)
        return jsonify({"error": "Stash could not encrypt this Vault entry."}), 500


@stash_route("/api/vault/entries/<entry_id>", methods=["GET", "DELETE"])
def vault_entry(entry_id):
    try:
        if request.method == "DELETE":
            deleted = delete_vault_entry(entry_id)
            if not deleted:
                return jsonify({"error": "That Vault entry no longer exists."}), 404
            return jsonify({"success": True})
        entry = get_vault_entry(entry_id)
        if entry is None:
            return jsonify({"error": "That Vault entry no longer exists."}), 404
        return jsonify({"entry": entry})
    except VaultLockedError as error:
        return jsonify({"error": str(error)}), 423
    except Exception as error:
        app.logger.warning("Could not open Vault entry: %s", type(error).__name__)
        return jsonify({"error": "Stash could not open this encrypted Vault entry."}), 500


@stash_route("/api/vault/capture-all", methods=["POST"])
def vault_capture_all():
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled") if isinstance(data, dict) else None
    try:
        return jsonify({"success": True, "enabled": set_capture_all_text(enabled)})
    except VaultLockedError as error:
        return jsonify({"error": str(error)}), 423
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Could not change Vault capture setting: %s", type(error).__name__)
        return jsonify({"error": "Stash could not save the Vault capture setting."}), 500


@stash_route("/api/vault/move-library-copy", methods=["POST"])
def move_library_copy_to_vault():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id") if isinstance(data, dict) else None
    try:
        candidate = next(
            (item for item in load_items() if str(item.get("id")) == str(item_id)),
            None,
        )
        if candidate is None or candidate.get("type") != "text" or not isinstance(candidate.get("content"), str):
            return jsonify({"error": "That text copy is no longer in the library."}), 404
        entry_id = add_vault_entry(
            candidate.get("original_name") or "Moved from Library",
            candidate["content"],
            source="moved from library",
        )
        deleted = delete_item(candidate.get("id"))
        if deleted is None:
            delete_vault_entry(entry_id)
            return jsonify({"error": "The library copy changed before it could be moved."}), 409
        return jsonify({"success": True})
    except VaultLockedError as error:
        return jsonify({"error": str(error)}), 423
    except Exception as error:
        app.logger.warning("Could not move library copy to Vault: %s", type(error).__name__)
        return jsonify({"error": "Stash could not move this copy into the encrypted Vault."}), 500
