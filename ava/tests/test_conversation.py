import unittest
from unittest.mock import patch

from ava import agent


class ConversationTests(unittest.TestCase):
    def test_help_phrases_return_capabilities_without_calling_model(self):
        prompts = (
            "Hi! What can you help me with?",
            "What can you do?",
            "Help",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt), patch.object(agent, "ask_qwen") as ask_qwen:
                result = agent.run(prompt)

            self.assertTrue(result["success"])
            self.assertIn("search your Stash library", result["message"])
            self.assertIn("preview", result["message"])
            self.assertIn("confirm", result["message"])
            ask_qwen.assert_not_called()

    def test_simple_greeting_stays_brief_without_calling_model(self):
        with patch.object(agent, "ask_qwen") as ask_qwen:
            result = agent.run("Hello!")

        self.assertTrue(result["success"])
        self.assertIn("What would you like me to do?", result["message"])
        ask_qwen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
