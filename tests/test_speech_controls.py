import threading
import unittest
from unittest.mock import patch

import main


class SpeechControlListenerTests(unittest.TestCase):
    def test_non_command_audio_does_not_disable_pause_listening_during_speech(self):
        stop_listening = threading.Event()
        speech_stopped = threading.Event()

        with (
            patch("main.GetMicrophoneStatus", return_value="True"),
            patch(
                "main.SpeechRecognition",
                side_effect=["background sound", "pause."],
            ) as recognize,
            patch("main.SetAssistantStatus"),
            patch("main._acknowledge_active_reminder", return_value=False),
        ):
            main._listen_for_speech_controls(
                stop_listening,
                speech_stopped,
                "active-reminder",
            )

        self.assertTrue(speech_stopped.is_set())
        self.assertEqual(recognize.call_count, 2)

    def test_workspace_and_non_workspace_commands_keep_their_own_routing(self):
        self.assertEqual(
            main._classify_query("select project bridge"),
            "workspace open_project bridge",
        )
        self.assertEqual(
            main._classify_query("create new tab"),
            "desktop new_tab",
        )
        self.assertEqual(
            main._classify_query(
                "remind me to update that part of the code later"
            ),
            "reminder remind me to update that part of the code later",
        )
        self.assertEqual(
            main._classify_query(
                "set me a reminder to update that part of the code later"
            ),
            "reminder set me a reminder to update that part of the code later",
        )
        self.assertEqual(
            main._classify_query("I want to work on a new design of a chair"),
            "workspace create a chair",
        )
        self.assertEqual(
            main._classify_query("what am I working on"),
            "workspace describe",
        )
        self.assertEqual(
            main._classify_query("what is on my workbench"),
            "workspace describe",
        )
        self.assertEqual(
            main._classify_query("go back to project bridge"),
            "workspace open_project bridge",
        )

    def test_google_open_and_search_strip_request_filler_from_query(self):
        with patch.object(main, "_google_search_pending", False):
            self.assertEqual(main._classify_query("open Google"), "open google")
            self.assertEqual(
                main._classify_query(
                    "open google let me see what the weather looks like"
                ),
                "google search weather",
            )
            self.assertEqual(
                main._classify_query(
                    "open google let me see what th weather looks like"
                ),
                "google search weather",
            )
            self.assertEqual(
                main._classify_query(
                    "open google and search for the weather in Seattle"
                ),
                "google search weather in Seattle",
            )
            self.assertEqual(
                main._classify_query("search for weather in Seattle on Google"),
                "google search weather in Seattle",
            )

    def test_google_followup_is_used_as_the_search_query(self):
        with patch.object(main, "_google_search_pending", True):
            self.assertEqual(
                main._classify_query("what's the weather in Seattle?"),
                "google search weather in Seattle",
            )
            self.assertFalse(main._google_search_pending)

    def test_google_followup_can_repeat_open_google_without_searching_that_phrase(self):
        with patch.object(main, "_google_search_pending", True):
            self.assertEqual(main._classify_query("open Google"), "open google")
            self.assertFalse(main._google_search_pending)


if __name__ == "__main__":
    unittest.main()
