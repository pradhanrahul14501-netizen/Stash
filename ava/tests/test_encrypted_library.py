import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import library_security
import storage_manager
from ava import tools
import database
from integrations.cursor import server as cursor_server


class AvaEncryptedLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="ava-library-")
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        self._patches = [
            patch.object(storage_manager, "BASE_DIR", str(self.root)),
            patch.object(storage_manager, "STORAGE_DIR", str(self.storage)),
            patch.object(storage_manager, "MEDIA_DIR", str(self.storage / "media")),
            patch.object(storage_manager, "STORAGE_FILE", str(self.storage / "clipboard.json")),
            patch.object(storage_manager, "LIBRARY_LOCK_FILE", str(self.storage / ".clipboard.lock")),
            patch.object(storage_manager, "ITEM_ID_COUNTER_FILE", str(self.storage / ".next_item_id")),
            patch.object(storage_manager, "FOLDERS_FILE", str(self.storage / "folders.json")),
            patch.object(
                storage_manager,
                "WORKSPACE_MODE_SETTINGS_FILE",
                str(self.storage / "workspace_mode_settings.json"),
            ),
            patch.object(
                storage_manager,
                "PRIVACY_SETTINGS_FILE",
                str(self.storage / "privacy_settings.json"),
            ),
            patch.object(library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _write_encrypted_library(self, items):
        raw = library_security.encrypt_json(items)
        Path(storage_manager.STORAGE_FILE).write_bytes(raw)
        return raw

    def test_ava_reads_and_updates_encrypted_library(self):
        items = [
            {
                "id": 41,
                "type": "text",
                "content": "encrypted fixture phrase",
                "created_at": "2026-10-20T10:00:00",
            }
        ]
        self._write_encrypted_library(items)

        self.assertEqual(tools.search_library(query="fixture", limit=None), items)

        self.assertTrue(tools.organize_items(query="fixture")["success"])
        saved_raw = Path(storage_manager.STORAGE_FILE).read_bytes()
        saved_items, encrypted = library_security.decrypt_json(saved_raw)
        self.assertTrue(encrypted)
        self.assertEqual(saved_items[0]["organized_category"], "text")

        with patch.object(database, "DATABASE_FILE", self.storage / "copy_maker.db"):
            database.create_database()
            database.import_clipboard()
            with closing(sqlite3.connect(database.DATABASE_FILE)) as connection:
                row = connection.execute(
                    "SELECT id, type FROM items WHERE id = ?", ("41",)
                ).fetchone()
        self.assertEqual(row, ("41", "text"))

    def test_ava_organization_preserves_items_saved_after_its_read(self):
        original = [{
            "id": 41,
            "type": "text",
            "content": "organize this fixture",
        }]
        self._write_encrypted_library(original)
        original_load = tools.load_library
        inserted = False

        def load_then_insert():
            nonlocal inserted
            snapshot = original_load()
            if not inserted:
                inserted = True
                storage_manager.save_metadata_with_next_id({
                    "type": "text",
                    "content": "concurrent save",
                })
            return snapshot

        with patch.object(tools, "load_library", side_effect=load_then_insert):
            tools.organize_items(query="organize this")

        saved_items = storage_manager.load_items()
        self.assertEqual(len(saved_items), 2)
        self.assertEqual(saved_items[0]["organized_category"], "text")
        self.assertEqual(saved_items[1]["content"], "concurrent save")

    def test_ava_delete_preserves_items_saved_after_its_read(self):
        self._write_encrypted_library([{
            "id": 41,
            "type": "text",
            "content": "delete this fixture",
        }])
        original_load = tools.load_library
        inserted = False

        def load_then_insert():
            nonlocal inserted
            snapshot = original_load()
            if not inserted:
                inserted = True
                storage_manager.save_metadata_with_next_id({
                    "type": "text",
                    "content": "concurrent save",
                })
            return snapshot

        with patch.object(tools, "load_library", side_effect=load_then_insert):
            result = tools.delete_library_item(41)

        self.assertTrue(result["success"])
        saved_items = storage_manager.load_items()
        self.assertEqual(len(saved_items), 1)
        self.assertEqual(saved_items[0]["content"], "concurrent save")

    def test_cursor_lists_and_searches_encrypted_library_without_rewriting_it(self):
        items = [{"id": 52, "type": "text", "content": "cursor encrypted fixture"}]
        original = self._write_encrypted_library(items)

        listed = json.loads(cursor_server.list_items({"limit": 10}))
        found = json.loads(cursor_server.search_text({"query": "encrypted"}))

        self.assertEqual(listed[0]["id"], 52)
        self.assertEqual(found[0]["id"], 52)
        self.assertEqual(Path(storage_manager.STORAGE_FILE).read_bytes(), original)

    def test_cursor_reports_library_decryption_errors(self):
        Path(storage_manager.STORAGE_FILE).write_bytes(
            library_security.JSON_MAGIC + b"invalid encrypted data"
        )

        with self.assertRaisesRegex(ValueError, "encrypted Stash library"):
            cursor_server.read_items()


if __name__ == "__main__":
    unittest.main()
