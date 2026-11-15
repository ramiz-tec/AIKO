import unittest
from unittest.mock import Mock, patch

from backend.TextToSpeech import TTS


class TextToSpeechTests(unittest.TestCase):
    def test_edge_audio_uses_pygame_for_playback_and_cleanup(self):
        should_continue = Mock(return_value=True)
        with (
            patch("backend.TextToSpeech.os.name", "posix"),
            patch("backend.TextToSpeech.asyncio.run"),
            patch("backend.TextToSpeech.TextToAudioFile", new=Mock()),
            patch("backend.TextToSpeech.pygame") as pygame,
        ):
            pygame.mixer.music.get_busy.side_effect = [True, True, False]
            pygame.mixer.music.get_pos.return_value = 0
            pygame.mixer.get_init.return_value = True

            self.assertTrue(TTS("Hello there.", should_continue))

        pygame.mixer.init.assert_called_once_with()
        pygame.mixer.music.play.assert_called_once_with()
        pygame.mixer.music.stop.assert_called_once_with()
        pygame.mixer.quit.assert_called_once_with()
        should_continue.assert_any_call(False)


if __name__ == "__main__":
    unittest.main()
