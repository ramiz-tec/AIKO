import re
from datetime import datetime


_SPEECH_STOP_PHRASES = {
    "stop",
    "wait",
    "shut up",
    "hold on",
    "pause",
}


def IsSpeechStopCommand(query: str) -> bool:
    normalized = re.sub(r"[\W_]+", " ", query.casefold()).strip()
    return normalized in _SPEECH_STOP_PHRASES


def TimeOfDayGreeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now().astimezone()).hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"
