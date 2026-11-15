import os
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPoint, QRect, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QDialog, QPushButton, QWidget
from types import SimpleNamespace

from backend.HandTracking import (
    adjust_system_volume,
    measure_hand_landmarks,
    volume_action_for_motion,
    zoom_openness_for_hand,
    zoom_openness_for_two_hands,
)
from frontend.GUI import (
    ConversationMapScreen,
    HandCursorOverlay,
    HologramCanvas,
    OrbMapCanvas,
    _hand_click_is_valid,
    _send_hand_mouse_event,
)


def make_landmarks():
    points = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    points[0] = SimpleNamespace(x=0.5, y=0.8, z=0.0)
    points[9] = SimpleNamespace(x=0.5, y=0.5, z=0.0)
    points[4] = SimpleNamespace(x=0.55, y=0.35, z=0.0)
    points[6] = SimpleNamespace(x=0.5, y=0.42, z=0.0)
    points[8] = SimpleNamespace(x=0.45, y=0.35, z=0.0)
    for tip, pip in ((12, 10), (16, 14), (20, 18)):
        points[pip] = SimpleNamespace(x=0.5, y=0.42, z=0.0)
        points[tip] = SimpleNamespace(x=0.5, y=0.25, z=0.0)
    return points


class MeasureHandLandmarksTests(unittest.TestCase):
    def test_returns_pointer_midpoint_and_normalized_pinch_distance(self):
        (
            x, y, pinch_distance, fist_openness, open_palm,
            palm_facing, hand_center_x, hand_center_y,
            hand_depth,
        ) = measure_hand_landmarks(make_landmarks())

        self.assertAlmostEqual(x, 0.5)
        self.assertAlmostEqual(y, 0.35)
        self.assertAlmostEqual(pinch_distance, 1 / 3)
        self.assertGreater(fist_openness, 0.5)
        self.assertTrue(open_palm)
        self.assertEqual(palm_facing, 0)
        self.assertAlmostEqual(hand_center_x, 0.5)
        self.assertAlmostEqual(hand_center_y, 0.44904761904761903)
        self.assertAlmostEqual(hand_depth, 0.3)

    def test_closed_pinch_is_not_an_open_palm(self):
        landmarks = make_landmarks()
        landmarks[4] = SimpleNamespace(x=0.505, y=0.35, z=0.0)
        landmarks[8] = SimpleNamespace(x=0.495, y=0.35, z=0.0)

        _x, _y, pinch_distance, _openness, open_palm, *_rest = measure_hand_landmarks(landmarks)

        self.assertLess(pinch_distance, 0.3)
        self.assertFalse(open_palm)

    def test_folded_finger_is_not_an_open_palm(self):
        landmarks = make_landmarks()
        landmarks[12] = SimpleNamespace(x=0.5, y=0.45, z=0.0)

        _x, _y, _pinch_distance, _openness, open_palm, *_rest = measure_hand_landmarks(landmarks)

        self.assertFalse(open_palm)

    def test_closed_fist_has_lower_openness_than_open_hand(self):
        open_landmarks = make_landmarks()
        fist_landmarks = make_landmarks()
        for tip in (8, 12, 16, 20):
            fist_landmarks[tip] = SimpleNamespace(x=0.5, y=0.65, z=0.0)

        open_openness = measure_hand_landmarks(open_landmarks)[3]
        fist_openness = measure_hand_landmarks(fist_landmarks)[3]

        self.assertGreater(open_openness, fist_openness)

    def test_requires_all_21_landmarks_inside_camera_frame(self):
        with self.assertRaisesRegex(ValueError, "21-point"):
            measure_hand_landmarks(make_landmarks()[:20])

        landmarks = make_landmarks()
        landmarks[20] = SimpleNamespace(x=1.1, y=0.5, z=0.0)
        with self.assertRaisesRegex(ValueError, "within the camera frame"):
            measure_hand_landmarks(landmarks)

    def test_tolerates_small_landmark_overshoot_at_camera_edges(self):
        landmarks = make_landmarks()
        landmarks[20] = SimpleNamespace(x=-0.02, y=1.02, z=0.0)

        measured = measure_hand_landmarks(landmarks)

        self.assertEqual(len(measured), 9)

    def test_palm_orientation_distinguishes_up_from_down(self):
        palm_up = make_landmarks()
        palm_down = make_landmarks()
        for landmarks, pinky_z in ((palm_up, 0.3), (palm_down, -0.3)):
            landmarks[5] = SimpleNamespace(x=0.6, y=0.7, z=0.0)
            landmarks[17] = SimpleNamespace(x=0.5, y=0.7, z=pinky_z)

        self.assertEqual(measure_hand_landmarks(palm_up)[5], 1)
        self.assertEqual(measure_hand_landmarks(palm_down)[5], -1)


class VolumeGestureTests(unittest.TestCase):
    def test_volume_up_requires_raising_a_palm_facing_up(self):
        self.assertIs(volume_action_for_motion(0.05, 1), True)
        self.assertIsNone(volume_action_for_motion(-0.05, 1))

    def test_volume_down_requires_lowering_a_palm_facing_down(self):
        self.assertIs(volume_action_for_motion(-0.05, -1), False)
        self.assertIsNone(volume_action_for_motion(0.05, -1))

    def test_neutral_palm_does_not_change_volume(self):
        self.assertIsNone(volume_action_for_motion(0.05, 0))


class ZoomGestureTests(unittest.TestCase):
    def test_spreading_thumb_and_index_increases_zoom_openness(self):
        relaxed = zoom_openness_for_hand(0.33, 0.8)
        spread = zoom_openness_for_hand(0.7, 0.8)

        self.assertAlmostEqual(relaxed, 1 / 3)
        self.assertGreater(spread, relaxed)
        self.assertLessEqual(spread, 1.0)

    def test_closing_fist_sets_zoom_out_even_if_thumb_and_index_are_apart(self):
        self.assertEqual(zoom_openness_for_hand(0.8, 0.0), 0.0)

    def test_pinching_without_a_closed_fist_does_not_trigger_zoom_out(self):
        self.assertAlmostEqual(zoom_openness_for_hand(0.18, 0.5), 1 / 3)

    def test_zoom_in_requires_deliberately_spreading_thumb_and_index(self):
        self.assertAlmostEqual(zoom_openness_for_hand(0.4, 0.5), 1 / 3)
        self.assertGreater(zoom_openness_for_hand(0.7, 0.5), 1 / 3)

    def test_spreading_two_hands_controls_zoom_openness(self):
        self.assertEqual(zoom_openness_for_two_hands(0.2), 0.0)
        self.assertAlmostEqual(zoom_openness_for_two_hands(0.425), 0.5)
        self.assertEqual(zoom_openness_for_two_hands(0.65), 1.0)


@unittest.skipUnless(os.name == "nt", "Windows master-volume keys are Windows-specific")
class SystemVolumeTests(unittest.TestCase):
    @patch("backend.HandTracking.ctypes.WinDLL")
    def test_raise_gesture_sends_volume_up_key_down_and_up(self, load_user32):
        adjust_system_volume(True)

        load_user32.assert_called_once_with("user32", use_last_error=True)
        load_user32.return_value.keybd_event.assert_has_calls(
            [call(0xAF, 0, 0, 0), call(0xAF, 0, 2, 0)]
        )

    @patch("backend.HandTracking.ctypes.WinDLL")
    def test_lower_gesture_sends_volume_down_key_down_and_up(self, load_user32):
        adjust_system_volume(False)

        load_user32.return_value.keybd_event.assert_has_calls(
            [call(0xAE, 0, 0, 0), call(0xAE, 0, 2, 0)]
        )


class OrbMapHandGestureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_drag_rotates_map_at_hand_speed_and_hand_zoom_is_smooth(self):
        canvas = OrbMapCanvas()
        canvas.resize(500, 400)
        canvas.show()
        self.app.processEvents()
        initial_rotation = canvas.rotation

        _send_hand_mouse_event(
            canvas, QEvent.MouseButtonPress, QPoint(100, 100),
            Qt.LeftButton, Qt.LeftButton,
        )
        _send_hand_mouse_event(
            canvas, QEvent.MouseMove, QPoint(120, 115),
            Qt.NoButton, Qt.LeftButton,
        )
        _send_hand_mouse_event(
            canvas, QEvent.MouseButtonRelease, QPoint(120, 115),
            Qt.LeftButton, Qt.NoButton,
        )
        initial_zoom = canvas.zoom
        canvas.set_hand_zoom(0.0)
        zoomed_out = canvas.zoom
        canvas.set_hand_zoom(1.0)
        zoomed_in = canvas.zoom
        expected_first_step = (0.65 - initial_zoom) * 0.05625

        self.assertNotEqual(canvas.rotation, initial_rotation)
        self.assertAlmostEqual(canvas.rotation - initial_rotation, 20 * 0.004)
        self.assertLess(zoomed_out, initial_zoom)
        self.assertGreater(zoomed_in, zoomed_out)
        self.assertLess(zoomed_in - zoomed_out, 0.1)
        self.assertAlmostEqual(zoomed_out - initial_zoom, expected_first_step)
        canvas.set_hand_cursor(QPoint(50, 50))
        canvas.render(QPixmap(canvas.size()))
        canvas.close()

    def test_hand_cursor_overlay_is_click_through_and_tracks_both_hands(self):
        overlay = HandCursorOverlay()
        positions = [QPoint(40, 60), QPoint(140, 160)]

        overlay.set_positions(positions)

        self.assertTrue(overlay.testAttribute(Qt.WA_TransparentForMouseEvents))
        self.assertEqual(overlay.positions, positions)
        overlay.close()

    def test_zoom_smoothly_responds_to_each_new_fist_sample(self):
        canvas = OrbMapCanvas()
        initial_zoom = canvas.zoom
        canvas.set_hand_zoom(0.8)
        first_frame_zoom = canvas.zoom
        canvas.set_hand_zoom(0.8)

        self.assertGreater(first_frame_zoom, initial_zoom)
        self.assertGreater(canvas.zoom, first_frame_zoom)
        self.assertLess(canvas.zoom, 0.65 + 0.8 * 1.05)

    def test_two_pinched_hands_move_map_by_the_average_hand_motion(self):
        canvas = OrbMapCanvas()
        canvas.resize(500, 400)
        initial_rotation = canvas.rotation
        initial_tilt = canvas.vertical_rotation

        canvas.apply_hand_drag(0.1, 0.05)

        self.assertAlmostEqual(canvas.rotation - initial_rotation, 0.2)
        self.assertAlmostEqual(canvas.vertical_rotation - initial_tilt, 0.08)

    def test_map_and_hologram_pitch_can_rotate_through_full_turns(self):
        map_canvas = OrbMapCanvas()
        map_canvas.resize(500, 400)
        map_canvas.apply_hand_drag(2.0, 4.0)

        hologram = HologramCanvas()
        hologram.resize(420, 320)
        hologram.apply_hand_drag(6.0, 20.0)

        self.assertGreater(map_canvas.rotation, math.pi)
        self.assertGreater(map_canvas.vertical_rotation, 2 * math.pi)
        self.assertLess(hologram.rotation, -math.pi)
        self.assertGreater(hologram.vertical_rotation, 2 * math.pi)
        map_canvas.close()
        hologram.close()

    def test_two_hand_handler_uses_closing_distance_for_zoom_and_pinched_motion_for_rotation(self):
        class FakeWindow:
            def isActiveWindow(self):
                return True

            def centralWidget(self):
                return self

            def currentWidget(self):
                return screen

            def mapToGlobal(self, point):
                return point

            def width(self):
                return 500

            def height(self):
                return 400

        class FakeCanvas:
            def __init__(self):
                self.zoom_values = []
                self.drag_values = []
                self.cursor_positions = []

            def set_hand_cursor(self, _position):
                pass

            def set_hand_cursors(self, positions):
                self.cursor_positions = list(positions)

            def rect(self):
                return QRect(0, 0, 500, 400)

            def mapFromGlobal(self, point):
                return point

            def set_hand_zoom(self, openness):
                self.zoom_values.append(openness)

            def apply_hand_drag(self, delta_x, delta_y):
                self.drag_values.append((delta_x, delta_y))

        screen = SimpleNamespace(
            window=lambda: FakeWindow(),
            canvas=FakeCanvas(),
            hand_cursor_overlay=None,
            _two_hand_drag_position=None,
            _two_hand_depth_position=None,
            _cancel_hand_gesture=Mock(),
            _adopt_two_hand_state=lambda _positions: None,
            _release_other_hand_states=lambda _active_ids: None,
            _set_hand_cursor_positions=lambda positions: setattr(
                screen, "global_cursor_positions", list(positions)
            ),
            _update_hand_volume=lambda *_args: None,
            _hand_gesture_states={},
            _pending_hand_clicks={},
            _hand_is_pinched=lambda _hand_id, distance, openness: (
                distance < 0.18 and openness >= 0.15
            ),
            _update_hand_interaction=lambda *_args: None,
            hand_tracking_status=Mock(),
        )
        screen.hand_tracking_status.text.return_value = "Camera active; no hand detected."

        def metrics(center_x, center_y, pinch_distance=0.4):
            return (center_x, center_y, pinch_distance, 0.5, False, 0, center_x, center_y)

        ConversationMapScreen._on_two_hands_detected(
            screen, [metrics(0.3, 0.5), metrics(0.7, 0.5)]
        )
        self.assertAlmostEqual(screen.canvas.zoom_values[0], zoom_openness_for_two_hands(0.4))
        self.assertEqual(
            screen.canvas.cursor_positions, [QPoint(150, 200), QPoint(349, 200)]
        )

        screen.canvas.zoom_values.clear()
        ConversationMapScreen._on_two_hands_detected(
            screen, [metrics(0.31, 0.5, 0.1), metrics(0.71, 0.5, 0.1)]
        )
        self.assertEqual(screen.canvas.drag_values, [])
        self.assertEqual(
            screen.canvas.cursor_positions, [QPoint(155, 200), QPoint(354, 200)]
        )
        ConversationMapScreen._on_two_hands_detected(
            screen, [metrics(0.32, 0.51, 0.1), metrics(0.72, 0.51, 0.1)]
        )
        self.assertAlmostEqual(screen.canvas.drag_values[0][0], 0.01)
        self.assertAlmostEqual(screen.canvas.drag_values[0][1], 0.01)

    def test_two_pinched_hands_manipulate_a_workspace_item_before_view_rotation(self):
        class FakeWindow:
            def __init__(self):
                self.workspace_screen = SimpleNamespace(viewer=FakeCanvas())

            def centralWidget(self):
                return self

            def currentWidget(self):
                return self.workspace_screen

            def mapToGlobal(self, point):
                return point

            def width(self):
                return 500

            def height(self):
                return 400

        class FakeCanvas:
            def __init__(self):
                self.drag_values = []
                self.manipulation_positions = []
                self.depth_deltas = []

            def rect(self):
                return QRect(0, 0, 500, 400)

            def mapFromGlobal(self, point):
                return point

            def set_hand_cursors(self, _positions):
                pass

            def update_two_hand_item_manipulation(self, positions, depth_delta=0.0):
                self.manipulation_positions.append(positions)
                self.depth_deltas.append(depth_delta)
                return True

            def end_two_hand_item_manipulation(self):
                pass

            def apply_hand_drag(self, delta_x, delta_y):
                self.drag_values.append((delta_x, delta_y))

        window = FakeWindow()
        screen = SimpleNamespace(
            window=lambda: window,
            canvas=FakeCanvas(),
            hand_cursor_overlay=None,
            _two_hand_drag_position=None,
            _two_hand_depth_position=None,
            _cancel_hand_gesture=Mock(),
            _adopt_two_hand_state=lambda _positions: None,
            _release_other_hand_states=lambda _active_ids: None,
            _set_hand_cursor_positions=lambda _positions: None,
            _update_hand_volume=lambda *_args: None,
            _hand_gesture_states={},
            _pending_hand_clicks={},
            _hand_is_pinched=lambda _hand_id, distance, openness: (
                distance < 0.18 and openness >= 0.15
            ),
            _update_hand_interaction=lambda *_args: None,
            hand_tracking_status=Mock(),
        )

        def metrics(center_x, center_y, depth):
            return (
                center_x,
                center_y,
                0.1,
                0.5,
                False,
                0,
                center_x,
                center_y,
                depth,
            )

        ConversationMapScreen._on_two_hands_detected(
            screen, [metrics(0.35, 0.5, 0.3), metrics(0.65, 0.5, 0.3)]
        )
        ConversationMapScreen._on_two_hands_detected(
            screen, [metrics(0.35, 0.5, 0.32), metrics(0.65, 0.5, 0.32)]
        )

        self.assertEqual(len(window.workspace_screen.viewer.manipulation_positions), 2)
        self.assertEqual(
            window.workspace_screen.viewer.depth_deltas,
            [0.0, 0.020000000000000018],
        )
        self.assertEqual(window.workspace_screen.viewer.drag_values, [])

    def test_single_hand_handler_accepts_palm_size_depth_metric(self):
        class FakeWindow:
            def centralWidget(self):
                return self

            def currentWidget(self):
                return workspace

            def mapToGlobal(self, point):
                return point

            def width(self):
                return 500

            def height(self):
                return 400

        class FakeCanvas:
            def mapFromGlobal(self, point):
                return point

            def rect(self):
                return QRect(0, 0, 500, 400)

            def set_hand_cursor(self, _position):
                pass

        class FakeViewer:
            def mapFromGlobal(self, point):
                return point

            def rect(self):
                return QRect(0, 0, 500, 400)

            def end_two_hand_item_manipulation(self):
                pass

        workspace = SimpleNamespace(viewer=FakeViewer())
        window = FakeWindow()
        window.workspace_screen = workspace
        metrics = (0.5, 0.5, 0.1, 0.5, False, 0, 0.5, 0.5, 0.3)
        screen = SimpleNamespace(
            window=lambda: window,
            canvas=FakeCanvas(),
            _two_hand_drag_position=None,
            _two_hand_depth_position=None,
            _adopt_single_hand_state=lambda _position: None,
            _set_hand_cursor_positions=lambda _positions: None,
            _hand_is_pinched=lambda *_args: True,
            _update_hand_volume=Mock(),
            _update_hand_interaction=Mock(),
            _update_single_hand_workbench_depth=Mock(),
            hand_tracking_status=Mock(),
        )
        screen.hand_tracking_status.text.return_value = ""

        ConversationMapScreen._on_hand_detected(screen, [metrics])

        screen._update_hand_interaction.assert_called_once()
        screen._update_single_hand_workbench_depth.assert_called_once_with(
            metrics, True
        )

    def test_two_hands_can_hold_independent_controls_and_release_one(self):
        parent = QWidget()
        left_button = QPushButton("Left", parent)
        right_button = QPushButton("Right", parent)
        left_button.move(0, 0)
        right_button.move(150, 0)
        parent.resize(300, 100)
        parent.show()
        self.app.processEvents()
        clicked = []
        left_button.clicked.connect(lambda: clicked.append("left"))
        right_button.clicked.connect(lambda: clicked.append("right"))
        left_position = left_button.mapToGlobal(left_button.rect().center())
        right_position = right_button.mapToGlobal(right_button.rect().center())

        screen = SimpleNamespace(
            _hand_gesture_states={},
            _pending_hand_clicks={},
            _hand_target_at=lambda position: (
                left_button if position.x() < right_position.x() else right_button
            ),
            _send_hand_pointer_event=lambda target, event_type, point, button, buttons: (
                ConversationMapScreen._send_hand_pointer_event(
                    screen, target, event_type, point, button, buttons
                )
            ),
            _send_hand_mouse_event=lambda target, event_type, point, button, buttons: (
                _send_hand_mouse_event(target, event_type, point, button, buttons)
            ),
            canvas=Mock(),
        )
        screen._release_hand_gesture = lambda state, position=None, allow_click=True: (
            ConversationMapScreen._release_hand_gesture(
                screen, state, position, allow_click
            )
        )
        left_metrics = (0, 0, 0.1, 0.5, False, 0, 0, 0)
        right_metrics = (0, 0, 0.1, 0.5, False, 0, 0, 0)
        ConversationMapScreen._update_hand_interaction(
            screen, "left", left_metrics, left_position, True
        )
        ConversationMapScreen._update_hand_interaction(
            screen, "right", right_metrics, right_position, True
        )
        ConversationMapScreen._update_hand_interaction(
            screen, "left", left_metrics, left_position + QPoint(20, 0), True
        )
        ConversationMapScreen._update_hand_interaction(
            screen, "right", right_metrics, right_position + QPoint(20, 0), True
        )

        self.assertTrue(left_button.isDown())
        self.assertTrue(right_button.isDown())
        ConversationMapScreen._update_hand_interaction(
            screen, "left", left_metrics, left_position + QPoint(20, 0), False
        )

        self.assertEqual(clicked, [])
        self.assertTrue(right_button.isDown())
        self.assertIn("right", screen._hand_gesture_states)
        ConversationMapScreen._update_hand_interaction(
            screen, "right", right_metrics, right_position + QPoint(20, 0), False
        )
        self.assertEqual(clicked, [])
        parent.close()

    def test_hand_target_can_select_controls_in_generated_image_dialogs(self):
        main_window = QWidget()
        chat_section = QWidget(main_window)
        image_dialog = QDialog(chat_section, Qt.Window)
        choose_button = QPushButton("Choose this image", image_dialog)
        choose_button.show()
        image_dialog.show()
        main_window.show()
        self.app.processEvents()
        screen = SimpleNamespace(
            window=lambda: main_window,
            canvas=Mock(),
        )

        with patch("frontend.GUI.QApplication.widgetAt", return_value=choose_button):
            target = ConversationMapScreen._hand_target_at(screen, QPoint(10, 10))

        self.assertIs(target, choose_button)
        image_dialog.close()
        main_window.close()

    def test_click_requires_stationary_non_fist_pinch_but_can_be_held(self):
        self.assertTrue(_hand_click_is_valid(False, False))
        self.assertFalse(_hand_click_is_valid(True, False))
        self.assertFalse(_hand_click_is_valid(False, True))

    def test_suppressed_pinch_release_cannot_click_a_button(self):
        button = QPushButton("Test")
        button.resize(120, 40)
        button.show()
        self.app.processEvents()
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        position = button.rect().center()

        _send_hand_mouse_event(
            button, QEvent.MouseButtonPress, position,
            Qt.LeftButton, Qt.LeftButton,
        )
        screen = SimpleNamespace(
            _hand_gesture_states={
                "left": {
                    "target": button,
                    "position": position,
                    "start_position": QPoint(10, 10),
                    "moved": False,
                    "fist_seen": False,
                    "pressed": True,
                    "mode": "grab",
                }
            },
            _pending_hand_clicks={},
            canvas=Mock(),
        )
        screen._release_hand_gesture = lambda state, position=None, allow_click=True: (
            ConversationMapScreen._release_hand_gesture(
                screen, state, position, allow_click
            )
        )
        ConversationMapScreen._cancel_hand_gesture(screen)

        self.assertEqual(clicked, [])
        self.assertEqual(screen._hand_gesture_states, {})
        button.close()

    def test_double_pinch_clicks_but_a_single_quick_pinch_does_not(self):
        button = QPushButton("Test")
        button.resize(120, 40)
        button.show()
        self.app.processEvents()
        position = button.mapToGlobal(button.rect().center())
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        screen = SimpleNamespace(
            _hand_gesture_states={},
            _pending_hand_clicks={},
            _hand_target_at=lambda _position: button,
            _send_hand_pointer_event=lambda target, event_type, point, button, buttons: (
                ConversationMapScreen._send_hand_pointer_event(
                    screen, target, event_type, point, button, buttons
                )
            ),
            _send_hand_mouse_event=lambda target, event_type, point, button, buttons: (
                _send_hand_mouse_event(target, event_type, point, button, buttons)
            ),
            _send_hand_pointer_click=lambda target, point: (
                ConversationMapScreen._send_hand_pointer_click(screen, target, point)
            ),
            _workspace_click_target=lambda _target: False,
            canvas=Mock(),
        )
        metrics = (0, 0, 0.1, 0.5, False, 0, 0, 0)

        with patch("frontend.GUI.time.monotonic", side_effect=[10.0, 10.1, 10.1, 10.2]):
            ConversationMapScreen._update_hand_interaction(
                screen, "single", metrics, position, True
            )
            self.assertEqual(clicked, [])
            ConversationMapScreen._update_hand_interaction(
                screen, "single", metrics, position, False
            )
            self.assertEqual(clicked, [])
            ConversationMapScreen._update_hand_interaction(
                screen, "single", metrics, position, True
            )

        self.assertEqual(clicked, [True])
        button.close()

    def test_single_pinch_drag_starts_a_grab_without_double_pinch(self):
        button = QPushButton("Test")
        button.resize(120, 40)
        button.show()
        self.app.processEvents()
        position = button.mapToGlobal(button.rect().center())
        pressed = []
        button.pressed.connect(lambda: pressed.append(True))
        screen = SimpleNamespace(
            _hand_gesture_states={},
            _pending_hand_clicks={},
            _hand_target_at=lambda _position: button,
            _send_hand_pointer_event=lambda target, event_type, point, button, buttons: (
                ConversationMapScreen._send_hand_pointer_event(
                    screen, target, event_type, point, button, buttons
                )
            ),
            _send_hand_mouse_event=lambda target, event_type, point, button, buttons: (
                _send_hand_mouse_event(target, event_type, point, button, buttons)
            ),
            canvas=Mock(),
        )
        metrics = (0, 0, 0.1, 0.5, False, 0, 0, 0)

        ConversationMapScreen._update_hand_interaction(
            screen, "single", metrics, position, True
        )
        self.assertEqual(pressed, [])
        ConversationMapScreen._update_hand_interaction(
            screen, "single", metrics, position + QPoint(20, 0), True
        )

        self.assertEqual(pressed, [True])
        self.assertTrue(button.isDown())
        button.close()

    def test_double_pinch_can_send_a_click_outside_aiko(self):
        screen = SimpleNamespace(
            _send_hand_pointer_event=lambda target, event_type, point, button, buttons: (
                ConversationMapScreen._send_hand_pointer_event(
                    screen, target, event_type, point, button, buttons
                )
            )
        )
        position = QPoint(200, 150)

        with patch("frontend.GUI._send_global_hand_mouse_event") as send_global:
            ConversationMapScreen._send_hand_pointer_click(
                screen, None, position
            )

        send_global.assert_has_calls([
            call(QEvent.MouseButtonPress, position),
            call(QEvent.MouseButtonRelease, position),
        ])

    def test_quick_pinch_mouse_events_activate_aiko_button(self):
        button = QPushButton("Test")
        button.resize(120, 40)
        button.show()
        self.app.processEvents()
        clicked = []
        button.clicked.connect(lambda: clicked.append(True))
        position = button.rect().center()

        _send_hand_mouse_event(
            button, QEvent.MouseButtonPress, position,
            Qt.LeftButton, Qt.LeftButton,
        )
        _send_hand_mouse_event(
            button, QEvent.MouseButtonRelease, position,
            Qt.LeftButton, Qt.NoButton,
        )

        self.assertEqual(clicked, [True])
        button.close()


if __name__ == "__main__":
    unittest.main()
