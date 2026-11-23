import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests

import library_security
import storage_manager
from ava import agent, tools, unified_search


class AvaModelRetryTests(unittest.TestCase):
    def test_model_timeout_retries_once_then_returns_the_response(self):
        response = Mock()
        response.json.return_value = {"message": {"content": '{"intent":"find_item"}'}}
        with patch.object(
            agent.requests,
            "post",
            side_effect=[requests.Timeout("cold start"), response],
        ) as post:
            result = agent.ask_qwen("find videos")

        self.assertEqual(result, {"intent": "find_item"})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0], post.call_args_list[1])

    def test_model_timeout_twice_has_a_clear_retryable_error(self):
        with patch.object(
            agent.requests,
            "post",
            side_effect=requests.Timeout("model still loading"),
        ) as post:
            with self.assertRaises(agent.AvaServiceError) as raised:
                agent.ask_qwen("find videos")

        self.assertEqual(post.call_count, 2)
        self.assertEqual(raised.exception.code, "ollama_timeout")
        self.assertTrue(raised.exception.retryable)
        self.assertIn("timed out twice", str(raised.exception))

    def test_missing_model_is_not_reported_as_a_connection_failure(self):
        response = Mock()
        response.status_code = 404
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with patch.object(agent.requests, "post", return_value=response) as post:
            with self.assertRaises(agent.AvaServiceError) as raised:
                agent.ask_qwen("find videos")

        self.assertEqual(post.call_count, 1)
        self.assertEqual(raised.exception.code, "model_missing")
        self.assertIn("not available in Ollama", str(raised.exception))

    def test_api_preserves_a_clear_model_error_for_the_chat_ui(self):
        import main as stash_main

        with stash_main.app.test_request_context(
            "/api/ava", method="POST", json={"command": "find videos"}
        ), patch.object(
            stash_main,
            "ava_run",
            side_effect=agent.AvaServiceError("Ollama timed out twice.", "ollama_timeout", True),
        ):
            response, status = stash_main.ava_api()

        self.assertEqual(status, 503)
        self.assertEqual(response.get_json()["message"], "Ollama timed out twice.")
        self.assertEqual(response.get_json()["error_code"], "ollama_timeout")
        self.assertTrue(response.get_json()["retryable"])

    def test_api_forwards_saved_search_context_and_page_offset(self):
        import main as stash_main

        context = {"query": "meeting", "type": "video"}
        with stash_main.app.test_request_context(
            "/api/ava", method="POST", json={
                "command": "only text", "search_context": context, "search_offset": 50,
            }
        ), patch.object(stash_main, "ava_run", return_value={"success": True}) as run:
            stash_main.ava_api()

        self.assertEqual(run.call_args.kwargs["search_context"], context)
        self.assertEqual(run.call_args.kwargs["search_offset"], 50)


class AvaEncryptedLibrarySearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="ava-search-")
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
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
        for name, path in paths.items():
            patcher = patch.object(storage_manager, name, str(path))
            patcher.start()
            self.addCleanup(patcher.stop)
        key_patcher = patch.object(
            library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"
        )
        key_patcher.start()
        self.addCleanup(key_patcher.stop)

        self.addCleanup(time.tzset)
        timezone_patcher = patch.dict(os.environ, {"TZ": "Asia/Kolkata"})
        timezone_patcher.start()
        self.addCleanup(timezone_patcher.stop)
        time.tzset()

    def _write_encrypted_items(self, items):
        Path(storage_manager.STORAGE_FILE).write_bytes(library_security.encrypt_json(items))

    def test_type_word_query_returns_all_encrypted_video_matches(self):
        items = [
            {"id": 7, "type": "video", "original_name": "first.mp4", "created_at": "2026-10-20T10:00:00"},
            {"id": 8, "type": "video", "original_name": "second.mp4", "created_at": "2026-10-20T09:00:00"},
            {"id": 9, "type": "text", "content": "videos are mentioned here", "created_at": "2026-10-20T08:00:00"},
        ]
        self._write_encrypted_items(items)

        found = tools.search_library(query="videos", item_type="video", limit=None, fuzzy=True)

        self.assertEqual([item["id"] for item in found], [7, 8])

    def test_aware_utc_timestamps_match_local_calendar_date_across_midnight(self):
        items = [
            {"id": 1, "type": "video", "original_name": "before.mp4", "created_at": "2026-10-19T18:29:00Z"},
            {"id": 2, "type": "video", "original_name": "after.mp4", "created_at": "2026-10-19T18:31:00Z"},
            {"id": 3, "type": "video", "original_name": "later.mp4", "created_at": "2026-10-19T20:00:00+00:00"},
        ]
        self._write_encrypted_items(items)

        yesterday = tools.search_library(item_type="video", date="2026-10-19", limit=None)
        today = tools.search_library(item_type="video", date="2026-10-20", limit=None)

        self.assertEqual([item["id"] for item in yesterday], [1])
        self.assertEqual([item["id"] for item in today], [3, 2])


class UnifiedSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="ava-everywhere-")
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        self.addCleanup(time.tzset)
        timezone_patcher = patch.dict(os.environ, {"TZ": "Asia/Kolkata"})
        timezone_patcher.start()
        self.addCleanup(timezone_patcher.stop)
        time.tzset()
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
        for name, path in paths.items():
            patcher = patch.object(storage_manager, name, str(path))
            patcher.start()
            self.addCleanup(patcher.stop)
        key_patcher = patch.object(
            library_security, "_get_key", return_value=b"test-library-key-32-bytes-long!!"
        )
        key_patcher.start()
        self.addCleanup(key_patcher.stop)

    def _write_encrypted_items(self, items):
        Path(storage_manager.STORAGE_FILE).write_bytes(library_security.encrypt_json(items))

    def test_type_and_date_phrases_parse_without_a_folder(self):
        today_video = unified_search.parse_search_request("find my today video")
        broad_files = unified_search.parse_search_request("find files")
        pdfs = unified_search.parse_search_request("find my pdfs from last week")
        this_month = unified_search.parse_search_request("find files from this month")
        explicit_date = unified_search.parse_search_request("find videos on 2026-10-20")
        explicit_folder = unified_search.parse_search_request(
            "find PDFs in ~/Documents", folder_resolver=lambda _: "/Users/example/Documents"
        )
        before_midnight = unified_search.resolve_local_date_range(
            "today", now=datetime(2026, 10, 19, 23, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
        )
        after_midnight = unified_search.resolve_local_date_range(
            "today", now=datetime(2026, 10, 20, 0, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
        )

        self.assertEqual(today_video["type"], "video")
        self.assertEqual(today_video["date_range"]["label"], "today")
        self.assertIsNone(today_video["query"])
        self.assertEqual(broad_files["type"], "file")
        self.assertIsNone(broad_files["folder"])
        self.assertIsNone(broad_files["query"])
        self.assertEqual(pdfs["extension"], "pdf")
        self.assertEqual(pdfs["date_range"]["label"], "last week")
        self.assertEqual(this_month["date_range"]["start"][8:], "01")
        self.assertEqual(explicit_date["date_range"]["start"], "2026-10-20")
        self.assertEqual(explicit_folder["folder"], "/Users/example/Documents")
        self.assertEqual(before_midnight["start"], "2026-10-19")
        self.assertEqual(after_midnight["start"], "2026-10-20")

    def test_spotlight_uses_mocked_mdfind_and_filters_sensitive_paths(self):
        safe = self.root / "Documents" / "meeting notes.pdf"
        secret = self.root / "Documents" / ".env"
        safe.parent.mkdir()
        safe.write_bytes(b"fixture only")
        secret.write_bytes(b"not read by search")

        class Completed:
            returncode = 0
            stdout = (str(safe) + "\0" + str(secret) + "\0").encode()
            stderr = b""

        runner = Mock(return_value=Completed())
        result = unified_search.spotlight_search(
            query="meeting", item_type="file", folder=str(safe.parent), runner=runner
        )

        self.assertEqual([item["name"] for item in result["results"]], [safe.name])
        command = runner.call_args.args[0]
        self.assertEqual(command[:3], ["/usr/bin/mdfind", "-0", "-onlyin"])
        self.assertIn(str(safe.parent.resolve()), command)
        self.assertIn('kMDItemFSName == "*meeting*"cd', command[-1])
        self.assertIn('kMDItemTextContent == "*meeting*"cd', command[-1])

    def test_folderless_search_is_stash_only(self):
        self._write_encrypted_items([{
            "id": 70, "type": "file", "original_name": "invoice.pdf",
            "created_at": "2026-10-20T10:00:00", "size": 100,
        }])
        mac_match = {
            "source": "mac", "name": "invoice-copy.pdf", "type": "file",
            "size": 200, "modified_at": "2026-10-20T09:00:00+05:30",
            "location": str(self.root / "Documents"), "path": str(self.root / "Documents" / "invoice-copy.pdf"),
        }
        with patch.object(unified_search, "spotlight_search", return_value={
            "results": [mac_match], "available": True, "permission_blocked": False,
        }) as spotlight:
            result = agent.run("find files")

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual({item["source"] for item in result["results"]}, {"stash"})
        spotlight.assert_not_called()
        self.assertNotIn("Which folder", result["message"])

    def test_plain_video_and_today_video_searches_find_encrypted_fixture(self):
        self._write_encrypted_items([
            {"id": 80, "type": "video", "original_name": "today.mp4", "created_at": "2026-10-19T20:00:00Z"},
            {"id": 81, "type": "video", "original_name": "yesterday.mp4", "created_at": "2026-10-19T17:00:00Z"},
        ])

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                moment = cls(2026, 10, 20, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
                return moment.astimezone(tz) if tz else moment

        backend = Mock(return_value={"results": [], "available": True, "permission_blocked": False})
        with patch.object(unified_search, "datetime", FixedDateTime), patch.object(
            unified_search, "spotlight_search", backend
        ):
            all_videos = agent.run("find videos")
            today_video = agent.run("find my today video")

        self.assertEqual(all_videos["count"], 2)
        self.assertEqual(today_video["count"], 1)
        self.assertEqual(today_video["results"][0]["id"], 80)
        self.assertEqual(today_video["search_summary"]["date_range"]["start"], "2026-10-20")

    def test_pages_are_capped_at_20_and_empty_message_names_filters(self):
        self._write_encrypted_items([
            {"id": index, "type": "video", "original_name": f"video-{index}.mp4", "created_at": "2026-10-20T10:00:00"}
            for index in range(30)
        ])
        mac_matches = [
            {"source": "mac", "name": f"clip-{index}.mp4", "type": "video", "size": 1,
             "modified_at": "2026-10-20T09:00:00+05:30", "location": "/Users/test/Videos", "path": f"/Users/test/Videos/clip-{index}.mp4"}
            for index in range(30)
        ]
        backend = Mock(return_value={"results": mac_matches, "available": True, "permission_blocked": False})

        filters = {"type": "video", "places": "stash_and_mac"}
        first = unified_search.search_everywhere(filters, spotlight_backend=backend)
        second = unified_search.search_everywhere(filters, offset=40, spotlight_backend=backend)
        empty = unified_search.search_everywhere(
            {"type": "video", "places": "stash_and_mac", "date_range": {"start": "2026-10-21", "end": "2026-10-21", "label": "2026-10-21"}},
            spotlight_backend=Mock(return_value={"results": [], "available": True, "permission_blocked": False}),
        )

        self.assertEqual(first["count"], 60)
        self.assertEqual(len(first["results"]), 20)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(second["results"]), 20)
        self.assertFalse(second["has_more"])
        self.assertIn("video", empty["message"])
        self.assertIn("2026-10-21", empty["message"])
        self.assertIn("Stash", empty["message"])
        self.assertIn("Mac", empty["message"])
        self.assertIn("broader search", empty["message"])

    def test_spotlight_permission_error_keeps_stash_matches(self):
        self._write_encrypted_items([{
            "id": 71, "type": "text", "content": "saved phrase", "created_at": "2026-10-20T10:00:00",
        }])
        result = unified_search.search_everywhere(
            {"query": "saved phrase", "places": "stash_and_mac"},
            spotlight_backend=Mock(return_value={"results": [], "available": False, "permission_blocked": True}),
        )

        self.assertEqual(result["count"], 1)
        self.assertTrue(result["spotlight_permission_blocked"])
        self.assertIn("Full Disk Access", result["message"])

    def test_short_followups_filter_the_last_search_without_calling_the_model(self):
        self._write_encrypted_items([
            {"id": 90, "type": "video", "original_name": "meeting.mp4", "content": "meeting video", "created_at": "2026-10-20T03:00:00Z"},
            {"id": 91, "type": "text", "content": "meeting agenda today", "created_at": "2026-10-20T03:00:00Z"},
            {"id": 92, "type": "text", "content": "meeting agenda yesterday", "created_at": "2026-10-19T06:00:00Z"},
        ])

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                moment = cls(2026, 10, 20, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
                return moment.astimezone(tz) if tz else moment

        context = {"query": "meeting", "type": "video", "places": "stash_and_mac"}
        backend = Mock(return_value={"results": [], "available": True, "permission_blocked": False})
        with patch.object(unified_search, "datetime", FixedDateTime), patch.object(
            unified_search, "spotlight_search", backend
        ), patch.object(agent, "ask_qwen", side_effect=AssertionError("follow-ups must not need the model")):
            only_text = agent.run("only text", search_context=context)
            from_yesterday = agent.run("from yesterday", search_context=only_text["search_context"])

        self.assertEqual(only_text["search_context"]["type"], "text")
        self.assertEqual([item["id"] for item in only_text["results"]], [91, 92])
        self.assertEqual(from_yesterday["search_context"]["type"], "text")
        self.assertEqual([item["id"] for item in from_yesterday["results"]], [92])

    def test_show_more_uses_the_saved_offset_and_no_context_is_not_a_followup(self):
        mac_results = [
            {"source": "mac", "name": f"clip-{index}.mp4", "type": "video", "size": 1,
             "modified_at": "2026-10-20T09:00:00+05:30", "location": "/Users/test/Videos", "path": f"/Users/test/Videos/clip-{index}.mp4"}
            for index in range(60)
        ]
        backend = Mock(return_value={"results": mac_results, "available": True, "permission_blocked": False})
        with patch.object(unified_search, "spotlight_search", backend):
            result = agent.run("show more", search_context={"type": "video", "places": "mac"}, search_offset=40)

        self.assertEqual(result["offset"], 40)
        self.assertEqual(len(result["results"]), 20)
        self.assertFalse(result["has_more"])
        self.assertIsNone(unified_search.parse_search_followup("only text", None))

    def test_explicit_save_action_encrypts_a_mac_file_in_temporary_stash(self):
        import main as stash_main

        source = self.root / "Documents" / "meeting.txt"
        source.parent.mkdir()
        original = b"unchanged local test file"
        source.write_bytes(original)
        with stash_main.app.test_request_context(
            "/api/ava/search-action", method="POST",
            json={"action": "save", "source": "mac", "path": str(source)},
        ), patch.object(stash_main, "request_is_same_origin", return_value=True):
            response = stash_main.ava_search_action()

        self.assertEqual(response.status_code, 200)
        saved_items = storage_manager.load_items()
        self.assertEqual(len(saved_items), 1)
        self.assertEqual(saved_items[0]["type"], "file")
        self.assertEqual(source.read_bytes(), original)

    def test_search_action_refuses_sensitive_mac_paths(self):
        import main as stash_main

        secret = self.root / ".env"
        secret.write_text("fixture", encoding="utf-8")
        with stash_main.app.test_request_context(
            "/api/ava/search-action", method="POST",
            json={"action": "save", "source": "mac", "path": str(secret)},
        ), patch.object(stash_main, "request_is_same_origin", return_value=True):
            response = stash_main.ava_search_action()

        if isinstance(response, tuple):
            response, status = response
        else:
            status = response.status_code
        self.assertEqual(status, 400)
        self.assertFalse(storage_manager.load_items())


if __name__ == "__main__":
    unittest.main()
