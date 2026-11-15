import math
import sys
import time
from array import array

from PyQt5.QtCore import QThread, pyqtSignal


_AUDIO_RATE = 16000
_AUDIO_CHUNK_SIZE = 1024
_MIN_DOUBLE_SOUND_GAP = 0.12
_MAX_DOUBLE_SOUND_GAP = 0.8


class DoubleSoundDetector:
    def __init__(self):
        self._noise_level = 300.0
        self._last_sound_at = None
        self._armed = True

    def process_levels(self, rms: float, peak: int, timestamp: float) -> bool:
        threshold = max(900.0, self._noise_level * 2.5)
        is_sharp_sound = (
            rms >= threshold
            and peak >= max(5000, self._noise_level * 6)
            and peak >= rms * 2
        )
        if not is_sharp_sound:
            self._armed = True
            self._noise_level = max(
                100.0,
                self._noise_level * 0.95 + min(rms, threshold) * 0.05,
            )
            return False

        if not self._armed:
            return False
        self._armed = False
        if self._last_sound_at is None:
            self._last_sound_at = timestamp
            return False

        gap = timestamp - self._last_sound_at
        if gap < _MIN_DOUBLE_SOUND_GAP:
            return False
        if gap > _MAX_DOUBLE_SOUND_GAP:
            self._last_sound_at = timestamp
            return False
        self._last_sound_at = None
        return True


class DoubleSoundTriggerWorker(QThread):
    double_sound_detected = pyqtSignal()
    listening_error = pyqtSignal(str)

    def __init__(self, device_index=None, parent=None):
        super().__init__(parent)
        self.device_index = device_index

    def run(self) -> None:
        try:
            import pyaudio
        except ImportError:
            self.listening_error.emit(
                "PyAudio is missing. Install the desktop requirements with "
                "`pip install -r requirements.txt`."
            )
            return

        audio = None
        stream = None
        try:
            audio = pyaudio.PyAudio()
            device_info = (
                audio.get_device_info_by_index(self.device_index)
                if self.device_index is not None
                else audio.get_default_input_device_info()
            )
            sample_rate = int(device_info.get("defaultSampleRate", _AUDIO_RATE))
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=_AUDIO_CHUNK_SIZE,
            )
            detector = DoubleSoundDetector()
            while not self.isInterruptionRequested():
                raw_audio = stream.read(
                    _AUDIO_CHUNK_SIZE,
                    exception_on_overflow=False,
                )
                samples = array("h")
                samples.frombytes(raw_audio)
                if sys.byteorder != "little":
                    samples.byteswap()
                if not samples:
                    continue
                peak = max(abs(sample) for sample in samples)
                rms = math.sqrt(
                    sum(sample * sample for sample in samples) / len(samples)
                )
                if detector.process_levels(rms, peak, time.monotonic()):
                    self.double_sound_detected.emit()
        except (OSError, RuntimeError, ValueError) as error:
            if not self.isInterruptionRequested():
                self.listening_error.emit(f"Sound trigger stopped: {error}")
        finally:
            try:
                if stream is not None:
                    try:
                        stream.stop_stream()
                    finally:
                        stream.close()
            finally:
                if audio is not None:
                    audio.terminate()
