import ctypes
import math
import os
from pathlib import Path
import time
from typing import Sequence

from PyQt5.QtCore import QThread, pyqtSignal


_HAND_LANDMARKER_MODEL = (
    Path(__file__).resolve().parent / "models" / "hand_landmarker.task"
)
_LANDMARK_FRAME_TOLERANCE = 0.05
_CAMERA_FRAME_WIDTH = 320
_CAMERA_FRAME_HEIGHT = 240
_CAMERA_TARGET_FPS = 20


def measure_hand_landmarks(
    landmarks: Sequence[object],
) -> tuple[float, float, float, float, bool, int, float, float, float]:
    """Measure hand gestures and palm size as a relative depth signal."""
    if len(landmarks) != 21:
        raise ValueError("A complete 21-point hand landmark set is required.")
    if any(
        not math.isfinite(float(point.x))
        or not math.isfinite(float(point.y))
        or not math.isfinite(float(point.z))
        or not -_LANDMARK_FRAME_TOLERANCE <= float(point.x) <= 1 + _LANDMARK_FRAME_TOLERANCE
        or not -_LANDMARK_FRAME_TOLERANCE <= float(point.y) <= 1 + _LANDMARK_FRAME_TOLERANCE
        for point in landmarks
    ):
        raise ValueError("All 21 hand landmarks must be visible within the camera frame.")

    wrist = landmarks[0]
    middle_mcp = landmarks[9]
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    palm_size = math.hypot(
        float(wrist.x) - float(middle_mcp.x),
        float(wrist.y) - float(middle_mcp.y),
    )
    if palm_size <= 0:
        raise ValueError("The hand landmarks do not have a measurable palm size.")

    pinch_distance = math.hypot(
        float(thumb_tip.x) - float(index_tip.x),
        float(thumb_tip.y) - float(index_tip.y),
    ) / palm_size
    pointer_x = (float(thumb_tip.x) + float(index_tip.x)) / 2
    pointer_y = (float(thumb_tip.y) + float(index_tip.y)) / 2
    finger_extension = sum(
        math.sqrt(
            (float(landmarks[tip].x) - float(wrist.x)) ** 2
            + (float(landmarks[tip].y) - float(wrist.y)) ** 2
            + (float(landmarks[tip].z) - float(wrist.z)) ** 2
        )
        for tip in (8, 12, 16, 20)
    ) / (4 * palm_size)
    fist_openness = min(1.0, max(0.0, (finger_extension - 0.72) / 1.15))
    fingers_extended = all(
        math.sqrt(
            (float(landmarks[tip].x) - float(wrist.x)) ** 2
            + (float(landmarks[tip].y) - float(wrist.y)) ** 2
            + (float(landmarks[tip].z) - float(wrist.z)) ** 2
        )
        > 1.1 * math.sqrt(
            (float(landmarks[pip].x) - float(wrist.x)) ** 2
            + (float(landmarks[pip].y) - float(wrist.y)) ** 2
            + (float(landmarks[pip].z) - float(wrist.z)) ** 2
        )
        for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18))
    )
    open_palm = fingers_extended and pinch_distance >= 0.3

    index_base = landmarks[5]
    pinky_base = landmarks[17]
    first = (
        float(index_base.x) - float(wrist.x),
        float(index_base.y) - float(wrist.y),
        float(index_base.z) - float(wrist.z),
    )
    second = (
        float(pinky_base.x) - float(wrist.x),
        float(pinky_base.y) - float(wrist.y),
        float(pinky_base.z) - float(wrist.z),
    )
    normal_y = first[2] * second[0] - first[0] * second[2]
    normal_size = math.sqrt(
        (first[1] * second[2] - first[2] * second[1]) ** 2
        + normal_y**2
        + (first[0] * second[1] - first[1] * second[0]) ** 2
    )
    facing_threshold = normal_size * 0.35
    palm_facing = (
        1 if normal_y < -facing_threshold
        else -1 if normal_y > facing_threshold
        else 0
    )
    hand_center_y = sum(float(point.y) for point in landmarks) / len(landmarks)
    hand_center_x = sum(float(point.x) for point in landmarks) / len(landmarks)
    return (
        pointer_x,
        pointer_y,
        pinch_distance,
        fist_openness,
        open_palm,
        palm_facing,
        hand_center_x,
        hand_center_y,
        palm_size,
    )


def volume_action_for_motion(vertical_motion: float, palm_facing: int) -> bool | None:
    if palm_facing > 0 and vertical_motion > 0:
        return True
    if palm_facing < 0 and vertical_motion < 0:
        return False
    return None


def zoom_openness_for_hand(pinch_distance: float, fist_openness: float) -> float:
    if fist_openness < 0.15:
        return 0.0
    neutral_openness = 1.0 / 3.0
    aperture_openness = min(
        1.0,
        max(0.0, (pinch_distance - 0.55) / 0.4),
    )
    return neutral_openness + aperture_openness * (1.0 - neutral_openness)


def zoom_openness_for_two_hands(hand_distance: float) -> float:
    return min(1.0, max(0.0, (hand_distance - 0.2) / 0.45))


def adjust_system_volume(increase: bool) -> None:
    """Send one Windows master-volume key step."""
    if os.name != "nt":
        raise RuntimeError("Hand gesture volume control is available only on Windows.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.keybd_event.argtypes = [
        ctypes.c_ubyte,
        ctypes.c_ubyte,
        ctypes.c_ulong,
        ctypes.c_size_t,
    ]
    user32.keybd_event.restype = None
    virtual_key = 0xAF if increase else 0xAE
    user32.keybd_event(virtual_key, 0, 0, 0)
    user32.keybd_event(virtual_key, 0, 2, 0)


class HandTrackingWorker(QThread):
    camera_ready = pyqtSignal()
    hand_detected = pyqtSignal(object)
    hand_lost = pyqtSignal()
    tracking_error = pyqtSignal(str)

    def run(self) -> None:
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            self.tracking_error.emit(
                "Hand tracking packages are missing. Install the desktop "
                "requirements with `pip install -r requirements.txt`."
            )
            return

        if not _HAND_LANDMARKER_MODEL.is_file():
            self.tracking_error.emit(
                f"The local hand-landmarker model is missing: "
                f"{_HAND_LANDMARKER_MODEL}"
            )
            return

        camera = None
        try:
            camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not camera.isOpened():
                self.tracking_error.emit(
                    "AIKO could not open the default camera. Check that it is "
                    "connected and not being used by another app."
                )
                return

            camera.set(cv2.CAP_PROP_FRAME_WIDTH, _CAMERA_FRAME_WIDTH)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, _CAMERA_FRAME_HEIGHT)
            camera.set(cv2.CAP_PROP_FPS, _CAMERA_TARGET_FPS)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            options = vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(
                    model_asset_path=str(_HAND_LANDMARKER_MODEL)
                ),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            with vision.HandLandmarker.create_from_options(options) as hands:
                self.camera_ready.emit()
                was_tracking = False
                timestamp_ms = 0
                consecutive_read_failures = 0
                while not self.isInterruptionRequested():
                    frame_started = time.monotonic()
                    success, frame = camera.read()
                    if not success:
                        consecutive_read_failures += 1
                        if consecutive_read_failures >= 30:
                            self.tracking_error.emit(
                                "The camera stopped providing frames. Check the "
                                "camera connection and try enabling hand tracking again."
                            )
                            return
                        self.msleep(25)
                        continue

                    consecutive_read_failures = 0
                    if (
                        frame.shape[1] != _CAMERA_FRAME_WIDTH
                        or frame.shape[0] != _CAMERA_FRAME_HEIGHT
                    ):
                        frame = cv2.resize(
                            frame,
                            (_CAMERA_FRAME_WIDTH, _CAMERA_FRAME_HEIGHT),
                            interpolation=cv2.INTER_AREA,
                        )
                    frame = cv2.flip(frame, 1)
                    image = mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    )
                    timestamp_ms = max(
                        timestamp_ms + 1,
                        int(time.monotonic() * 1000),
                    )
                    result = hands.detect_for_video(image, timestamp_ms)
                    if result.hand_landmarks:
                        detected_hands = []
                        for landmarks in result.hand_landmarks:
                            try:
                                detected_hands.append(measure_hand_landmarks(landmarks))
                            except (AttributeError, IndexError, TypeError, ValueError):
                                continue
                        if detected_hands:
                            self.hand_detected.emit(detected_hands)
                            was_tracking = True
                        elif was_tracking:
                            self.hand_lost.emit()
                            was_tracking = False
                    elif was_tracking:
                        self.hand_lost.emit()
                        was_tracking = False
                    remaining_ms = int(
                        1000 / _CAMERA_TARGET_FPS
                        - (time.monotonic() - frame_started) * 1000
                    )
                    if remaining_ms > 0:
                        self.msleep(remaining_ms)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError, cv2.error) as error:
            self.tracking_error.emit(f"Hand tracking stopped: {error}")
        finally:
            if camera is not None:
                camera.release()
