import re

from backend.Workspace import parse_workspace_command


_TRAILING_PUNCTUATION = " \t\r\n.,!?"
_IMAGE_WORDS = (
    r"(?:images?|pictures?|photos?|photographs?|illustrations?|artwork|drawings?)"
)


def parse_image_generation_request(query: str) -> str | None:
    normalized = query.strip().strip(_TRAILING_PUNCTUATION)
    normalized = re.sub(
        r"^(?:please\s+|can you\s+|could you\s+|would you\s+)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    show_request = re.match(
        r"^show\s+me\b\s*(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if show_request:
        prompt = show_request.group(1).strip(_TRAILING_PUNCTUATION)
        if re.match(r"^(?:what(?:'s| is)\s+)?on\s+(?:my\s+)?screen\b", prompt, re.I):
            return None
        prompt = re.sub(
            rf"^(?:(?:an?|the|some)\s+)?{_IMAGE_WORDS}\b"
            r"(?:\s+(?:of|showing|about))?\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        )
        prompt = re.sub(r"^(?:of|showing|about)\s+", "", prompt, flags=re.I)
        return prompt.strip(_TRAILING_PUNCTUATION)

    framed_image_request = re.match(
        rf"^(?:(?:i|we)\s+(?:want|need)\s+"
        rf"(?:to\s+(?:see|view|get|have)\s+|(?:an?|some|the)\s+)|"
        rf"(?:i|we)(?:\s+would|\s*['’]d)\s+like\s+"
        rf"(?:to\s+(?:see|view|get|have)\s+|(?:an?|some|the)\s+)|"
        rf"(?:can|could|would)\s+i\s+(?:see|get|have)\s+|"
        rf"(?:give|send)\s+(?:me|us)\s+|show\s+(?:me|us)\s+)"
        rf"(?:(?:an?|some|the)\s+)?{_IMAGE_WORDS}\b"
        r"(?:\s+(?:of|showing|about|depicting|with))?\s*(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if framed_image_request:
        return framed_image_request.group(1).strip(_TRAILING_PUNCTUATION)

    image_request = re.match(
        rf"^(?:(?:generate|make|create|draw|paint|render|illustrate)\s+"
        rf"(?:me\s+)?(?:(?:an?|new)\s+){{0,2}}|"
        r"(?:(?:an?|the)\s+)?)"
        rf"{_IMAGE_WORDS}\b"
        r"(?:\s+(?:of|about|showing|depicting|with))?\s*(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if not image_request:
        return None
    return image_request.group(1).strip(_TRAILING_PUNCTUATION)


def parse_music_request(query: str) -> str | None:
    normalized = query.strip().strip(_TRAILING_PUNCTUATION)
    spotify_liked_songs = re.fullmatch(
        r"(?:(?:please|can you|could you|would you)\s+)?"
        r"(?:(?:play|open|put on)\s+)?"
        r"(?:my\s+)?liked\s+songs"
        r"(?:\s+(?:on|from|in))?\s+spotify",
        normalized,
        re.IGNORECASE,
    )
    if spotify_liked_songs:
        return "spotify liked songs"

    if re.fullmatch(
        r"(?:(?:please|can you|could you|would you)\s+)?"
        r"drop\s+my\s+needle",
        normalized,
        re.IGNORECASE,
    ):
        return "play some tunes"

    if re.fullmatch(
        r"(?:(?:please|can you|could you|would you)\s+)?"
        r"play\s+(?:me\s+)?some\s+toons",
        normalized,
        re.IGNORECASE,
    ):
        return "play some tunes"

    if re.fullmatch(
        r"(?:(?:please|can you|could you|would you)\s+)?"
        r"serenade\s+me",
        normalized,
        re.IGNORECASE,
    ):
        return "play romantic songs"
    return None


def parse_generation_request(query: str) -> str | None:
    image_prompt = parse_image_generation_request(query)
    if image_prompt is not None:
        return f"generate image({image_prompt})"

    workspace_request = parse_workspace_command(query)
    if workspace_request is not None and workspace_request[0] == "create":
        return f"workspace create {workspace_request[1]}".rstrip()
    return None


def intent_from_decision(decision: str) -> str:
    intent_text = decision.partition("(")[0].strip().lower()
    if intent_text.startswith("generate image"):
        return "generate image"
    if intent_text.startswith("choose image"):
        return "choose"
    return intent_text.split(" ", 1)[0]
