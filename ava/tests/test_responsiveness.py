import os
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import requests
from werkzeug.serving import make_server

import library_security
import storage_manager

try:
    from test_confirmation_api import stash_main
except ImportError:
    from ava.tests.test_confirmation_api import stash_main


class ResponsivenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stash-responsiveness-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        paths = {
            "BASE_DIR": self.root,
            "STORAGE_DIR": self.storage,
            "MEDIA_DIR": self.storage / "media",
            "STORAGE_FILE": self.storage / "clipboard.json",
            "LIBRARY_LOCK_FILE": self.storage / ".clipboard.lock",
            "ITEM_ID_COUNTER_FILE": self.storage / ".next_item_id",
            "FOLDERS_FILE": self.storage / "folders.json",
            "WORKSPACE_MODE_SETTINGS_FILE": self.storage / "workspace_mode_settings.json",
            "PRIVACY_SETTINGS_FILE": self.storage / "privacy_settings.json",
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(stash_main, "LOCAL_STORAGE_DIR", str(self.storage)))
        self.patches.enter_context(patch.object(stash_main, "initialize_local_runtime"))
        self.patches.enter_context(patch.object(stash_main, "has_authenticated_session", return_value=True))
        self.patches.enter_context(patch.object(stash_main, "request_is_same_origin", return_value=True))
        self.patches.enter_context(patch.object(stash_main, "is_local_extension_request", return_value=True))
        self.patches.enter_context(patch.object(stash_main, "get_privacy_settings", return_value={
            "capture_enabled": True,
            "excluded_sites": [],
            "excluded_app_bundle_ids": [],
            "retention_days": 0,
        }))
        self.patches.enter_context(patch.object(stash_main, "_browser_video_copy_allowed", return_value=True))
        self.patches.enter_context(patch.object(stash_main, "get_clipboard_change_count", return_value=None))
        self.patches.enter_context(patch.object(stash_main, "publish_video_file_to_clipboard", return_value=True))
        self.patches.enter_context(patch.object(library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"))
        for name, path in paths.items():
            self.patches.enter_context(patch.object(storage_manager, name, str(path)))
        stash_main.app.config.update(TESTING=True)
        self.server = make_server("127.0.0.1", 0, stash_main.app, threaded=True)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self._stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        self.server.shutdown()
        self.server_thread.join(timeout=5)

    def test_scaled_near_limit_upload_does_not_block_health_or_library(self):
        upload_limit = 8 * 1024 * 1024
        upload_size = upload_limit - 512 * 1024
        self.patches.enter_context(patch.object(stash_main, "MAX_UPLOAD_BYTES", upload_limit))
        self.patches.enter_context(patch.dict(stash_main.app.config, {"MAX_CONTENT_LENGTH": upload_limit}))
        upload_started = threading.Event()

        def chunks():
            remaining = upload_size
            while remaining:
                size = min(256 * 1024, remaining)
                upload_started.set()
                yield b"v" * size
                remaining -= size
                time.sleep(0.025)

        def upload():
            return requests.post(
                f"{self.base_url}/api/browser-copy",
                data=chunks(),
                headers={
                    "X-Copy-Maker-Type": "video",
                    "X-Copy-Maker-URL": "https://fixture.test/large.webm",
                    "X-Copy-Maker-Page": "https://fixture.test/",
                    "Content-Type": "video/webm",
                },
                timeout=20,
            )

        with ThreadPoolExecutor(max_workers=3) as pool:
            upload_future = pool.submit(upload)
            self.assertTrue(upload_started.wait(timeout=2))
            time.sleep(0.08)
            start = time.monotonic()
            health = requests.get(f"{self.base_url}/health", timeout=3)
            health_elapsed = time.monotonic() - start
            start = time.monotonic()
            library = requests.get(f"{self.base_url}/api/clipboard", timeout=3)
            library_elapsed = time.monotonic() - start
            uploaded = upload_future.result(timeout=20)

        self.assertLess(upload_size, upload_limit)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(library.status_code, 200)
        self.assertLess(health_elapsed, 1.5, f"health took {health_elapsed:.2f}s")
        self.assertLess(library_elapsed, 1.5, f"library took {library_elapsed:.2f}s")
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(uploaded.json()["size"], upload_size)

    def test_slow_ava_call_does_not_block_other_requests(self):
        model_started = threading.Event()
        release_model = threading.Event()

        def slow_model(*args, **kwargs):
            model_started.set()
            if not release_model.wait(timeout=5):
                raise TimeoutError("fixture model exceeded test limit")
            return {"success": True, "reply": "Fixture response"}

        self.patches.enter_context(patch.object(stash_main, "ava_run", side_effect=slow_model))
        with ThreadPoolExecutor(max_workers=2) as pool:
            ava_future = pool.submit(requests.post, f"{self.base_url}/api/ava", json={"command": "test"}, timeout=8)
            self.assertTrue(model_started.wait(timeout=2))
            start = time.monotonic()
            health = requests.get(f"{self.base_url}/health", timeout=3)
            health_elapsed = time.monotonic() - start
            library = requests.get(f"{self.base_url}/api/clipboard", timeout=3)
            release_model.set()
            ava = ava_future.result(timeout=8)

        self.assertEqual(health.status_code, 200)
        self.assertEqual(library.status_code, 200)
        self.assertLess(health_elapsed, 1.5, f"health took {health_elapsed:.2f}s")
        self.assertEqual(ava.status_code, 200, ava.text)
        self.assertEqual(ava.json()["reply"], "Fixture response")


if __name__ == "__main__":
    unittest.main()
