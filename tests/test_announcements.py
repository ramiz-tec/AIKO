import unittest
from datetime import datetime

from backend.Announcements import IsSpeechStopCommand, TimeOfDayGreeting


class SpeechControlTests(unittest.TestCase):
    def test_only_requested_stop_phrases_interrupt_speech(self):
        for phrase in ("stop", "wait!", "shut up", "hold on", "pause."):
            with self.subTest(phrase=phrase):
                self.assertTrue(IsSpeechStopCommand(phrase))
        for phrase in ("stop talking", "thanks", "go ahead", "not now"):
            with self.subTest(phrase=phrase):
                self.assertFalse(IsSpeechStopCommand(phrase))

    def test_greeting_follows_local_time_period_boundaries(self):
        cases = (
            (0, "Good morning"),
            (11, "Good morning"),
            (12, "Good afternoon"),
            (16, "Good afternoon"),
            (17, "Good evening"),
            (23, "Good evening"),
        )
        for hour, expected in cases:
            with self.subTest(hour=hour):
                self.assertEqual(
                    TimeOfDayGreeting(datetime(2026, 11, 14, hour)),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
