import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend import Reminders
import main


class ReminderTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.reminders_path = Path(self.temporary_directory.name) / "Reminders.json"
        self.path_patch = patch.object(Reminders, "REMINDERS_PATH", self.reminders_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)
        self.previous_reminder = main._active_reminder
        self.addCleanup(self._restore_active_reminder)

    def _restore_active_reminder(self):
        with main._active_reminder_lock:
            main._active_reminder = self.previous_reminder
            main._reminder_acknowledged.clear()

    def test_expiry_timer_deletes_and_dismisses_unacknowledged_reminder(self):
        reminder = Reminders.SaveReminder(
            "Call Sam",
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        )
        with main._active_reminder_lock:
            main._active_reminder = reminder
            main._reminder_acknowledged.clear()

        with patch.object(main, "AcknowledgeReminderNotification") as dismiss:
            timer = main._start_reminder_expiry(reminder["id"], timeout=0.02)
            timer.join(timeout=1)

        self.assertFalse(timer.is_alive())
        self.assertEqual(Reminders.ListReminders(), [])
        self.assertTrue(main._reminder_acknowledged.is_set())
        dismiss.assert_called_once_with(reminder["id"])

    def test_expiry_uses_two_second_default(self):
        with patch.object(main.threading, "Timer") as timer_factory:
            main._start_reminder_expiry("reminder-id")

        timer_factory.assert_called_once_with(
            2.0,
            main._expire_active_reminder,
            args=("reminder-id",),
        )
        timer_factory.return_value.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
