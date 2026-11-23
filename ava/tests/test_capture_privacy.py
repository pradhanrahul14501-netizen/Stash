import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main as stash_main
import storage_manager


class CapturePrivacySettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings_dir = tempfile.TemporaryDirectory(prefix="stash-privacy-test-")
        self.settings_path = Path(self.settings_dir.name) / "privacy_settings.json"
        self.settings_patch = patch.object(
            storage_manager, "PRIVACY_SETTINGS_FILE", str(self.settings_path)
        )
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()
        self.settings_dir.cleanup()

    def test_pause_and_exclusions_round_trip(self):
        saved = storage_manager.set_privacy_settings(
            capture_enabled=False,
            excluded_app_bundle_ids=["com.apple.Terminal"],
            excluded_sites=["Example.com", "*.private.example.org"],
        )

        self.assertFalse(saved["capture_enabled"])
        self.assertEqual(saved["excluded_app_bundle_ids"], ["com.apple.Terminal"])
        self.assertEqual(saved["excluded_sites"], ["example.com", "private.example.org"])
        self.assertEqual(storage_manager.get_privacy_settings(), saved)

    def test_rejects_paths_and_invalid_site_entries(self):
        with self.assertRaises(ValueError):
            storage_manager.set_privacy_settings(excluded_app_bundle_ids=["../../.env"])
        with self.assertRaises(ValueError):
            storage_manager.set_privacy_settings(excluded_sites=["https://example.com/path"])

    def test_site_exclusion_matches_subdomains_but_not_lookalikes(self):
        with patch.object(
            stash_main,
            "get_privacy_settings",
            return_value={"excluded_sites": ["example.com"]},
        ):
            self.assertTrue(stash_main._excluded_capture_site("https://video.example.com/reel"))
            self.assertTrue(stash_main._excluded_capture_site("https://example.com/"))
            self.assertFalse(stash_main._excluded_capture_site("https://notexample.com/"))

    def test_app_exclusion_is_case_insensitive(self):
        with patch.object(
            stash_main,
            "get_privacy_settings",
            return_value={"excluded_app_bundle_ids": ["com.apple.Terminal"]},
        ):
            self.assertTrue(stash_main._excluded_capture_app("COM.APPLE.TERMINAL"))
            self.assertFalse(stash_main._excluded_capture_app("com.apple.Safari"))


class HealthRouteTests(unittest.TestCase):
    def test_health_is_fast_and_does_not_initialize_storage(self):
        with patch.object(stash_main, "initialize_local_runtime") as initialize:
            response = stash_main.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})
        initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
