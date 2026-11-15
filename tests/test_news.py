import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import News


class BreakingNewsTests(unittest.TestCase):
    def test_feed_keeps_only_recent_major_event_headlines(self):
        response = Mock()
        response.content = b"""<?xml version="1.0"?>
        <rss><channel>
          <item><title>Breaking: Major earthquake hits region</title>
            <link>https://news.example/quake</link><guid>quake-1</guid>
            <source>Example News</source></item>
          <item><title>Breaking: Local team wins championship</title>
            <link>https://news.example/sports</link><guid>sports-1</guid></item>
        </channel></rss>"""
        response.raise_for_status.return_value = None

        with patch.object(News.requests, "get", return_value=response):
            stories = News.FetchBreakingNews()

        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["id"], "quake-1")
        self.assertEqual(stories[0]["source"], "Example News")
        response.raise_for_status.assert_called_once()

    def test_unannounced_headlines_are_persistently_deduplicated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "seen.json"
            stories = [
                {"id": "quake-1", "title": "Earthquake", "source": "News", "link": ""}
            ]
            with patch.object(News, "_SEEN_NEWS_PATH", path):
                self.assertEqual(News.GetUnannouncedBreakingNews(stories), stories)
                self.assertEqual(News.GetUnannouncedBreakingNews(stories), [])
            self.assertEqual(path.read_text(encoding="utf-8"), '[\n  "quake-1"\n]')

    def test_invalid_rss_xml_reports_an_error(self):
        response = Mock(content=b"<rss><channel>")
        response.raise_for_status.return_value = None
        with patch.object(News.requests, "get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "invalid XML"):
                News.FetchBreakingNews()


if __name__ == "__main__":
    unittest.main()
