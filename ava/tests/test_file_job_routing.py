import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ava import agent, file_actions


class FileJobRoutingTests(unittest.TestCase):
    def test_show_me_plan_does_not_route_file_sort_to_search(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            folder = root / "Downloads"
            folder.mkdir()
            file_actions.connect_folder(str(root))
            (folder / "report.pdf").write_text("fixture", encoding="utf-8")

            with patch.object(agent, "search_everywhere") as search_everywhere:
                result = agent.run(f"Sort the files by type in {folder} and show me the plan")

            self.assertEqual(result.get("confirmation_type"), "file_action")
            self.assertEqual(result["file_action_preview"]["count"], 1)
            search_everywhere.assert_not_called()

    def test_sort_by_date_proposes_date_based_organization(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            folder = root / "Downloads"
            folder.mkdir()
            (folder / "report.pdf").write_text("fixture", encoding="utf-8")
            file_actions.connect_folder(str(root))

            result = agent.run(f"Sort my files by date in {folder}")

            self.assertEqual(result["confirmation_type"], "file_action")
            self.assertEqual(result["file_action_preview"]["by"], "date")
            self.assertIn("by date", result["message"].casefold())

    def test_summary_honors_model_clarification_before_reading_one_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory) / "Inbox"
            folder.mkdir()
            document = folder / "quarterly-report.txt"
            document.write_text("fixture only", encoding="utf-8")
            file_actions.connect_folder(str(folder))
            with (
                patch.object(agent, "_summarize_local_text", return_value="One summary.") as summarize,
            ):
                result = agent.run(f"Summarize {document.name} in {folder}")

            self.assertTrue(result["success"])
            self.assertIn("One summary", result["message"])
            summarize.assert_called_once()

    def test_multi_file_summary_does_not_silently_use_only_first_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory) / "Inbox"
            folder.mkdir()
            document = folder / "quarterly-report.txt"
            document.write_text("fixture only", encoding="utf-8")
            (folder / "meeting.md").write_text("meeting notes", encoding="utf-8")
            (folder / "research.txt").write_text("research notes", encoding="utf-8")
            file_actions.connect_folder(str(folder))
            command = (
                f"Summarize {document.name}, meeting.md, and research.txt in {folder}"
            )

            with (
                patch.object(agent, "_summarize_local_text", return_value="Combined summary.") as summarize,
            ):
                result = agent.run(command)

            self.assertTrue(result["success"])
            self.assertIn("Combined summary", result["message"])
            self.assertEqual(len(result["summaries"]), 3)
            summarize.assert_called_once()

    def test_no_cancels_a_pending_delete_confirmation_without_calling_model(self):
        history = [{
            "role": "assistant",
            "content": "Delete quarterly-report.txt? I’ll wait for your confirmation.",
        }]

        with patch.object(agent, "ask_qwen") as ask_qwen:
            result = agent.run("No", history=history)

        self.assertTrue(result["cancelled"])
        self.assertIn("Nothing was deleted", result["message"])
        ask_qwen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
