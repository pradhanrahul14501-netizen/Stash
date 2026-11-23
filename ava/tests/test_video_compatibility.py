import hashlib
import json
import os
import time
import subprocess
import sys
import tempfile
import unittest
import stat
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import library_security
import storage_manager

if "test_confirmation_api" in sys.modules:
    from test_confirmation_api import stash_main
else:
    from ava.tests.test_confirmation_api import stash_main


class QuickTimeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="quicktime-video-")
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.mp4"
        self.original_bytes = b"saved-original-video"
        self.source.write_bytes(self.original_bytes)

    def test_startup_removes_stale_decrypted_conversion_copies(self):
        temporary_root = self.root / "temporary"
        temporary_root.mkdir()
        stale = temporary_root / ".stash-video-convert-crashed"
        stale.mkdir()
        (stale / "decrypted.mp4").write_bytes(b"temporary plaintext")
        current = temporary_root / ".stash-video-convert-current"
        current.mkdir()
        (current / "decrypted.mp4").write_bytes(b"active temporary plaintext")
        old_time = time.time() - 2 * 60 * 60
        os.utime(stale, (old_time, old_time))

        with patch.object(stash_main.tempfile, "gettempdir", return_value=str(temporary_root)):
            stash_main._cleanup_stale_video_conversions()

        self.assertFalse(stale.exists())
        self.assertTrue(current.exists())

    def test_next_process_start_removes_conversion_copy_left_by_crash(self):
        temporary_root = self.root / "crash-temp"
        temporary_root.mkdir()
        storage_root = temporary_root / "storage"
        stale = temporary_root / ".stash-video-convert-crashed-process"
        crash_code = (
            "import os, pathlib, time; "
            "root=pathlib.Path(os.environ['TMPDIR']); "
            "folder=root/'.stash-video-convert-crashed-process'; folder.mkdir(); "
            "(folder/'decrypted.mp4').write_bytes(b'decrypted bytes from interrupted handoff'); "
            "old=time.time()-7200; os.utime(folder,(old,old)); os._exit(0)"
        )
        environment = {
            **os.environ,
            "TMPDIR": str(temporary_root),
            "STASH_TEST_MODE": "1",
            "STASH_STORAGE_DIR": str(storage_root),
            "STASH_DISABLE_BACKGROUND_WORKERS": "1",
            "STASH_DISABLE_CLIPBOARD_MONITOR": "1",
            "COPY_MAKER_SECRET_KEY": "isolated-crash-cleanup-test-key",
        }
        subprocess.run([sys.executable, "-c", crash_code], env=environment, check=True)
        self.assertTrue((stale / "decrypted.mp4").exists())

        startup_code = "import main; main.initialize_local_runtime()"
        subprocess.run(
            [sys.executable, "-c", startup_code],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            check=True,
        )

        self.assertFalse(stale.exists())

    def _streams(self, video_codec="vp9", pixel_format="yuv420p", audio_codec="opus"):
        return [
            {"codec_type": "video", "codec_name": video_codec, "pix_fmt": pixel_format},
            {"codec_type": "audio", "codec_name": audio_codec},
        ]

    def test_incompatible_mp4_is_transcoded_to_a_separate_copy(self):
        def run(command, **kwargs):
            if command[0] == "/test/ffprobe":
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"streams": self._streams()}), ""
                )
            if command[0] == "/test/ffmpeg":
                Path(command[-1]).write_bytes(b"quicktime-compatible-copy")
                return subprocess.CompletedProcess(command, 0, "", "")
            raise AssertionError(f"Unexpected command: {command[0]}")

        real_mkdtemp = tempfile.mkdtemp
        with (
            patch.object(stash_main.shutil, "which", side_effect=lambda name: f"/test/{name}"),
            patch.object(stash_main.subprocess, "run", side_effect=run),
            patch.object(
                stash_main.tempfile,
                "mkdtemp",
                side_effect=lambda prefix: real_mkdtemp(prefix=prefix, dir=self.root),
            ),
        ):
            converted_path, converted, error = stash_main.convert_video_to_shareable_mp4(str(self.source))

        self.assertTrue(converted)
        self.assertIsNone(error)
        self.assertNotEqual(converted_path, str(self.source))
        self.assertEqual(Path(converted_path).read_bytes(), b"quicktime-compatible-copy")
        conversion_dir = Path(converted_path).parent
        self.assertEqual(stat.S_IMODE(conversion_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(Path(converted_path).stat().st_mode), 0o600)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)
        stash_main.cleanup_video_conversion(converted_path)
        self.assertFalse(conversion_dir.exists())

    def test_conversion_reports_missing_ffmpeg_without_creating_plaintext(self):
        with patch.object(stash_main.shutil, "which", return_value=None):
            result = stash_main.convert_video_to_shareable_mp4(str(self.root / "source.webm"))

        self.assertEqual(result, (str(self.root / "source.webm"), False, "ffmpeg_not_found"))

    def test_supported_h264_aac_mp4_is_passed_through(self):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"streams": self._streams("h264", "yuv420p", "aac")}),
                "",
            )

        with (
            patch.object(stash_main.shutil, "which", side_effect=lambda name: f"/test/{name}"),
            patch.object(stash_main.subprocess, "run", side_effect=run) as run_process,
        ):
            converted_path, converted, error = stash_main.convert_video_to_shareable_mp4(str(self.source))

        self.assertEqual(converted_path, str(self.source))
        self.assertFalse(converted)
        self.assertIsNone(error)
        self.assertEqual(run_process.call_count, 1)
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_browser_capture_finds_duplicate_in_encrypted_video_library(self):
        app_root = self.root / "copy-maker"
        videos = app_root / "storage" / "videos"
        videos.mkdir(parents=True)
        storage = app_root / "storage"
        encrypted_video = videos / "existing.mp4"
        plaintext_video = self.root / "fixture.mp4"
        plaintext_video.write_bytes(b"incoming video bytes")
        key = b"test-library-key-32-bytes-long!!"

        storage_paths = {
            "BASE_DIR": app_root,
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
            stack.enter_context(patch.object(stash_main, "__file__", str(app_root / "main.py")))
            stack.enter_context(patch.object(stash_main, "initialize_local_runtime"))
            stack.enter_context(patch.object(stash_main, "LOCAL_STORAGE_DIR", str(app_root / "storage")))
            stack.enter_context(patch.object(library_security, "_get_key", return_value=key))
            stack.enter_context(patch.object(stash_main, "_browser_video_copy_allowed", return_value=True))
            stack.enter_context(patch.object(stash_main, "is_local_extension_request", return_value=True))
            stack.enter_context(
                patch.object(stash_main, "get_privacy_settings", return_value={"capture_enabled": True})
            )
            stack.enter_context(patch.object(stash_main, "get_clipboard_change_count", return_value=17))
            publish = stack.enter_context(
                patch.object(stash_main, "publish_video_file_to_clipboard", return_value=True)
            )
            for name, path in storage_paths.items():
                stack.enter_context(patch.object(storage_manager, name, str(path)))

            library_security.encrypt_media_file(str(plaintext_video), str(encrypted_video))
            storage_manager.save_metadata({
                "id": 73,
                "type": "video",
                "file": "storage/videos/existing.mp4",
                "url": "/videos/existing.mp4",
                "size": plaintext_video.stat().st_size,
                "mime_type": "video/mp4",
            })

            encrypted_before = encrypted_video.read_bytes()
            stash_main.app.config.update(TESTING=True)
            response = stash_main.app.test_client().post(
                "/api/browser-copy",
                data=plaintext_video.read_bytes(),
                headers={
                    "X-Copy-Maker-Type": "video",
                    "X-Copy-Maker-URL": "https://example.test/reel.mp4",
                    "X-Copy-Maker-Page": "https://example.test/reel",
                    "X-Copy-Maker-Title": "Encrypted duplicate fixture",
                    "Content-Type": "video/mp4",
                },
            )

            self.assertEqual(response.status_code, 200)
            result = response.get_json()
            self.assertTrue(result["duplicate"])
            self.assertEqual(result["item"]["id"], 73)
            self.assertEqual(
                result["item"]["source_sha256"],
                hashlib.sha256(plaintext_video.read_bytes()).hexdigest(),
            )
            self.assertEqual(encrypted_video.read_bytes(), encrypted_before)
            self.assertEqual(len(storage_manager.load_items()), 1)
            publish.assert_called_once()
            self.assertEqual([path.name for path in videos.iterdir()], ["existing.mp4"])

    def test_browser_capture_caches_hash_for_nonduplicate_legacy_video(self):
        app_root = self.root / "copy-maker-nonduplicate"
        videos = app_root / "storage" / "videos"
        videos.mkdir(parents=True)
        storage = app_root / "storage"
        encrypted_video = videos / "existing.mp4"
        existing_plaintext = self.root / "legacy.mp4"
        incoming = b"different incoming video bytes"
        existing_plaintext.write_bytes(b"old legacy video bytes")
        key = b"test-library-key-32-bytes-long!!"

        storage_paths = {
            "BASE_DIR": app_root,
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
            stack.enter_context(patch.object(stash_main, "__file__", str(app_root / "main.py")))
            stack.enter_context(patch.object(stash_main, "initialize_local_runtime"))
            stack.enter_context(patch.object(library_security, "_get_key", return_value=key))
            stack.enter_context(patch.object(stash_main, "_browser_video_copy_allowed", return_value=True))
            stack.enter_context(patch.object(stash_main, "is_local_extension_request", return_value=True))
            stack.enter_context(
                patch.object(stash_main, "get_privacy_settings", return_value={"capture_enabled": True})
            )
            stack.enter_context(patch.object(stash_main, "get_clipboard_change_count", return_value=17))
            stack.enter_context(patch.object(stash_main, "publish_video_file_to_clipboard", return_value=True))
            for name, path in storage_paths.items():
                stack.enter_context(patch.object(storage_manager, name, str(path)))

            library_security.encrypt_media_file(str(existing_plaintext), str(encrypted_video))
            storage_manager.save_metadata({
                "id": 73,
                "type": "video",
                "file": "storage/videos/existing.mp4",
                "url": "/videos/existing.mp4",
                "size": existing_plaintext.stat().st_size,
                "mime_type": "video/mp4",
            })
            stash_main.app.config.update(TESTING=True)
            response = stash_main.app.test_client().post(
                "/api/browser-copy",
                data=incoming,
                headers={
                    "X-Copy-Maker-Type": "video",
                    "X-Copy-Maker-URL": "https://example.test/new.mp4",
                    "X-Copy-Maker-Page": "https://example.test/reel",
                    "X-Copy-Maker-Title": "New capture",
                    "Content-Type": "video/mp4",
                },
            )
            saved_items = storage_manager.load_items()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json().get("duplicate", False))
        self.assertEqual(len(saved_items), 2)
        legacy = next(item for item in saved_items if item["id"] == 73)
        self.assertEqual(
            legacy["source_sha256"],
            hashlib.sha256(b"old legacy video bytes").hexdigest(),
        )

    def test_quicktime_handoff_transcodes_encrypted_original_to_separate_copy(self):
        app_root = self.root / "quicktime-app"
        videos = app_root / "storage" / "videos"
        videos.mkdir(parents=True)
        source_path = videos / "instagram.mp4"
        plaintext_path = self.root / "quicktime-source.mp4"
        plaintext_path.write_bytes(self.original_bytes)
        key = b"test-library-key-32-bytes-long!!"
        with patch.object(library_security, "_get_key", return_value=key):
            library_security.encrypt_media_file(str(plaintext_path), str(source_path))
        original_encrypted_bytes = source_path.read_bytes()
        item = {
            "id": 9,
            "type": "video",
            "file": "storage/videos/instagram.mp4",
            "original_name": "instagram.mp4",
        }

        class NoopTimer:
            daemon = False

            def start(self):
                pass

        def run(command, **kwargs):
            if command[0] == "/test/ffprobe":
                return subprocess.CompletedProcess(
                    command, 0, json.dumps({"streams": self._streams()}), ""
                )
            if command[0] == "/test/ffmpeg":
                Path(command[-1]).write_bytes(b"quicktime-copy")
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[0] == "open":
                return subprocess.CompletedProcess(command, 0, "", "")
            raise AssertionError(f"Unexpected command: {command[0]}")

        with ExitStack() as stack:
            stack.enter_context(patch.object(stash_main, "__file__", str(app_root / "main.py")))
            stack.enter_context(patch.object(stash_main, "initialize_local_runtime"))
            stack.enter_context(patch.object(stash_main, "LOCAL_STORAGE_DIR", str(app_root / "storage")))
            stack.enter_context(patch.object(library_security, "_get_key", return_value=key))
            stack.enter_context(patch.object(stash_main, "load_items", return_value=[item]))
            stack.enter_context(patch.object(stash_main, "is_local_extension_request", return_value=True))
            stack.enter_context(patch.object(stash_main, "request_is_same_origin", return_value=True))
            stack.enter_context(
                patch.object(stash_main.shutil, "which", side_effect=lambda name: f"/test/{name}")
            )
            process = stack.enter_context(patch.object(stash_main.subprocess, "run", side_effect=run))
            stack.enter_context(patch.object(stash_main.threading, "Timer", return_value=NoopTimer()))
            real_mkdtemp = tempfile.mkdtemp
            stack.enter_context(
                patch.object(
                    stash_main.tempfile,
                    "mkdtemp",
                    side_effect=lambda prefix: real_mkdtemp(prefix=prefix, dir=self.root),
                )
            )

            stash_main.app.config.update(TESTING=True)
            response = stash_main.app.test_client().post(
                "/api/integrations/open-library-item",
                json={"itemId": 9, "app": "quicktime"},
            )

        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["success"])
        self.assertTrue(result["appOpened"])
        self.assertTrue(result["displayName"].endswith(".mp4"))
        handoff_file = app_root / "storage" / "integrations" / "handoff" / "quicktime" / result["displayName"]
        self.assertEqual(handoff_file.read_bytes(), b"quicktime-copy")
        self.assertEqual(source_path.read_bytes(), original_encrypted_bytes)
        self.assertTrue(any(call.args[0][0] == "/test/ffmpeg" for call in process.call_args_list))
        self.assertEqual(list(self.root.glob(".stash-video-convert-*")), [])

    def test_quicktime_handoff_enforces_storage_budget_before_conversion(self):
        app_root = self.root / "quicktime-full"
        storage = app_root / "storage"
        videos = storage / "videos"
        videos.mkdir(parents=True)
        source_path = videos / "source.mp4"
        source_path.write_bytes(b"video")
        item = {
            "id": 9,
            "type": "video",
            "file": "storage/videos/source.mp4",
            "original_name": "source.mp4",
        }

        with ExitStack() as stack:
            stack.enter_context(patch.object(stash_main, "__file__", str(app_root / "main.py")))
            stack.enter_context(patch.object(stash_main, "initialize_local_runtime"))
            stack.enter_context(patch.object(stash_main, "LOCAL_STORAGE_DIR", str(storage)))
            stack.enter_context(patch.object(stash_main, "load_items", return_value=[item]))
            stack.enter_context(patch.object(stash_main, "is_local_extension_request", return_value=True))
            stack.enter_context(patch.object(stash_main, "request_is_same_origin", return_value=True))
            stack.enter_context(patch.object(stash_main, "MAX_HANDOFF_TOTAL_BYTES", 1))
            convert = stack.enter_context(patch.object(stash_main, "convert_video_to_shareable_mp4"))
            stash_main.app.config.update(TESTING=True)
            response = stash_main.app.test_client().post(
                "/api/integrations/open-library-item",
                json={"itemId": 9, "app": "quicktime"},
            )

        self.assertEqual(response.status_code, 507)
        convert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
