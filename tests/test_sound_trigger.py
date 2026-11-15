import sys
import types
import unittest
from unittest.mock import Mock, patch

from backend.SoundTrigger import DoubleSoundDetector, DoubleSoundTriggerWorker


class DoubleSoundDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = DoubleSoundDetector()

    def sound(self, timestamp):
        return self.detector.process_levels(1800, 9000, timestamp)

    def quiet(self, timestamp):
        return self.detector.process_levels(200, 500, timestamp)

    def test_requires_two_separated_sharp_sounds_within_window(self):
        self.assertFalse(self.sound(0.0))
        self.assertFalse(self.quiet(0.1))
        self.assertTrue(self.sound(0.35))

    def test_one_sound_does_not_activate(self):
        self.assertFalse(self.sound(0.0))
        self.assertFalse(self.quiet(0.1))

    def test_continuous_loud_audio_is_not_counted_as_repeated_sounds(self):
        self.assertFalse(self.sound(0.0))
        self.assertFalse(self.detector.process_levels(1800, 9000, 0.3))
        self.assertFalse(self.detector.process_levels(1800, 9000, 0.6))

    def test_sound_after_window_becomes_first_sound_of_new_pair(self):
        self.assertFalse(self.sound(0.0))
        self.assertFalse(self.quiet(0.1))
        self.assertFalse(self.sound(1.0))
        self.assertFalse(self.quiet(1.1))
        self.assertTrue(self.sound(1.3))

    def test_microphone_open_error_is_reported(self):
        pyaudio = types.ModuleType("pyaudio")
        pyaudio.PyAudio = Mock(side_effect=OSError("no microphone"))
        errors = []
        worker = DoubleSoundTriggerWorker()
        worker.listening_error.connect(errors.append)

        with patch.dict(sys.modules, {"pyaudio": pyaudio}):
            worker.run()

        self.assertEqual(errors, ["Sound trigger stopped: no microphone"])


if __name__ == "__main__":
    unittest.main()
