import io
import unittest
from unittest.mock import patch

import auth

try:
    from test_confirmation_api import stash_main
except ImportError:
    from ava.tests.test_confirmation_api import stash_main


class FirebaseOutageTests(unittest.TestCase):
    def setUp(self):
        self.runtime = patch.object(stash_main, "initialize_local_runtime")
        self.authenticated = patch.object(stash_main, "has_authenticated_session", return_value=True)
        self.auth_request = patch.object(auth, "has_authenticated_session", return_value=True)
        self.origin = patch.object(stash_main, "request_is_same_origin", return_value=True)
        self.auth_origin = patch.object(auth, "request_is_same_origin", return_value=True)
        for context in (self.runtime, self.authenticated, self.auth_request, self.origin, self.auth_origin):
            context.start()
            self.addCleanup(context.stop)
        stash_main.app.config.update(TESTING=True)
        self.client = stash_main.app.test_client()

    def test_missing_firebase_config_returns_explanation_and_local_library_stays_available(self):
        with (
            patch.object(auth, "_FIREBASE_AUTH_READY", False),
            patch.object(auth, "firebase_storage", None),
            patch.object(auth, "_FIREBASE_STORAGE_BUCKET", ""),
            patch.object(stash_main, "load_items", return_value=[]),
        ):
            cloud = self.client.get("/api/cloud-storage/status")
            local_library = self.client.get("/api/clipboard")

        self.assertEqual(cloud.status_code, 503)
        self.assertIn("Firebase Cloud Storage is not configured", cloud.get_json()["error"])
        self.assertEqual(local_library.status_code, 200)
        self.assertEqual(local_library.get_json(), [])

    def test_blocked_firebase_network_returns_actionable_status_not_traceback(self):
        with (
            patch.object(auth, "_cloud_storage_context", return_value=("test-user", object(), None)),
            patch.object(auth, "_cloud_storage_files", side_effect=OSError("network blocked")),
        ):
            response = self.client.get("/api/cloud-storage/status")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "Set up the Firebase Storage bucket, then check again.",
        )

    def test_mid_upload_firebase_failure_returns_clear_message(self):
        class FailedBlob:
            metadata = None
            content_disposition = None

            def upload_from_file(self, *args, **kwargs):
                raise OSError("simulated network drop during upload")

        class FakeBucket:
            def blob(self, name):
                return FailedBlob()

        with (
            patch.object(auth, "_cloud_storage_context", return_value=("test-user", FakeBucket(), None)),
            patch.object(auth, "_cloud_storage_files", return_value=([], 0)),
        ):
            response = self.client.post(
                "/api/cloud-storage/upload",
                data={"file": (io.BytesIO(b"isolated fixture"), "fixture.txt")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "The file could not be saved to Firebase Storage. Check that Storage is set up.",
        )


if __name__ == "__main__":
    unittest.main()
