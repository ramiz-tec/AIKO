import unittest
from unittest.mock import patch

import main


class ImageGenerationFlowTests(unittest.TestCase):
    def test_picture_request_generates_and_queues_three_options(self):
        image_paths = ["option-1.png", "option-2.png", "option-3.png"]
        with (
            patch.object(main, "GetActiveChatLogPath", return_value="chat.json"),
            patch.object(main, "append_to_chatlogs"),
            patch.object(main, "SetAssistantStatus"),
            patch.object(main, "GenerateImage", return_value=image_paths) as generate,
            patch.object(main, "QueueImageGallery") as queue_gallery,
            patch.object(main, "ChatBot") as chatbot,
            patch.object(main, "UpdateConversationOrbCategory"),
            patch.object(main, "ActivateConversation"),
            patch.object(main, "_speak_text"),
        ):
            main.MainExecution("I want a picture of a red fox")

        generate.assert_called_once_with("a red fox")
        queue_gallery.assert_called_once_with("a red fox", image_paths)
        chatbot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
