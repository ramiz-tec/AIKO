import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import backend.chatbot as chatbot
import main


class WorkspaceConversationContextTests(unittest.TestCase):
    def test_main_chat_wrapper_reads_context_only_when_chat_is_requested(self):
        with (
            patch("main.GetWorkspaceContext", return_value="Workbench: chair"),
            patch("main.BackendChatBot", return_value="response") as backend_chat,
        ):
            result = main.ChatBot("Can you help me?")

        self.assertEqual(result, "response")
        backend_chat.assert_called_once_with(
            "Can you help me?",
            0,
            3,
            workspace_context="Workbench: chair",
        )

    def test_context_is_sent_to_the_model_but_not_saved_in_chat_history(self):
        response_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="I can help with the chair.")
                )
            ]
        )
        fake_client = Mock()
        fake_client.chat.completions.create.return_value = [response_chunk]

        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "ChatLog.json"
            log_path.write_text(json.dumps([]), encoding="utf-8")
            with (
                patch.object(chatbot, "client", fake_client),
                patch.object(
                    chatbot,
                    "_get_latest_chatlog_path",
                    return_value=str(log_path),
                ),
                patch.object(chatbot, "append_to_chatlogs") as append_message,
                patch.object(chatbot, "GoogleSearch", None),
            ):
                result = chatbot.ChatBot(
                    "Help with the chair design",
                    max_retries=0,
                    workspace_context="Workbench: chair; parts: seat, legs",
                )

        self.assertEqual(result, "I can help with the chair.")
        sent_messages = fake_client.chat.completions.create.call_args.kwargs[
            "messages"
        ]
        context_messages = [
            message for message in sent_messages
            if "Current AIKO workspace context" in message["content"]
        ]
        self.assertEqual(len(context_messages), 1)
        self.assertIn("parts: seat, legs", context_messages[0]["content"])
        self.assertTrue(
            all(
                "Current AIKO workspace context" not in call.args[1]
                for call in append_message.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
