import unittest
from unittest.mock import patch

from backend.IntentRouting import (
    intent_from_decision,
    parse_generation_request,
    parse_image_generation_request,
    parse_music_request,
)
from backend.Automation import GoogleSearch
from backend.Music import (
    PlaySpotifyLikedSongs,
    SPOTIFY_LIKED_SONGS_URL,
)
from backend.Workspace import parse_workspace_command


class ImageGenerationRoutingTests(unittest.TestCase):
    def test_explicit_image_and_picture_phrases_route_to_image_generation(self):
        requests = {
            "image of a red fox": "a red fox",
            "picture of a lighthouse": "a lighthouse",
            "make an image of a glass house": "a glass house",
            "make a new picture of a robot": "a robot",
            "show me a picture of a blue car": "a blue car",
            "show me a cat": "a cat",
            "generate a picture of a mountain": "a mountain",
            "I want a picture of a dragon": "a dragon",
            "I'd like to see an image of a cabin": "a cabin",
            "Can I see a photo of a red fox": "a red fox",
            "give me an illustration of a robot": "a robot",
            "draw a picture of a castle": "a castle",
        }
        for request, expected_prompt in requests.items():
            with self.subTest(request=request):
                self.assertEqual(
                    parse_image_generation_request(request),
                    expected_prompt,
                )

    def test_image_generation_command_without_a_subject_requests_one(self):
        for request in ("image", "picture", "show me", "make an image"):
            with self.subTest(request=request):
                self.assertEqual(
                    parse_image_generation_request(request),
                    "",
                )

    def test_non_image_generation_requests_are_not_claimed(self):
        for request in (
            "generate a chair",
            "create a 3D model of a gear",
            "play some toons",
            "what is image generation?",
            "what is a photograph?",
            "what is on my screen?",
        ):
            with self.subTest(request=request):
                self.assertIsNone(parse_image_generation_request(request))


class ItemGenerationRoutingTests(unittest.TestCase):
    def test_decision_dispatch_preserves_multiword_intents(self):
        requests = {
            "generate image(a fox)": "generate image",
            "choose image 2": "choose",
            "workspace create chair": "workspace",
            "google search weather": "google",
        }
        for decision, expected_intent in requests.items():
            with self.subTest(decision=decision):
                self.assertEqual(intent_from_decision(decision), expected_intent)

    def test_requested_item_generation_phrases_route_to_design_creation(self):
        requests = {
            "generate a chair": ("create", "chair"),
            "create a new lamp": ("create", "lamp"),
            "make a wooden stool": ("create", "wooden stool"),
            "make a new item": ("create", ""),
            "make blueprint of a small house": (
                "create",
                "blueprint of a small house",
            ),
            "blueprint of a bridge": ("create", "blueprint of a bridge"),
            "generate": ("create", ""),
            "create": ("create", ""),
            "I want to work on a new design": ("create", ""),
            "I want to work on a new design of a chair": (
                "create",
                "a chair",
            ),
            "I wanna create a chair": ("create", "chair"),
            "I need a design for a desk lamp": (
                "create",
                "a desk lamp",
            ),
            "new project": ("create", ""),
            "new 3D design": ("create", ""),
            "need a design": ("create", ""),
            "go back to project bridge": ("open_project", "bridge"),
            "going back to a project": ("open_project", ""),
            "what am I working on": ("describe", ""),
            "tell me what I'm working on": ("describe", ""),
            "what files are in my workspace": ("describe", ""),
        }
        for request, expected in requests.items():
            with self.subTest(request=request):
                self.assertEqual(parse_workspace_command(request), expected)

    def test_explicit_generation_routes_have_distinct_intents(self):
        requests = {
            "image of a fox": "generate image(a fox)",
            "make an image of a fox": "generate image(a fox)",
            "I want a picture of a dragon": "generate image(a dragon)",
            "Can I see a photo of a red fox": "generate image(a red fox)",
            "generate a chair": "workspace create chair",
            "make a new item": "workspace create",
            "make blueprint of a house": "workspace create blueprint of a house",
            "blueprint of a bridge": "workspace create blueprint of a bridge",
        }
        for request, expected in requests.items():
            with self.subTest(request=request):
                self.assertEqual(parse_generation_request(request), expected)

    def test_image_nouns_are_not_misrouted_as_3d_items(self):
        for request in (
            "make an image of a cat",
            "make a new picture of a boat",
            "image of a city",
        ):
            with self.subTest(request=request):
                self.assertIsNone(parse_workspace_command(request))


class MusicRoutingTests(unittest.TestCase):
    def test_music_aliases_route_to_playback(self):
        requests = {
            "drop my needle": "play some tunes",
            "play some toons": "play some tunes",
            "serenade me": "play romantic songs",
            "play my liked songs from Spotify": "spotify liked songs",
            "open liked songs on Spotify": "spotify liked songs",
        }
        for request, expected in requests.items():
            with self.subTest(request=request):
                self.assertEqual(parse_music_request(request), expected)

    def test_spotify_liked_songs_opens_spotify_collection(self):
        with patch("backend.Music.webbrowser.open", return_value=True) as open_url:
            self.assertTrue(PlaySpotifyLikedSongs())
        open_url.assert_called_once_with(SPOTIFY_LIKED_SONGS_URL)

    def test_spotify_open_failures_are_reported(self):
        with patch("backend.Music.webbrowser.open", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Could not open Spotify"):
                PlaySpotifyLikedSongs()


class GoogleSearchTests(unittest.TestCase):
    def test_empty_google_search_opens_homepage_instead_of_searching_empty_text(self):
        with patch("backend.Automation.webbrowser.open", return_value=True) as open_url:
            self.assertTrue(GoogleSearch(""))

        open_url.assert_called_once_with("https://www.google.com")


if __name__ == "__main__":
    unittest.main()
