import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ava import agent, file_actions


class FilePreviewSafetyTests(unittest.TestCase):
    def test_organize_request_only_previews_moves(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory) / "Downloads"
            folder.mkdir()
            file_actions.connect_folder(str(folder))
            document = folder / "report.pdf"
            hidden_file = folder / ".private.txt"
            document.write_text("sample report", encoding="utf-8")
            hidden_file.write_text("hidden", encoding="utf-8")

            with patch.object(agent, "ask_qwen") as ask_qwen:
                result = agent.run("Organize files by type")

            self.assertTrue(result["success"])
            self.assertTrue(result["requires_confirmation"])
            self.assertEqual(result["confirmation_type"], "file_action")
            self.assertEqual(len(result["file_action_preview"]["items"]), 1)
            self.assertEqual(
                result["file_action_preview"]["items"][0]["path"], "report.pdf",
            )
            self.assertTrue(document.is_file())
            self.assertTrue(hidden_file.is_file())
            self.assertFalse((folder / "Documents").exists())
            ask_qwen.assert_not_called()

    def test_copy_today_request_only_previews_copies(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            file_actions.connect_folder(str(root))
            source_file = source / "today.txt"
            hidden_file = source / ".hidden.txt"
            source_file.write_text("keep the original", encoding="utf-8")
            hidden_file.write_text("hidden", encoding="utf-8")
            today = date.today().isoformat()

            with patch.object(agent, "ask_qwen") as ask_qwen:
                result = agent.run(
                    f"Copy today's files from {source} to {destination}"
                )

            self.assertTrue(result["success"])
            self.assertTrue(result["requires_confirmation"])
            self.assertEqual(result["confirmation_type"], "copy_files")
            preview = result["file_copy_preview"]
            self.assertEqual(preview["date"], today)
            self.assertEqual(preview["count"], 1)
            self.assertEqual(preview["moves"][0]["file"], "today.txt")
            self.assertTrue(source_file.is_file())
            self.assertTrue(hidden_file.is_file())
            self.assertFalse(destination.exists())
            ask_qwen.assert_not_called()

    def test_copy_request_without_paths_asks_for_them(self):
        with patch.object(agent, "ask_qwen") as ask_qwen:
            result = agent.run("Copy today's files")

        self.assertTrue(result["success"])
        self.assertTrue(result["needs_file_copy_paths"])
        self.assertIn("source folder", result["message"])
        self.assertIn("destination folder", result["message"])
        ask_qwen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
