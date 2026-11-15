import json
import threading
from pathlib import Path
from urllib.parse import urlencode

import requests
from xml.etree import ElementTree


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SEEN_NEWS_PATH = _PROJECT_ROOT / "Data" / "BreakingNewsSeen.json"
_FEED_URL = "https://news.google.com/rss/search"
_BREAKING_TERMS = (
    "earthquake",
    "tsunami",
    "hurricane",
    "tornado",
    "wildfire",
    "mass shooting",
    "attack",
    "invasion",
    "war",
    "explosion",
    "coup",
    "evacuation",
    "emergency declared",
    "ceasefire",
    "assassination",
    "terror",
)
_seen_lock = threading.Lock()


def FetchBreakingNews(timeout: float = 10.0) -> list[dict[str, str]]:
    """Fetch recent major-event headlines from the public Google News RSS feed."""
    params = urlencode({
        "q": "breaking news when:1h",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    try:
        response = requests.get(
            f"{_FEED_URL}?{params}",
            timeout=timeout,
            headers={"User-Agent": "AIKO/1.0 breaking-news-reader"},
        )
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach the breaking-news feed: {error}") from error
    response.raise_for_status()
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as error:
        raise RuntimeError("The breaking-news feed returned invalid XML.") from error

    stories = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        title_lower = title.casefold()
        if not title or not any(term in title_lower for term in _BREAKING_TERMS):
            continue
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link or title).strip()
        source = (item.findtext("source") or "Google News").strip()
        stories.append({
            "id": guid,
            "title": title,
            "source": source,
            "link": link,
        })
        if len(stories) >= 5:
            break
    return stories


def GetUnannouncedBreakingNews(
    stories: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return only unseen headlines and persist their IDs to prevent repeats."""
    with _seen_lock:
        if _SEEN_NEWS_PATH.exists():
            try:
                seen = json.loads(_SEEN_NEWS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(
                    f"Could not read {_SEEN_NEWS_PATH.name}: {error}"
                ) from error
            if not isinstance(seen, list) or any(
                not isinstance(item, str) for item in seen
            ):
                raise RuntimeError(
                    f"{_SEEN_NEWS_PATH.name} must contain a list of story IDs."
                )
        else:
            seen = []

        seen_ids = set(seen)
        new_stories = [
            story for story in stories
            if story.get("id") and story["id"] not in seen_ids
        ]
        if new_stories:
            seen.extend(story["id"] for story in new_stories)
            _SEEN_NEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SEEN_NEWS_PATH.write_text(
                json.dumps(seen[-200:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return new_stories
