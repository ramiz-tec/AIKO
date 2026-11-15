import base64
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from backend.DesktopControl import (
    _analyze_image,
    _capture_screen,
    describe_generated_image,
    describe_screen,
    parse_desktop_request,
)


class ParseDesktopRequestTests(unittest.TestCase):
    def test_screen_questions_are_on_demand_commands(self):
        for request in (
            "What's on my screen?",
            "What is on screen?",
            "What am I looking at?",
            "Please describe the screen.",
            "Can you tell me what is on my screen?",
            "What was on my screen?",
        ):
            with self.subTest(request=request):
                self.assertEqual(parse_desktop_request(request), ("screen", ""))

    def test_selected_image_questions_are_explicit_local_vision_requests(self):
        for request in (
            "Tell me about the image he generated.",
            "Describe the selected image",
            "What's in that picture?",
            "What does this image look like?",
        ):
            with self.subTest(request=request):
                self.assertEqual(parse_desktop_request(request), ("image", ""))

    def test_only_direct_tab_commands_are_recognized(self):
        self.assertEqual(parse_desktop_request("open a new tab"), ("new_tab", ""))
        self.assertEqual(parse_desktop_request("Could you open another browser tab?"), ("new_tab", ""))
        self.assertEqual(parse_desktop_request("close this tab"), ("close_tab", ""))
        self.assertIsNone(parse_desktop_request("You should open a new tab"))

    def test_click_targets_are_exact_control_labels(self):
        self.assertEqual(parse_desktop_request("click the Sign in button"), ("click", "Sign in"))
        self.assertEqual(parse_desktop_request('select the "Continue" option'), ("click", "Continue"))
        self.assertEqual(parse_desktop_request("Could you click on the sign in link?"), ("click", "sign in"))

    def test_non_commands_are_not_treated_as_desktop_actions(self):
        self.assertIsNone(parse_desktop_request("What can you do on a computer?"))
        self.assertIsNone(parse_desktop_request("I think you should click Sign in"))

    def test_high_impact_controls_are_never_clicked(self):
        from backend.DesktopControl import click_control

        for label in ("Submit", "Delete account", "Place order", "Send"):
            with self.subTest(label=label):
                with self.assertRaisesRegex(RuntimeError, "high-impact"):
                    click_control(label)

    @patch("backend.DesktopControl.requests.Session")
    @patch("backend.DesktopControl._capture_screen", return_value="in-memory-image")
    def test_screen_image_is_sent_only_to_local_ollama(self, _capture, session_class):
        session = session_class.return_value.__enter__.return_value
        session.post.return_value.json.return_value = {
            "message": {"content": "A browser window is open."}
        }
        session.post.return_value.is_redirect = False

        self.assertEqual(describe_screen(), "A browser window is open.")
        self.assertFalse(session.trust_env)
        session.post.assert_called_once()
        self.assertEqual(
            session.post.call_args.args[0],
            "http://127.0.0.1:11434/api/chat",
        )
        self.assertEqual(
            session.post.call_args.kwargs["json"]["messages"][0]["images"],
            ["in-memory-image"],
        )
        self.assertFalse(session.post.call_args.kwargs["allow_redirects"])
        self.assertEqual(session.post.call_args.kwargs["timeout"], (3, 90))
        self.assertEqual(
            session.post.call_args.kwargs["json"]["options"]["num_predict"],
            96,
        )

    @patch("backend.DesktopControl.ImageGrab.grab")
    @patch("backend.DesktopControl._temporarily_hide_aiko_windows")
    def test_screen_capture_is_one_primary_monitor_image(
        self,
        hide_aiko,
        grab,
    ):
        grab.return_value = Image.new("RGB", (1920, 1080), "white")
        encoded = _capture_screen()

        grab.assert_called_once_with()
        self.assertGreater(len(encoded), 0)
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as captured:
            self.assertLessEqual(max(captured.size), 512)

    @patch("backend.DesktopControl.requests.Session")
    def test_image_analysis_uses_one_local_request(self, session_class):
        session = session_class.return_value.__enter__.return_value
        session.post.return_value.json.return_value = {
            "message": {"content": "The image shows a red square."}
        }
        session.post.return_value.is_redirect = False

        self.assertEqual(
            _analyze_image("selected-image", "Describe the image."),
            "The image shows a red square.",
        )
        session.post.assert_called_once()
        request = session.post.call_args.kwargs
        self.assertFalse(session.trust_env)
        self.assertFalse(request["allow_redirects"])
        self.assertEqual(
            request["json"]["messages"][0]["images"],
            ["selected-image"],
        )

    @patch("backend.DesktopControl._analyze_image", return_value="A red square.")
    def test_selected_generated_image_uses_its_prompt_as_visual_context(self, analyze):
        with TemporaryDirectory() as directory:
            image_directory = Path(directory)
            image_path = image_directory / "generated.png"
            Image.new("RGB", (20, 20), "red").save(image_path)
            with patch("backend.DesktopControl.OUTPUT_DIR", image_directory):
                result = describe_generated_image(
                    str(image_path),
                    "a red square on a gray background",
                )

        self.assertEqual(result, "A red square.")
        prompt = analyze.call_args.args[1]
        self.assertIn("a red square on a gray background", prompt)
        self.assertIn("What objects and colors are visible", prompt)

    def test_generated_image_description_rejects_files_outside_gallery(self):
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "not-generated.png"
            Image.new("RGB", (20, 20), "red").save(image_path)
            with self.assertRaisesRegex(ValueError, "Only a selected AIKO-generated"):
                describe_generated_image(str(image_path))


if __name__ == "__main__":
    unittest.main()
