import multiprocessing
import hashlib
import tempfile
import threading
import unittest
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch

import auth
import shared_service
import storage_manager
import library_security
from library_security import LibraryEncryptionError
from ava import conversation_state, unified_search
from ava import file_actions


_TEST_ROOT = Path(tempfile.mkdtemp(prefix="copy-maker-tests-"))
_TEST_STORAGE = _TEST_ROOT / "storage"
_TEST_STORAGE.mkdir()
_STORAGE_PATHS = {
    "BASE_DIR": _TEST_ROOT,
    "STORAGE_DIR": _TEST_STORAGE,
    "MEDIA_DIR": _TEST_STORAGE / "media",
    "STORAGE_FILE": _TEST_STORAGE / "clipboard.json",
    "LIBRARY_LOCK_FILE": _TEST_STORAGE / ".clipboard.lock",
    "ITEM_ID_COUNTER_FILE": _TEST_STORAGE / ".next_item_id",
    "FOLDERS_FILE": _TEST_STORAGE / "folders.json",
    "WORKSPACE_MODE_SETTINGS_FILE": _TEST_STORAGE / "workspace_mode_settings.json",
    "PRIVACY_SETTINGS_FILE": _TEST_STORAGE / "privacy_settings.json",
}
_STORAGE_PATCHES = [
    patch.object(storage_manager, name, str(path))
    for name, path in _STORAGE_PATHS.items()
]
for _storage_patch in _STORAGE_PATCHES:
    _storage_patch.start()


# Keep app imports and route tests isolated from live user storage and auth.
with (
    patch.object(auth, "initialize_auth") as _auth_initialization,
    patch.object(shared_service, "shared_service_enabled", return_value=False),
    patch.object(storage_manager, "ensure_encrypted_media_storage") as _storage_migration,
    patch.object(threading.Thread, "start") as _thread_start,
):
    import main as stash_main
    IMPORT_INITIALIZED_AUTH = _auth_initialization.called
    IMPORT_RAN_STORAGE_MIGRATION = _storage_migration.called
    IMPORT_STARTED_THREADS = _thread_start.called


class AvaConfirmationApiTests(unittest.TestCase):
    def setUp(self):
        stash_main.app.config.update(TESTING=True)
        stash_main._AVA_PENDING_FILE_ORGANIZATION.clear()
        stash_main._AVA_PENDING_FILE_COPY.clear()
        stash_main._AVA_PENDING_DELETE.clear()
        stash_main._AVA_PENDING_FILE_ACTION.clear()
        conversation_state.clear_all()
        self.file_storage_patcher = patch.object(file_actions, "STORAGE_DIR", str(_TEST_STORAGE))
        self.file_storage_patcher.start()
        self.addCleanup(self.file_storage_patcher.stop)
        self.addCleanup(file_actions.disconnect_folder)
        self.library_key_patcher = patch.object(
            library_security,
            "_get_key",
            return_value=b"test-library-key-32-bytes-long!!",
        )
        self.library_key_patcher.start()
        self.addCleanup(self.library_key_patcher.stop)
        self.runtime_patcher = patch.object(stash_main, "initialize_local_runtime")
        self.runtime_patcher.start()
        self.addCleanup(self.runtime_patcher.stop)
        self.client = stash_main.app.test_client()

    def test_delete_confirmation_requires_a_preview_token_and_is_one_use(self):
        item = storage_manager.save_metadata_with_next_id({
            "type": "text",
            "title": "temporary delete-gate probe",
            "content": "temporary test data",
        })
        self.addCleanup(storage_manager.delete_item, item["id"])

        with patch.object(stash_main, "ava_run", return_value={
            "success": True,
            "requires_confirmation": True,
            "confirmation_type": "delete_item",
            "message": "Delete temporary delete-gate probe?",
            "item": item,
        }):
            preview = self._post_as_signed_in_user("/api/ava", {"command": "delete the probe"})

        self.assertEqual(preview.status_code, 200)
        token = preview.get_json()["confirmation_token"]
        self.assertTrue(token)

        bypass = self._post_as_signed_in_user(
            "/api/ava/confirm-delete", {"item_id": item["id"]}
        )
        self.assertEqual(bypass.status_code, 400)
        self.assertTrue(any(
            str(saved.get("id")) == str(item["id"])
            for saved in storage_manager.load_items()
        ))

        wrong_item = self._post_as_signed_in_user(
            "/api/ava/confirm-delete",
            {"item_id": item["id"] + 1, "confirmation_token": token},
        )
        self.assertEqual(wrong_item.status_code, 400)
        self.assertTrue(any(
            str(saved.get("id")) == str(item["id"])
            for saved in storage_manager.load_items()
        ))

        confirmed = self._post_as_signed_in_user(
            "/api/ava/confirm-delete",
            {"item_id": item["id"], "confirmation_token": token},
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(confirmed.get_json()["success"])
        self.assertFalse(any(
            str(saved.get("id")) == str(item["id"])
            for saved in storage_manager.load_items()
        ))

        repeated = self._post_as_signed_in_user(
            "/api/ava/confirm-delete",
            {"item_id": item["id"], "confirmation_token": token},
        )
        self.assertEqual(repeated.status_code, 400)

    def test_delete_confirmation_can_be_cancelled_without_deleting(self):
        item = storage_manager.save_metadata_with_next_id({
            "type": "text",
            "title": "temporary delete-cancel probe",
            "content": "temporary test data",
        })
        self.addCleanup(storage_manager.delete_item, item["id"])

        with patch.object(stash_main, "ava_run", return_value={
            "success": True,
            "requires_confirmation": True,
            "confirmation_type": "delete_item",
            "message": "Delete temporary delete-cancel probe?",
            "item": item,
        }):
            preview = self._post_as_signed_in_user("/api/ava", {"command": "delete the probe"})

        token = preview.get_json()["confirmation_token"]
        cancelled = self._post_as_signed_in_user(
            "/api/ava/confirm-delete",
            {"confirmation_token": token, "cancel": True},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertTrue(cancelled.get_json()["cancelled"])
        self.assertTrue(any(
            str(saved.get("id")) == str(item["id"])
            for saved in storage_manager.load_items()
        ))

        repeated = self._post_as_signed_in_user(
            "/api/ava/confirm-delete",
            {"item_id": item["id"], "confirmation_token": token},
        )
        self.assertEqual(repeated.status_code, 400)

    def test_typed_no_clears_a_pending_delete_preview(self):
        token = "temporary-delete-cancel-token"
        stash_main._AVA_PENDING_DELETE[token] = {
            "item_id": "123",
            "expires_at": stash_main.time.monotonic() + 600,
        }

        response = self._post_as_signed_in_user(
            "/api/ava",
            {
                "command": "No",
                "history": [{
                    "role": "assistant",
                    "content": "Delete quarterly-report.txt? I’ll wait for your confirmation.",
                }],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["cancelled"])
        self.assertNotIn(token, stash_main._AVA_PENDING_DELETE)

    def test_ava_api_keeps_bulk_delete_confirmation_scoped_to_chat(self):
        file_item = storage_manager.save_metadata_with_next_id({
            "type": "file", "title": "temporary multi-turn delete.pdf",
        })
        note = storage_manager.save_metadata_with_next_id({
            "type": "text", "title": "temporary note",
        })
        conversation_id = "api-bulk-delete-chat"

        preview = self._post_as_signed_in_user("/api/ava", {
            "command": "delete all files",
            "conversation_id": conversation_id,
        })
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Delete 1 item from Stash?", preview.get_json()["message"])
        self.assertNotIn("_conversation_refs", preview.get_json())

        confirmed = self._post_as_signed_in_user("/api/ava", {
            "command": "yes",
            "conversation_id": conversation_id,
        })
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.get_json()["deleted_count"], 1)
        items = {item["id"]: item for item in storage_manager.load_items()}
        self.assertTrue(items[file_item["id"]].get("trashed_at"))
        self.assertFalse(items[note["id"]].get("trashed_at"))

    def test_ava_folder_access_can_connect_and_disconnect_only_via_same_origin(self):
        with tempfile.TemporaryDirectory(prefix="ava-folder-access-") as temporary_directory:
            folder = Path(temporary_directory)
            connected = self._post_as_signed_in_user(
                "/api/ava/folder-access", {"folder": str(folder)}
            )
            self.assertEqual(connected.status_code, 200)
            self.assertTrue(connected.get_json()["connected"])
            self.assertEqual(file_actions.connected_root(), folder.resolve())

            with (
                patch.object(stash_main, "has_authenticated_session", return_value=True),
                patch.object(stash_main, "request_is_same_origin", return_value=False),
            ):
                denied = self.client.post("/api/ava/folder-access", json={"disconnect": True})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(file_actions.connected_root(), folder.resolve())

            disconnected = self._post_as_signed_in_user(
                "/api/ava/folder-access", {"disconnect": True}
            )
            self.assertEqual(disconnected.status_code, 200)
            self.assertFalse(disconnected.get_json()["connected"])
            self.assertIsNone(file_actions.connected_root(required=False))

    def test_physical_delete_confirmation_moves_only_the_previewed_file_to_trash(self):
        with tempfile.TemporaryDirectory(prefix="ava-delete-action-") as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "quarterly-report.txt"
            source.write_text("fixture only", encoding="utf-8")
            file_actions.connect_folder(str(folder))

            preview = self._post_as_signed_in_user(
                "/api/ava", {"command": "remove quarterly-report.txt"}
            )
            self.assertEqual(preview.status_code, 200)
            data = preview.get_json()
            self.assertEqual(data["confirmation_type"], "file_action")
            self.assertEqual(
                [item["path"] for item in data["file_action_preview"]["items"]],
                ["quarterly-report.txt"],
            )
            self.assertNotIn("signature", data["file_action_preview"]["items"][0])
            self.assertNotIn("root", data["file_action_preview"])
            self.assertTrue(source.is_file())

            confirmed = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm",
                {"confirmation_token": data["confirmation_token"]},
            )
            self.assertEqual(confirmed.status_code, 200)
            self.assertFalse(source.exists())
            self.assertEqual([row["path"] for row in file_actions.trash_listing()], ["quarterly-report.txt"])

            repeated = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm",
                {"confirmation_token": data["confirmation_token"]},
            )
            self.assertEqual(repeated.status_code, 400)

            undo_preview = self._post_as_signed_in_user(
                "/api/ava", {"command": "undo last action"}
            ).get_json()
            self.assertEqual(undo_preview["file_action_preview"]["operation"], "undo")
            undo = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm",
                {"confirmation_token": undo_preview["confirmation_token"]},
            )
            self.assertEqual(undo.status_code, 200)
            self.assertTrue(source.is_file())
            self.assertIn("quarterly-report.txt", undo.get_json()["restored"])

    def test_physical_file_action_cancel_consumes_token_without_changing_files(self):
        with tempfile.TemporaryDirectory(prefix="ava-cancel-action-") as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "short-notes.md"
            source.write_text("fixture only", encoding="utf-8")
            file_actions.connect_folder(str(folder))
            preview = self._post_as_signed_in_user(
                "/api/ava", {"command": "delete short-notes.md"}
            ).get_json()
            token = preview["confirmation_token"]

            cancelled = self._post_as_signed_in_user(
                "/api/ava/file-action/cancel", {"confirmation_token": token}
            )
            repeated = self._post_as_signed_in_user(
                "/api/ava/file-action/cancel", {"confirmation_token": token}
            )
            self.assertEqual(cancelled.status_code, 200)
            self.assertTrue(source.is_file())
            self.assertEqual(repeated.status_code, 400)

    def test_silent_file_action_preview_expires_without_changing_any_file(self):
        with tempfile.TemporaryDirectory(prefix="ava-expired-action-") as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "short-notes.md"
            source.write_text("fixture only", encoding="utf-8")
            file_actions.connect_folder(str(folder))
            preview = self._post_as_signed_in_user(
                "/api/ava", {"command": "delete short-notes.md"}
            ).get_json()
            stash_main._AVA_PENDING_FILE_ACTION[preview["confirmation_token"]]["expires_at"] = (
                stash_main.time.monotonic() - 1
            )

            expired = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm",
                {"confirmation_token": preview["confirmation_token"]},
            )
            self.assertEqual(expired.status_code, 400)
            self.assertTrue(source.is_file())
            self.assertIn("expired", expired.get_json()["message"].casefold())

    def test_typed_no_cancels_a_file_action_preview(self):
        token = "temporary-file-action-cancel-token"
        stash_main._AVA_PENDING_FILE_ACTION[token] = {
            "plan": {"operation": "delete", "items": []},
            "expires_at": stash_main.time.monotonic() + 300,
        }
        response = self._post_as_signed_in_user(
            "/api/ava",
            {
                "command": "No",
                "history": [{
                    "role": "assistant",
                    "content": "Preview: move report.txt to Archive/report.txt? Confirm or cancel.",
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["cancelled"])
        self.assertNotIn(token, stash_main._AVA_PENDING_FILE_ACTION)

    def test_import_does_not_migrate_storage_or_start_workers(self):
        self.assertFalse(IMPORT_INITIALIZED_AUTH)
        self.assertFalse(IMPORT_RAN_STORAGE_MIGRATION)
        self.assertFalse(IMPORT_STARTED_THREADS)
        self.assertEqual(Path(storage_manager.STORAGE_DIR), _TEST_STORAGE)

    def test_capture_search_and_open_smoke_flow_uses_encrypted_temp_library(self):
        phrase = "Stash isolated release smoke phrase"
        temporary_directory = tempfile.TemporaryDirectory(prefix="capture-search-open-")
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        storage = root / "storage"
        storage.mkdir()
        paths = {
            "BASE_DIR": root,
            "STORAGE_DIR": storage,
            "MEDIA_DIR": storage / "media",
            "STORAGE_FILE": storage / "clipboard.json",
            "LIBRARY_LOCK_FILE": storage / ".clipboard.lock",
            "ITEM_ID_COUNTER_FILE": storage / ".next_item_id",
            "FOLDERS_FILE": storage / "folders.json",
            "WORKSPACE_MODE_SETTINGS_FILE": storage / "workspace_mode_settings.json",
            "PRIVACY_SETTINGS_FILE": storage / "privacy_settings.json",
        }
        with ExitStack() as stack:
            stack.enter_context(patch.object(stash_main, "LOCAL_STORAGE_DIR", str(storage)))
            stack.enter_context(patch.object(
                library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"
            ))
            for name, path in paths.items():
                stack.enter_context(patch.object(storage_manager, name, str(path)))
            stack.enter_context(patch.object(
                unified_search,
                "spotlight_search",
                return_value={"results": [], "available": True, "permission_blocked": False},
            ))
            captured = self._post_as_signed_in_user(
                "/api/clipboard/mobile", {"text": phrase}
            )
            self.assertEqual(captured.status_code, 201)
            item = captured.get_json()["item"]

            searched = self._post_as_signed_in_user(
                "/api/ava", {"command": "find " + phrase}
            )
            self.assertEqual(searched.status_code, 200)
            result = searched.get_json()
            self.assertTrue(result["success"])
            self.assertTrue(any(
                str(match.get("id")) == str(item["id"])
                for match in result.get("results", [])
            ))

            opened = self._post_as_signed_in_user(
                "/api/ava/search-action",
                {"action": "open", "source": "stash", "item_id": item["id"]},
            )

        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.get_json()["open_text"], phrase)

    def test_runtime_initializes_auth_and_storage_before_worker(self):
        self.runtime_patcher.stop()
        calls = []
        with (
            patch.object(stash_main, "_LOCAL_RUNTIME_INITIALIZED", False),
            patch.object(stash_main, "initialize_auth", side_effect=lambda app: calls.append("auth")),
            patch.object(stash_main, "shared_service_enabled", return_value=False),
            patch.object(stash_main, "ensure_encrypted_media_storage", side_effect=lambda: calls.append("migration")),
            patch.object(stash_main, "_cleanup_stale_video_conversions", side_effect=lambda: calls.append("temp_cleanup")),
            patch.object(stash_main, "clear_legacy_auto_delete_schedules", return_value=0),
            patch.object(stash_main, "_start_privacy_worker", side_effect=lambda: calls.append("worker")),
        ):
            stash_main.initialize_local_runtime()
        self.assertEqual(calls, ["auth", "migration", "temp_cleanup", "worker"])

    def test_concurrent_pending_video_captures_get_unique_ids(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="pending-video-ids-")
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        storage = root / "storage"
        storage.mkdir()
        setting_file = storage / "browser_video_copy_setting.json"
        setting_file.write_text('{"enabled": true}', encoding="utf-8")
        paths = {
            "BASE_DIR": root,
            "STORAGE_DIR": storage,
            "MEDIA_DIR": storage / "media",
            "STORAGE_FILE": storage / "clipboard.json",
            "LIBRARY_LOCK_FILE": storage / ".clipboard.lock",
            "ITEM_ID_COUNTER_FILE": storage / ".next_item_id",
            "FOLDERS_FILE": storage / "folders.json",
            "WORKSPACE_MODE_SETTINGS_FILE": storage / "workspace_mode_settings.json",
            "PRIVACY_SETTINGS_FILE": storage / "privacy_settings.json",
        }

        def create_pending(index):
            with stash_main.app.test_request_context(
                "/api/video-capture-start",
                method="POST",
                json={
                    "create_pending": True,
                    "title": f"Concurrent video {index}",
                    "url": f"https://example.test/{index}.mp4",
                },
            ):
                return stash_main.video_capture_start().get_json()

        with ExitStack() as stack:
            stack.enter_context(patch.object(stash_main, "_BROWSER_VIDEO_COPY_SETTING_FILE", str(setting_file)))
            stack.enter_context(patch.object(library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"))
            for name, path in paths.items():
                stack.enter_context(patch.object(storage_manager, name, str(path)))
            with ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(create_pending, range(24)))
            with patch.object(library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"):
                saved_items = storage_manager.load_items()

        ids = [result["item_id"] for result in results]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(saved_items), len(ids))

    def test_processes_allocate_unique_ids_and_deletions_do_not_reuse_them(self):
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(4)
        results = context.Queue()
        with patch.object(library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"):
            processes = [
                context.Process(target=_save_library_item_process, args=(barrier, results, index))
                for index in range(4)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
            ids = [results.get(timeout=2) for _ in processes]

            self.assertTrue(all(process.exitcode == 0 for process in processes))
            self.assertEqual(len(ids), len(set(ids)), f"child process item IDs were not unique: {ids!r}")
            highest_id = max(ids)
            self.assertIsNotNone(storage_manager.delete_item(highest_id))
            next_item = storage_manager.save_metadata_with_next_id({
                "type": "text",
                "content": "after deletion",
            })
            self.assertGreater(next_item["id"], highest_id)

    def test_concurrent_audio_uploads_get_unique_ids(self):
        temporary_directory = tempfile.TemporaryDirectory(prefix="audio-id-race-")
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        storage = root / "storage"
        storage.mkdir()
        paths = {
            "BASE_DIR": root,
            "STORAGE_DIR": storage,
            "MEDIA_DIR": storage / "media",
            "STORAGE_FILE": storage / "clipboard.json",
            "LIBRARY_LOCK_FILE": storage / ".clipboard.lock",
            "ITEM_ID_COUNTER_FILE": storage / ".next_item_id",
            "FOLDERS_FILE": storage / "folders.json",
            "WORKSPACE_MODE_SETTINGS_FILE": storage / "workspace_mode_settings.json",
            "PRIVACY_SETTINGS_FILE": storage / "privacy_settings.json",
        }
        barrier = threading.Barrier(2)
        original_load_items = stash_main.load_items

        def synchronized_load_items():
            items = original_load_items()
            barrier.wait(timeout=5)
            return items

        def upload(index):
            with stash_main.app.test_request_context(
                "/api/browser-copy",
                method="POST",
                data=f"audio payload {index}".encode(),
                headers={
                    "X-Copy-Maker-Type": "audio",
                    "X-Copy-Maker-URL": f"https://example.test/{index}.mp3",
                    "X-Copy-Maker-Page": "https://example.test/",
                    "X-Copy-Maker-Title": f"Audio {index}",
                    "Content-Type": "audio/mpeg",
                },
            ):
                return stash_main.browser_copy()

        with ExitStack() as stack:
            stack.enter_context(patch.object(stash_main, "__file__", str(root / "main.py")))
            stack.enter_context(patch.object(stash_main, "load_items", side_effect=synchronized_load_items))
            stack.enter_context(patch.object(library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"))
            for name, path in paths.items():
                stack.enter_context(patch.object(storage_manager, name, str(path)))
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(upload, range(2)))

        self.assertEqual([response.status_code for response in responses], [200, 200])
        ids = [response.get_json()["item"]["id"] for response in responses]
        self.assertEqual(len(ids), len(set(ids)))

    def test_duplicate_check_verifies_matches_and_skips_known_nonmatches(self):
        digest = hashlib.sha256(b"video bytes").hexdigest()
        with patch.object(stash_main, "iter_decrypted_media") as read_media:
            self.assertEqual(
                stash_main._existing_video_match(
                    {"source_sha256": "a" * 64}, "unused-path", digest
                ),
                (False, None),
            )
            read_media.assert_not_called()

        with patch.object(
            stash_main,
            "iter_decrypted_media",
            return_value=iter([b"video bytes"]),
        ):
            self.assertEqual(
                stash_main._existing_video_match(
                    {"source_sha256": digest}, "match-path", digest
                ),
                (True, None),
            )

        with patch.object(
            stash_main,
            "iter_decrypted_media",
            side_effect=LibraryEncryptionError("damaged video"),
        ):
            self.assertEqual(
                stash_main._existing_video_match(
                    {"source_sha256": digest}, "damaged-path", digest
                ),
                (False, None),
            )

    def _post_as_signed_in_user(self, path, json):
        with (
            patch.object(stash_main, "has_authenticated_session", return_value=True),
            patch.object(stash_main, "request_is_same_origin", return_value=True),
        ):
            return self.client.post(path, json=json)

    def _organization_preview(self, folder):
        file_actions.connect_folder(str(folder))
        response = self._post_as_signed_in_user(
            "/api/ava", {"command": f"Sort the files by type in {folder}"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["requires_confirmation"])
        self.assertTrue(data.get("confirmation_token"))
        return data

    def test_cancel_keeps_files_in_place_and_consumes_token(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "report.txt"
            source.write_text("keep me here", encoding="utf-8")
            preview = self._organization_preview(folder)
            token = preview["confirmation_token"]

            cancelled = self._post_as_signed_in_user(
                "/api/ava/file-action/cancel", {"confirmation_token": token}
            )
            repeated = self._post_as_signed_in_user(
                "/api/ava/file-action/cancel", {"confirmation_token": token}
            )

            self.assertEqual(cancelled.status_code, 200)
            self.assertTrue(cancelled.get_json()["success"])
            self.assertTrue(source.is_file())
            self.assertFalse((folder / "Documents").exists())
            self.assertEqual(repeated.status_code, 400)

    def test_confirm_organizes_preview_and_token_is_one_use(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "report.txt"
            source.write_text("approved by preview", encoding="utf-8")
            preview = self._organization_preview(folder)
            token = preview["confirmation_token"]

            confirmed = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm", {"confirmation_token": token},
            )
            repeated = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm", {"confirmation_token": token}
            )

            self.assertEqual(confirmed.status_code, 200)
            self.assertTrue(confirmed.get_json()["success"])
            self.assertEqual([item["path"] for item in confirmed.get_json()["completed"]], ["report.txt"])
            self.assertFalse(source.exists())
            self.assertTrue((folder / "Documents" / "report.txt").is_file())
            self.assertEqual(repeated.status_code, 400)

    def test_confirm_rejects_file_changed_after_preview(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "report.txt"
            source.write_text("before", encoding="utf-8")
            preview = self._organization_preview(folder)
            source.write_text("changed after preview", encoding="utf-8")

            confirmed = self._post_as_signed_in_user(
                "/api/ava/file-action/confirm",
                {"confirmation_token": preview["confirmation_token"]},
            )
            data = confirmed.get_json()

            self.assertEqual(confirmed.status_code, 200)
            self.assertEqual(data["completed"], [])
            self.assertIn("changed since preview", data["skipped"][0]["reason"])
            self.assertTrue(source.is_file())
            self.assertFalse((folder / "Documents").exists())

    def test_confirm_copy_keeps_original_and_token_is_one_use(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            file_actions.connect_folder(str(root))
            source_folder = root / "source"
            destination_folder = root / "destination"
            source_folder.mkdir()
            source = source_folder / "today.txt"
            source.write_text("copy me", encoding="utf-8")
            response = self._post_as_signed_in_user(
                "/api/ava",
                {
                    "command": (
                        f"Copy today's files from {source_folder} "
                        f"to {destination_folder}"
                    )
                },
            )
            preview = response.get_json()
            token = preview["confirmation_token"]

            confirmed = self._post_as_signed_in_user(
                "/api/ava/confirm-copy-files", {"confirmation_token": token}
            )
            repeated = self._post_as_signed_in_user(
                "/api/ava/confirm-copy-files", {"confirmation_token": token}
            )

            copied = destination_folder / date.today().isoformat() / source.name
            self.assertEqual(response.status_code, 200)
            self.assertTrue(preview["requires_confirmation"])
            self.assertEqual(confirmed.status_code, 200)
            self.assertTrue(confirmed.get_json()["success"])
            self.assertTrue(source.is_file())
            self.assertTrue(copied.is_file())
            self.assertEqual(repeated.status_code, 400)


def _save_library_item_process(barrier, results, index):
    try:
        barrier.wait(timeout=10)
        item = storage_manager.save_metadata_with_next_id({
            "type": "text",
            "content": f"process item {index}",
        })
        results.put(item["id"])
    except Exception as error:
        results.put(f"{type(error).__name__}: {error}")


if __name__ == "__main__":
    unittest.main()
