import sys
import types
import unittest
from unittest.mock import Mock, mock_open, patch

from backend.SoundTrigger import DoubleSoundDetector, DoubleSoundTriggerWorker
from frontend.GUI import ConversationMapScreen


class DoubleSoundDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = DoubleSoundDetector()
        for index in range(10):
            self.detector.process_levels(200, 500, index / 10)

    def sound(self, timestamp):
        return self.detector.process_levels(4000, 22000, timestamp)

    def quiet(self, timestamp):
        return self.detector.process_levels(200, 500, timestamp)

    def test_startup_calibration_ignores_loud_transients(self):
        detector = DoubleSoundDetector()
        self.assertFalse(detector.process_levels(4000, 22000, 0.1))
        self.assertFalse(detector.process_levels(200, 500, 0.2))
        self.assertFalse(detector.process_levels(200, 500, 0.3))
        self.assertFalse(detector.process_levels(4000, 22000, 0.5))

    def test_requires_two_separated_sharp_sounds_within_window(self):
        self.assertFalse(self.sound(1.1))
        self.assertFalse(self.quiet(1.15))
        self.assertFalse(self.quiet(1.2))
        self.assertFalse(self.quiet(1.3))
        self.assertTrue(self.sound(1.4))

    def test_one_sound_does_not_activate(self):
        self.assertFalse(self.sound(1.1))
        self.assertFalse(self.quiet(1.2))

    def test_continuous_loud_audio_is_not_counted_as_repeated_sounds(self):
        self.assertFalse(self.sound(1.1))
        self.assertFalse(self.sound(1.4))
        self.assertFalse(self.sound(1.7))

    def test_sound_after_window_becomes_first_sound_of_new_pair(self):
        self.assertFalse(self.sound(1.1))
        self.assertFalse(self.quiet(1.2))
        self.assertFalse(self.quiet(1.3))
        self.assertFalse(self.quiet(1.35))
        self.assertFalse(self.sound(2.0))
        self.assertFalse(self.quiet(2.1))
        self.assertFalse(self.quiet(2.2))
        self.assertFalse(self.quiet(2.25))
        self.assertTrue(self.sound(2.3))

    def test_speech_level_spikes_do_not_count_as_claps(self):
        self.assertFalse(self.detector.process_levels(1800, 9000, 1.1))
        self.assertFalse(self.quiet(1.2))
        self.assertFalse(self.quiet(1.3))
        self.assertFalse(self.detector.process_levels(1800, 9000, 1.4))
        self.assertFalse(self.quiet(1.5))
        self.assertFalse(self.quiet(1.6))
        self.assertFalse(self.detector.process_levels(1800, 9000, 1.7))

    def test_microphone_open_error_is_reported(self):
        pyaudio = types.ModuleType("pyaudio")
        pyaudio.PyAudio = Mock(side_effect=OSError("no microphone"))
        errors = []
        worker = DoubleSoundTriggerWorker()
        worker.listening_error.connect(errors.append)

        with patch.dict(sys.modules, {"pyaudio": pyaudio}):
            worker.run()

        self.assertEqual(errors, ["Sound trigger stopped: no microphone"])


class DoubleSoundTriggerStartupTests(unittest.TestCase):
    def test_listener_starts_even_when_main_mic_is_off_and_avoids_duplicate_start(self):
        worker = Mock()
        worker.isRunning.return_value = False
        screen = types.SimpleNamespace(
            double_sound_trigger_worker=None,
            double_sound_trigger_status=Mock(),
            _on_double_sound_detected=Mock(),
            _on_double_sound_trigger_error=Mock(),
            _double_sound_trigger_finished=Mock(),
        )
        factory = Mock(return_value=worker)

        with (
            patch("frontend.GUI.GetMicrophoneStatus", return_value="False"),
            patch.dict(
                ConversationMapScreen.start_double_sound_trigger.__globals__,
                {
                    "TempDirectoryPath": Mock(return_value="MicDevice.data"),
                    "DoubleSoundTriggerWorker": factory,
                },
            ),
            patch("builtins.open", mock_open(read_data="")),
        ):
            ConversationMapScreen.start_double_sound_trigger(screen)
            worker.isRunning.return_value = True
            ConversationMapScreen.start_double_sound_trigger(screen)

        factory.assert_called_once_with(None, screen)
        worker.start.assert_called_once_with()
        self.assertIs(screen.double_sound_trigger_worker, worker)
        screen.double_sound_trigger_status.setText.assert_called_once_with(
            "Always listening locally for two sharp sounds to start hand tracking."
        )


if __name__ == "__main__":
    unittest.main()
