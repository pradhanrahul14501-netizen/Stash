import tempfile
import unittest
import json
import time
from pathlib import Path
from unittest.mock import patch

import storage_manager
from ava import agent, conversation_state, file_actions, unified_search


class AvaMultiTurnStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stash-ava-chat-")
        self.root = Path(self.temp.name)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        self.storage_patches = [
            patch.object(storage_manager, name, str(self.storage / filename))
            for name, filename in {
                "BASE_DIR": self.root,
                "STORAGE_DIR": self.storage,
                "MEDIA_DIR": self.storage / "media",
                "STORAGE_FILE": self.storage / "clipboard.json",
                "LIBRARY_LOCK_FILE": self.storage / ".clipboard.lock",
                "ITEM_ID_COUNTER_FILE": self.storage / ".next_item_id",
                "FOLDERS_FILE": self.storage / "folders.json",
                "WORKSPACE_MODE_SETTINGS_FILE": self.storage / "workspace_mode_settings.json",
                "PRIVACY_SETTINGS_FILE": self.storage / "privacy_settings.json",
            }.items()
        ]
        for item in self.storage_patches:
            item.start()
        self.file_actions_patch = patch.object(file_actions, "STORAGE_DIR", str(self.storage))
        self.file_actions_patch.start()
        self.addCleanup(self._cleanup)
        conversation_state.clear_all()

    def _cleanup(self):
        conversation_state.clear_all()
        for item in reversed(self.storage_patches):
            item.stop()
        self.temp.cleanup()

    def add_item(self, item_type, title):
        return storage_manager.save_metadata_with_next_id({
            "type": item_type,
            "title": title,
            "content": f"fixture {title}",
        })

    def test_saved_here_search_is_stash_only(self):
        self.add_item("file", "notes.pdf")
        with patch.object(unified_search, "spotlight_search") as spotlight:
            result = agent.run("find all files saved here", conversation_id="search-chat")

        spotlight.assert_not_called()
        self.assertEqual(result["search_context"]["places"], "stash")
        self.assertEqual(result["source_counts"]["stash"], 1)
        self.assertEqual([item["source"] for item in result["results"]], ["stash"])

    def test_create_folder_and_move_all_files_requires_one_confirmation(self):
        first = self.add_item("file", "one.pdf")
        second = self.add_item("file", "two.txt")
        self.add_item("text", "a note")

        preview = agent.run(
            "create a folder named flexo and save all the files there",
            conversation_id="folder-chat",
        )
        self.assertIn("2 files", preview["message"])
        self.assertIn("Yes / No", preview["message"])
        self.assertEqual(storage_manager.load_stash_folders(), ["flexo"])
        self.assertNotIn("folder_name", storage_manager.load_items()[0])

        moved = agent.run("yes", conversation_id="folder-chat")
        self.assertIn("Moved 2 files", moved["message"])
        items = {item["id"]: item for item in storage_manager.load_items()}
        self.assertEqual(items[first["id"]]["folder_name"], "flexo")
        self.assertEqual(items[second["id"]]["folder_name"], "flexo")
        self.assertNotEqual(items[3]["folder_name"] if "folder_name" in items[3] else None, "flexo")

    def test_split_folder_move_and_all_items_follow_up_keeps_target(self):
        self.add_item("file", "one.pdf")
        self.add_item("text", "two")
        conversation_id = "split-folder-chat"

        found = agent.run("find all items saved here", conversation_id=conversation_id)
        self.assertEqual(found["source_counts"], {"stash": 2, "mac": 0})
        created = agent.run("create folder flexo", conversation_id=conversation_id)
        self.assertIn("flexo", created["message"].casefold())
        preview = agent.run("put all the files there", conversation_id=conversation_id)
        self.assertIn("Move 1 file", preview["message"])
        revised = agent.run("all the items", conversation_id=conversation_id)
        self.assertIn("Move 2 items", revised["message"])
        moved = agent.run("yes", conversation_id=conversation_id)
        self.assertIn("Moved 2 items", moved["message"])
        self.assertEqual(
            {item.get("folder_name") for item in storage_manager.load_items()},
            {"flexo"},
        )

    def test_three_turn_create_move_all_items_without_a_search(self):
        self.add_item("file", "one.pdf")
        self.add_item("text", "two")
        conversation_id = "three-turn-folder-chat"

        created = agent.run("create folder flexo", conversation_id=conversation_id)
        self.assertIn("Created the Stash folder", created["message"])
        preview = agent.run("put all the files there", conversation_id=conversation_id)
        self.assertIn("Move 1 file", preview["message"])
        expanded = agent.run("all the items", conversation_id=conversation_id)
        self.assertIn("Move 2 items", expanded["message"])
        moved = agent.run("yes", conversation_id=conversation_id)

        self.assertIn("Moved 2 items", moved["message"])
        self.assertEqual(
            {item.get("folder_name") for item in storage_manager.load_items()},
            {"flexo"},
        )

    def test_ten_folder_phrasings_create_stash_folders_without_finder_access(self):
        prompts = [
            "create a folder named flexo",
            "make a new Stash folder called flexo",
            "create folder flexo here in Stash",
            "new folder named flexo in my library",
            "please make folder flexo in Stash",
            "create a folder here in Stash named flexo",
            "add a Stash folder called flexo",
            "make folder flexo in my library",
            "create folder named flexo for my saved items",
            "I want a new folder in Stash called flexo",
        ]
        created_names = []
        for index, prompt in enumerate(prompts):
            name = f"folder-{index}"
            with self.subTest(prompt=prompt):
                result = agent.run(prompt.replace("flexo", name), conversation_id=f"create-variant-{index}")
                self.assertTrue(result["success"])
                self.assertNotIn("Connect a folder", result["message"])
                created_names.append(name)
        self.assertEqual(set(storage_manager.load_stash_folders()), set(created_names))

    def test_bulk_delete_uses_stash_bin_and_yes_confirms(self):
        one = self.add_item("file", "one.pdf")
        two = self.add_item("file", "two.pdf")
        note = self.add_item("text", "keep this note")

        preview = agent.run("delete all the files", conversation_id="delete-chat")
        self.assertIn("Delete 2 items from Stash?", preview["message"])
        self.assertIn("one.pdf", preview["message"])
        self.assertIn("Yes / No", preview["message"])
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items()))

        deleted = agent.run("yes", conversation_id="delete-chat")
        self.assertIn("Moved 2 items to Stash Trash", deleted["message"])
        items = {item["id"]: item for item in storage_manager.load_items()}
        self.assertTrue(items[one["id"]].get("trashed_at"))
        self.assertTrue(items[two["id"]].get("trashed_at"))
        self.assertFalse(items[note["id"]].get("trashed_at"))

    def test_pending_confirmation_survives_memory_restart(self):
        saved = self.add_item("file", "restart.pdf")
        conversation_id = "restart-confirmation-chat"
        preview = agent.run("delete all files", conversation_id=conversation_id)
        self.assertIn("Reply Yes / No", preview["message"])

        conversation_state.clear_all(preserve_disk=True)
        confirmed = agent.run("yes", conversation_id=conversation_id)

        self.assertIn("Moved 1 item to Stash Trash", confirmed["message"])
        restored = next(item for item in storage_manager.load_items() if item["id"] == saved["id"])
        self.assertTrue(restored.get("trashed_at"))

    def test_expired_confirmation_repreviews_and_requires_a_second_yes(self):
        saved = self.add_item("file", "expired.pdf")
        conversation_id = "expired-confirmation-chat"
        agent.run("delete all files", conversation_id=conversation_id)
        state_path = self.storage / "ava_sessions" / f"{conversation_id}.json"
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        payload["updated_at"] = time.time() - conversation_state._CONVERSATION_TTL_SECONDS - 1
        state_path.write_text(json.dumps(payload), encoding="utf-8")
        conversation_state.clear_all(preserve_disk=True)

        refreshed = agent.run("yes", conversation_id=conversation_id)
        self.assertTrue(refreshed.get("repreviewed"))
        self.assertIn("I lost track of that, here's a fresh preview", refreshed["message"])
        current = next(item for item in storage_manager.load_items() if item["id"] == saved["id"])
        self.assertFalse(current.get("trashed_at"))

        confirmed = agent.run("yes", conversation_id=conversation_id)
        self.assertIn("Moved 1 item to Stash Trash", confirmed["message"])
        current = next(item for item in storage_manager.load_items() if item["id"] == saved["id"])
        self.assertTrue(current.get("trashed_at"))

    def test_missing_confirmation_state_uses_history_to_show_a_fresh_preview(self):
        saved = self.add_item("file", "missing-state.pdf")
        conversation_id = "missing-confirmation-state-chat"
        preview = agent.run("delete all files", conversation_id=conversation_id)
        history = [
            {"role": "user", "content": "delete all files"},
            {"role": "assistant", "content": preview["message"]},
        ]
        conversation_state.clear_all()

        refreshed = agent.run("yes", history=history, conversation_id=conversation_id)
        self.assertTrue(refreshed.get("repreviewed"))
        self.assertIn("I lost track of that, here's a fresh preview", refreshed["message"])
        current = next(item for item in storage_manager.load_items() if item["id"] == saved["id"])
        self.assertFalse(current.get("trashed_at"))

    def test_yes_without_pending_action_is_a_noop(self):
        self.add_item("file", "keep.pdf")
        with patch.object(storage_manager, "update_item") as update_item:
            result = agent.run("yes", conversation_id="no-pending-action-chat")
        self.assertIn("no pending Stash action", result["message"])
        self.assertIn("Nothing was changed", result["message"])
        update_item.assert_not_called()
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items()))

    def test_search_results_survive_memory_restart(self):
        self.add_item("file", "one.pdf")
        self.add_item("text", "plain note")
        conversation_id = "restart-search-chat"
        agent.run("find all items saved here", conversation_id=conversation_id)
        conversation_state.clear_all(preserve_disk=True)

        filtered = agent.run("only text", conversation_id=conversation_id)
        self.assertEqual(filtered["source_counts"]["stash"], 1)
        self.assertEqual(filtered["results"][0]["name"], "plain note")

    def test_target_folder_survives_memory_restart(self):
        self.add_item("file", "folder-persist.pdf")
        conversation_id = "restart-folder-chat"
        agent.run("create folder flexo", conversation_id=conversation_id)
        conversation_state.clear_all(preserve_disk=True)

        preview = agent.run("put all files there", conversation_id=conversation_id)
        self.assertIn("Move 1 file", preview["message"])
        self.assertIn("flexo", preview["message"])

    def test_stash_bulk_delete_dry_run_never_changes_library_metadata(self):
        self.add_item("file", "dry-delete.pdf")
        conversation_id = "dry-delete-chat"
        before = Path(storage_manager.STORAGE_FILE).read_bytes()
        preview = agent.run("delete all files", conversation_id=conversation_id, dry_run=True)
        result = agent.run("yes", conversation_id=conversation_id)

        self.assertIn("Reply Yes / No", preview["message"])
        self.assertTrue(result.get("dry_run"))
        self.assertIn("Nothing was changed", result["message"])
        self.assertEqual(Path(storage_manager.STORAGE_FILE).read_bytes(), before)
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items(read_only=True)))

    def test_stash_bulk_move_dry_run_never_changes_library_metadata(self):
        self.add_item("file", "dry-move.pdf")
        storage_manager.create_stash_folder("dryrun-destination")
        conversation_id = "dry-move-chat"
        before = Path(storage_manager.STORAGE_FILE).read_bytes()
        preview = agent.run("put all files in dryrun-destination", conversation_id=conversation_id, dry_run=True)
        result = agent.run("yes", conversation_id=conversation_id)

        self.assertIn("Reply Yes / No", preview["message"])
        self.assertTrue(result.get("dry_run"))
        self.assertIn("Nothing was changed", result["message"])
        self.assertEqual(Path(storage_manager.STORAGE_FILE).read_bytes(), before)
        self.assertNotIn("folder_name", storage_manager.load_items(read_only=True)[0])

    def test_unresolved_duplicate_request_never_expands_to_all_stash_items(self):
        self.add_item("file", "one.pdf")
        self.add_item("text", "note")

        result = agent.run("delete all my duplicates", conversation_id="duplicate-delete-chat")

        self.assertIn("refused to delete anything", result["message"].casefold())
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items()))

    def test_no_all_things_expands_pending_delete_scope_without_acting(self):
        self.add_item("file", "one.pdf")
        self.add_item("text", "two")
        conversation_id = "delete-all-chat"

        agent.run("delete all files", conversation_id=conversation_id)
        revised = agent.run("no, all things", conversation_id=conversation_id)
        self.assertIn("Delete 2 items from Stash?", revised["message"])
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items()))
        agent.run("yes", conversation_id=conversation_id)
        self.assertTrue(all(item.get("trashed_at") for item in storage_manager.load_items()))

    def test_typed_no_cancels_pending_bulk_delete(self):
        self.add_item("file", "one.pdf")
        conversation_id = "cancel-delete-chat"
        agent.run("delete all files", conversation_id=conversation_id)
        cancelled = agent.run("no", conversation_id=conversation_id)
        self.assertTrue(cancelled["cancelled"])
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items()))

    def test_all_answers_a_prior_delete_clarification(self):
        self.add_item("file", "one.pdf")
        conversation_id = "clarified-delete-chat"

        question = agent.run("delete that", conversation_id=conversation_id)
        self.assertTrue(question.get("needs_clarification"))
        preview = agent.run("all", conversation_id=conversation_id)
        self.assertIn("Delete 1 item from Stash?", preview["message"])
        self.assertIn("Yes / No", preview["message"])

    def test_folder_name_and_freeform_reply_are_answers_before_search_routing(self):
        result = agent.run("create a folder here in Stash", conversation_id="folder-name-chat")
        self.assertTrue(result.get("needs_clarification"))
        self.assertIn("name the folder", result["message"].casefold())

        answered = agent.run("ava text test", conversation_id="folder-name-chat")
        self.assertIn("ava text test", answered["message"].casefold())
        self.assertEqual(storage_manager.load_stash_folders(), ["ava text test"])

    def test_repeated_clarification_is_rephrased_instead_of_repeated(self):
        conversation_id = "repeat-question-chat"
        first = agent.run("delete that", conversation_id=conversation_id)
        repeated = agent.run("delete that", conversation_id=conversation_id)
        self.assertTrue(first.get("needs_clarification"))
        self.assertTrue(repeated.get("needs_clarification"))
        self.assertNotEqual(first["message"], repeated["message"])

    def test_delete_all_mac_path_is_refused_without_touching_stash_or_disk(self):
        item = self.add_item("file", "keep.pdf")
        result = agent.run(
            "delete all files in ~/Documents",
            conversation_id="mac-path-delete-chat",
        )
        self.assertIn("only remove its saved copies", result["message"])
        self.assertFalse(storage_manager.load_items()[0].get("trashed_at"))
        self.assertEqual(item["title"], storage_manager.load_items()[0]["title"])

    def test_mac_file_results_are_never_included_in_stash_delete(self):
        conversation_id = "mac-delete-chat"
        with patch.object(unified_search, "spotlight_search", return_value={
            "results": [{"source": "mac", "name": "outside.pdf", "path": "/Users/test/outside.pdf"}],
            "available": True,
            "permission_blocked": False,
        }):
            result = agent.run("find files on my Mac", conversation_id=conversation_id)
        self.assertEqual(result["source_counts"]["mac"], 1)
        response = agent.run("delete all the files", conversation_id=conversation_id)
        self.assertIn("Stash can only remove its saved copies", response["message"])

    def test_spotlight_search_excludes_development_junk(self):
        self.assertTrue(unified_search._excluded_search_path("/Users/test/project/.venv/lib/site-packages/a.py"))
        self.assertTrue(unified_search._excluded_search_path("/Users/test/project/node_modules/a.js"))
        self.assertTrue(unified_search._excluded_search_path("/Users/test/project/.git/config"))
        self.assertFalse(unified_search._excluded_search_path("/Users/test/Documents/notes.txt"))

    def test_ten_folder_phrasings_are_recognized_as_stash_folders(self):
        prompts = [
            "create a folder named flexo",
            "make a new Stash folder called flexo",
            "create folder flexo here in Stash",
            "new folder named flexo in my library",
            "please make folder flexo in Stash",
            "create a folder here in Stash named flexo",
            "add a Stash folder called flexo",
            "make folder flexo in my library",
            "create folder named flexo for my saved items",
            "I want a new folder in Stash called flexo",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                intent = agent._parse_stash_folder_request(prompt)
                self.assertEqual(intent["name"], "flexo")

    def test_ten_move_all_phrasings_resolve_target_folder(self):
        prompts = [
            "put all the files there",
            "move all files into flexo",
            "save every file in that folder",
            "move all items there",
            "put all copies into flexo",
            "save all the files there",
            "move everything to that folder",
            "place all items in flexo",
            "put every file in the folder",
            "move all the items into that folder",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIsNotNone(agent._parse_stash_move_all_request(prompt, "flexo"))

    def test_ten_move_all_phrasings_make_a_stash_preview(self):
        storage_manager.create_stash_folder("flexo")
        self.add_item("file", "one.pdf")
        self.add_item("text", "note")
        prompts = [
            "put all the files there",
            "move all files into flexo",
            "save every file in that folder",
            "move all items there",
            "put all copies into flexo",
            "save all the files there",
            "move everything to that folder",
            "place all items in flexo",
            "put every file in the folder",
            "move all the items into that folder",
        ]
        for index, prompt in enumerate(prompts):
            with self.subTest(prompt=prompt):
                conversation_id = f"move-variant-{index}"
                agent.run("create folder flexo", conversation_id=conversation_id)
                result = agent.run(prompt, conversation_id=conversation_id)
                self.assertIn("Move ", result["message"])
                self.assertIn("Yes / No", result["message"])


    def test_ten_delete_all_phrasings_are_recognized_as_stash_bulk_delete(self):
        prompts = [
            "delete all the files",
            "remove all files from Stash",
            "delete all items",
            "trash every file",
            "delete everything in Stash",
            "remove all things from my library",
            "delete every saved copy",
            "erase all the items here",
            "delete all files in my stash",
            "trash all my saved files",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIsNotNone(agent._parse_stash_bulk_delete_request(prompt))

    def test_ten_delete_all_phrasings_make_a_stash_preview(self):
        self.add_item("file", "one.pdf")
        self.add_item("text", "note")
        prompts = [
            "delete all the files",
            "remove all files from Stash",
            "delete all items",
            "trash every file",
            "delete everything in Stash",
            "remove all things from my library",
            "delete every saved copy",
            "erase all the items here",
            "delete all files in my stash",
            "trash all my saved files",
        ]
        for index, prompt in enumerate(prompts):
            with self.subTest(prompt=prompt):
                result = agent.run(prompt, conversation_id=f"delete-variant-{index}")
                expected_count = 1 if "file" in prompt.casefold() or "files" in prompt.casefold() else 2
                expected_noun = "item" if expected_count == 1 else "items"
                self.assertIn(f"Delete {expected_count} {expected_noun} from Stash?", result["message"])
                self.assertIn("Yes / No", result["message"])
        self.assertFalse(any(item.get("trashed_at") for item in storage_manager.load_items()))


if __name__ == "__main__":
    unittest.main()
