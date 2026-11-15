import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend import Reminders


class ReminderAcknowledgementTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.reminders_path = Path(self.temporary_directory.name) / "Reminders.json"
        self.path_patch = patch.object(Reminders, "REMINDERS_PATH", self.reminders_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)

    def test_due_reminder_remains_saved_until_acknowledged(self):
        due_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        reminder = Reminders.SaveReminder("Call Sam", due_at)

        due = Reminders.TakeDueReminders()

        self.assertEqual([item["id"] for item in due], [reminder["id"]])
        self.assertEqual(Reminders.ListReminders()[0]["id"], reminder["id"])
        self.assertTrue(Reminders.ListReminders()[0]["notified"])
        self.assertTrue(Reminders.AcknowledgeReminder(reminder["id"]))
        self.assertEqual(Reminders.ListReminders(), [])

    def test_unknown_reminder_cannot_be_acknowledged(self):
        self.assertFalse(Reminders.AcknowledgeReminder("missing"))

    def test_acknowledgement_accepts_only_requested_phrases(self):
        for phrase in ("ok", "Okay!", "thank you", "Thanks.", "will do"):
            with self.subTest(phrase=phrase):
                self.assertTrue(Reminders.IsReminderAcknowledgement(phrase))
        for phrase in ("okay, remind me", "stop", "thank you very much"):
            with self.subTest(phrase=phrase):
                self.assertFalse(Reminders.IsReminderAcknowledgement(phrase))

    def test_later_reminder_uses_a_clear_one_hour_default_and_simplifies_title(self):
        now = datetime(2026, 11, 14, 13, 0, tzinfo=timezone.utc)

        title, due_at = Reminders.ParseReminderRequest(
            "set me a reminder to update that part of the code later",
            now,
        )

        self.assertEqual(title, "update code")
        self.assertEqual(
            datetime.fromisoformat(due_at),
            now + timedelta(hours=1),
        )


if __name__ == "__main__":
    unittest.main()
