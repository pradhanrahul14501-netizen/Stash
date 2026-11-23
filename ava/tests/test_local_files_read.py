import tempfile
import unittest
from pathlib import Path

from ava.local_files import read_text_file
from ava import file_actions


class LocalFileReadTests(unittest.TestCase):
    def test_invalid_utf8_uses_a_friendly_read_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            file_actions.connect_folder(str(folder))
            (folder / "unreadable.txt").write_bytes(b"\xff\xfe\x80")

            with self.assertRaisesRegex(ValueError, "not readable as UTF-8 text"):
                read_text_file(str(folder), "unreadable.txt")

    def test_oversized_text_file_is_rejected_with_a_size_limit_message(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            file_actions.connect_folder(str(folder))
            (folder / "large.txt").write_bytes(b"x" * (1024 * 1024 + 1))

            with self.assertRaisesRegex(ValueError, "maximum 1 MB"):
                read_text_file(str(folder), "large.txt")


if __name__ == "__main__":
    unittest.main()
