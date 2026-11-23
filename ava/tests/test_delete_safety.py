import unittest
from unittest.mock import patch

from ava import agent


class DeleteSafetyTests(unittest.TestCase):
    def test_generic_file_delete_asks_before_searching(self):
        with (
            patch.object(agent, "ask_qwen") as ask_qwen,
            patch.object(agent, "search_library") as search_library,
        ):
            result = agent.run("Delete a file")

        self.assertTrue(result["needs_clarification"])
        self.assertIn("specific saved item", result["message"])
        ask_qwen.assert_not_called()
        search_library.assert_not_called()

    def test_bulk_delete_previews_stash_scope_without_searching_by_name(self):
        with (
            patch.object(agent, "ask_qwen") as ask_qwen,
            patch.object(agent, "search_library") as search_library,
            patch.object(agent, "_active_stash_items", return_value=[{
                "id": 42,
                "type": "file",
                "title": "fixture.pdf",
            }]),
        ):
            result = agent.run("Delete all my files", conversation_id="delete-safety-test")

        self.assertIn("Delete 1 item from Stash?", result["message"])
        self.assertIn("fixture.pdf", result["message"])
        self.assertIn("Yes / No", result["message"])
        ask_qwen.assert_not_called()
        search_library.assert_not_called()

    def test_latest_photo_uses_image_type_and_confirmation_gate(self):
        photo = {"id": 7, "type": "image", "original_name": "test-photo.png"}
        with (
            patch.object(agent, "ask_qwen") as ask_qwen,
            patch.object(agent, "search_library", return_value=[photo]) as search_library,
            patch.object(agent, "delete_library_item") as delete_library_item,
        ):
            result = agent.run("Delete my latest photo")

        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["confirmation_type"], "delete_item")
        self.assertEqual(result["item"], photo)
        search_library.assert_called_once_with(
            query=None,
            item_type="image",
            source=None,
            date=None,
            limit=1,
        )
        ask_qwen.assert_not_called()
        delete_library_item.assert_not_called()

    def test_explicit_photo_type_overrides_model_misclassification(self):
        photo = {"id": 9, "type": "image", "original_name": "test-photo.png"}
        with (
            patch.object(
                agent,
                "ask_qwen",
                return_value={
                    "intent": "delete_item",
                    "type": "file",
                    "latest": True,
                    "query": "library",
                },
            ),
            patch.object(agent, "search_library", return_value=[photo]) as search_library,
        ):
            result = agent.run("Please delete my latest photo from the library")

        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["item"], photo)
        search_library.assert_called_once_with(
            query=None,
            item_type="image",
            source=None,
            date=None,
            limit=1,
        )

    def test_model_query_must_be_grounded_in_user_request(self):
        with (
            patch.object(
                agent,
                "ask_qwen",
                return_value={"intent": "delete_item", "type": "file", "query": "ava_test.txt"},
            ),
            patch.object(agent, "search_library") as search_library,
        ):
            result = agent.run("Please delete a file from yesterday")

        self.assertTrue(result["needs_clarification"])
        search_library.assert_not_called()

    def test_generic_model_query_is_not_an_explicit_target(self):
        with (
            patch.object(
                agent,
                "ask_qwen",
                return_value={"intent": "delete_item", "type": "file", "query": "file"},
            ),
            patch.object(agent, "search_library") as search_library,
        ):
            result = agent.run("Please delete a file from yesterday")

        self.assertTrue(result["needs_clarification"])
        search_library.assert_not_called()

    def test_explicit_filename_can_reach_confirmation_preview(self):
        file_item = {"id": 8, "type": "file", "original_name": "report.pdf"}
        with (
            patch.object(
                agent,
                "ask_qwen",
                return_value={"intent": "delete_item", "type": "file", "query": "report.pdf"},
            ),
            patch.object(agent, "search_library", return_value=[file_item]) as search_library,
            patch.object(agent, "delete_library_item") as delete_library_item,
        ):
            result = agent.run("Delete the report.pdf file")

        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["item"], file_item)
        search_library.assert_called_once()
        delete_library_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
