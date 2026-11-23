import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app_paths import is_temporary_storage, require_isolated_test_storage


ROOT = Path(__file__).resolve().parents[2]


class TestStorageGuardTests(unittest.TestCase):
    def test_guard_accepts_a_dedicated_temp_directory(self):
        with tempfile.TemporaryDirectory(prefix="stash-guard-") as directory:
            environment = {
                **os.environ,
                "STASH_TEST_MODE": "1",
                "STASH_STORAGE_DIR": directory,
            }
            checked = subprocess.run(
                [sys.executable, "-c", "import app_paths; print(app_paths.require_isolated_test_storage())"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertTrue(is_temporary_storage(directory))

    def test_guard_rejects_the_real_library_path(self):
        environment = {
            **os.environ,
            "STASH_TEST_MODE": "1",
            "STASH_STORAGE_DIR": str(ROOT / "storage"),
        }
        checked = subprocess.run(
            [sys.executable, "-c", "import app_paths"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("temporary directory", checked.stderr)

    def test_guard_rejects_a_non_temp_library_path(self):
        outside = ROOT / "outside-temp-test-storage"
        environment = {
            **os.environ,
            "STASH_TEST_MODE": "1",
            "STASH_STORAGE_DIR": str(outside),
        }
        checked = subprocess.run(
            [sys.executable, "-c", "import app_paths"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("temporary directory", checked.stderr)

    def test_test_runner_refuses_to_start_without_isolated_storage(self):
        environment = os.environ.copy()
        environment.pop("STASH_TEST_MODE", None)
        environment.pop("STASH_STORAGE_DIR", None)
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run-tests.py")],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("temporary STASH_STORAGE_DIR", checked.stderr)


if __name__ == "__main__":
    unittest.main()
