import tempfile
import unittest
from datetime import date
from pathlib import Path
from ava import file_actions

from ava.file_organizer import (
    copy_today_files,
    organize_files,
    preview_copy_today_files,
    preview_file_organization,
)


class FileConfirmationSafetyTests(unittest.TestCase):
    def test_organization_moves_only_files_in_approved_preview(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            file_actions.connect_folder(str(folder))
            approved_file = folder / "approved.txt"
            unapproved_file = folder / "unapproved.txt"
            approved_file.write_text("approved", encoding="utf-8")
            unapproved_file.write_text("leave in place", encoding="utf-8")

            preview = preview_file_organization(str(folder))
            approved_move = next(
                move for move in preview["moves"] if move["file"] == "approved.txt"
            )
            result = organize_files(str(folder), [approved_move])

            self.assertEqual([item["file"] for item in result["moved"]], ["approved.txt"])
            self.assertTrue((folder / "Documents" / "approved.txt").is_file())
            self.assertTrue(unapproved_file.is_file())
            self.assertFalse((folder / "Documents" / "unapproved.txt").exists())

    def test_organization_rejects_file_changed_since_preview(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            file_actions.connect_folder(str(folder))
            source = folder / "report.txt"
            source.write_text("before preview", encoding="utf-8")
            preview = preview_file_organization(str(folder))

            source.write_text("changed after preview with a different size", encoding="utf-8")
            result = organize_files(str(folder), preview["moves"])

            self.assertEqual(result["moved"], [])
            self.assertIn("changed since preview", result["skipped"][0]["reason"])
            self.assertTrue(source.is_file())
            self.assertFalse((folder / "Documents").exists())

    def test_organization_preview_rejects_symlink_category_folder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "selected"
            outside = Path(temporary_directory) / "outside"
            root.mkdir()
            outside.mkdir()
            file_actions.connect_folder(str(root))
            (root / "report.txt").write_text("sample", encoding="utf-8")
            (root / "Documents").symlink_to(outside, target_is_directory=True)

            preview = preview_file_organization(str(root))

            self.assertEqual(preview["moves"], [])
            self.assertIn("safe folder", preview["skipped"][0]["reason"])
            self.assertEqual(list(outside.iterdir()), [])

    def test_copy_confirmation_copies_only_approved_files_and_keeps_originals(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            file_actions.connect_folder(str(root))
            approved_file = source / "approved.txt"
            unapproved_file = source / "unapproved.txt"
            approved_file.write_text("approved", encoding="utf-8")
            unapproved_file.write_text("keep original", encoding="utf-8")
            selected_date = date.today().isoformat()

            preview = preview_copy_today_files(
                str(source), str(destination), selected_date
            )
            approved_entry = next(
                entry for entry in preview["moves"] if entry["file"] == "approved.txt"
            )
            result = copy_today_files(
                str(source), str(destination), selected_date, [approved_entry]
            )
            dated_destination = destination / selected_date

            self.assertEqual([item["file"] for item in result["copied"]], ["approved.txt"])
            self.assertTrue(approved_file.is_file())
            self.assertTrue(unapproved_file.is_file())
            self.assertTrue((dated_destination / "approved.txt").is_file())
            self.assertFalse((dated_destination / "unapproved.txt").exists())

    def test_copy_confirmation_rejects_file_changed_since_preview(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            file_actions.connect_folder(str(root))
            source_file = source / "today.txt"
            source_file.write_text("before preview", encoding="utf-8")
            selected_date = date.today().isoformat()
            preview = preview_copy_today_files(
                str(source), str(destination), selected_date
            )

            source_file.write_text("changed after preview with a different size", encoding="utf-8")
            result = copy_today_files(
                str(source), str(destination), selected_date, preview["moves"]
            )

            self.assertEqual(result["copied"], [])
            self.assertIn("changed since preview", result["skipped"][0]["reason"])
            self.assertTrue(source_file.is_file())
            self.assertFalse(destination.exists())

    def test_copy_confirmation_does_not_overwrite_a_new_destination_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            file_actions.connect_folder(str(root))
            source_file = source / "today.txt"
            source_file.write_text("source contents", encoding="utf-8")
            selected_date = date.today().isoformat()
            preview = preview_copy_today_files(
                str(source), str(destination), selected_date
            )

            dated_destination = destination / selected_date
            dated_destination.mkdir(parents=True)
            target = dated_destination / source_file.name
            target.write_text("pre-existing destination", encoding="utf-8")
            result = copy_today_files(
                str(source), str(destination), selected_date, preview["moves"]
            )

            self.assertEqual(result["copied"], [])
            self.assertEqual(target.read_text(encoding="utf-8"), "pre-existing destination")
            self.assertTrue(source_file.is_file())
            self.assertIn("already exists", result["skipped"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
