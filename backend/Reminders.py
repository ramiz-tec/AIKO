import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMINDERS_PATH = PROJECT_ROOT / "Data" / "Reminders.json"
_STORE_LOCK = threading.Lock()

_WEEKDAYS = {
    name.lower(): index
    for index, name in enumerate(
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    )
}


def _read_reminders() -> list[dict]:
    if not REMINDERS_PATH.exists():
        return []
    try:
        with REMINDERS_PATH.open("r", encoding="utf-8") as file:
            reminders = json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{REMINDERS_PATH.name} contains invalid JSON.") from error
    if not isinstance(reminders, list) or any(not isinstance(item, dict) for item in reminders):
        raise RuntimeError(f"{REMINDERS_PATH.name} must contain a JSON list of reminders.")
    return reminders


def _write_reminders(reminders: list[dict]) -> None:
    REMINDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = REMINDERS_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(reminders, file, ensure_ascii=False, indent=2)
    os.replace(temporary_path, REMINDERS_PATH)


def _extract_due_time(text: str, now: datetime) -> tuple[datetime, str]:
    duration = re.search(
        r"\bin\s+(?P<count>\d+)\s*(?P<unit>minutes?|mins?|hours?|hrs?|days?)\b",
        text,
        re.IGNORECASE,
    )
    if duration:
        count = int(duration.group("count"))
        unit = duration.group("unit").lower()
        delta = timedelta(
            minutes=count if unit.startswith(("minute", "min")) else 0,
            hours=count if unit.startswith(("hour", "hr")) else 0,
            days=count if unit.startswith("day") else 0,
        )
        return now + delta, text[:duration.start()] + " " + text[duration.end():]

    time_match = re.search(
        r"(?<!\w)(?:at\s+)?"
        r"(?P<hour>2[0-3]|[01]?\d)(?::(?P<minute>[0-5]\d))?"
        r"\s*(?P<meridiem>a\.?m\.?|p\.?m\.?)?"
        r"(?:\s+(?:in\s+the\s+)?(?:this\s+)?"
        r"(?P<daypart>morning|afternoon|evening|tonight))?"
        r"(?!\w)",
        text,
        re.IGNORECASE,
    )
    if time_match and not (
        time_match.group("minute")
        or time_match.group("meridiem")
        or time_match.group("daypart")
        or re.match(r"\s*at\b", text[time_match.start():], re.IGNORECASE)
    ):
        time_match = None

    date_match = re.search(
        r"\b(?P<date>today|tomorrow|tonight|"
        r"(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        text,
        re.IGNORECASE,
    )
    external_daypart = re.search(
        r"\b(?:(?:in\s+the|this)\s+)?"
        r"(?P<daypart>morning|afternoon|evening|tonight)\b",
        text,
        re.IGNORECASE,
    )
    if not time_match:
        raise ValueError(
            "What date and time should I remind you? For example, "
            "'remind me to call Sam tomorrow at 9 AM'."
        )

    hour = int(time_match.group("hour"))
    minute = int(time_match.group("minute") or 0)
    meridiem = (time_match.group("meridiem") or "").lower().replace(".", "")
    daypart = (time_match.group("daypart") or "").lower()
    if not daypart and external_daypart:
        daypart = external_daypart.group("daypart").lower()
    if meridiem:
        if not 1 <= hour <= 12:
            raise ValueError("For AM or PM times, use an hour from 1 to 12.")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    elif daypart in {"afternoon", "evening", "tonight"} and hour < 12:
        hour += 12
    elif daypart == "morning" and hour == 12:
        hour = 0

    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    date_text = date_match.group("date").lower() if date_match else ""
    if date_text == "tomorrow":
        due += timedelta(days=1)
    elif date_text in {"today", "tonight"}:
        if date_text == "tonight" and not meridiem and hour < 12:
            due = due.replace(hour=hour + 12)
        if due <= now:
            raise ValueError("That time has already passed. Please choose a future time.")
    elif date_text:
        weekday = date_text.removeprefix("next ").lower()
        days_ahead = (_WEEKDAYS[weekday] - now.weekday()) % 7
        if days_ahead == 0 or date_text.startswith("next "):
            days_ahead = days_ahead or 7
            if date_text.startswith("next "):
                days_ahead = days_ahead if days_ahead > 0 else 7
        due += timedelta(days=days_ahead)
    elif due <= now:
        due += timedelta(days=1)

    spans = [time_match.span()]
    if date_match:
        spans.append(date_match.span())
    if external_daypart and external_daypart.span() != time_match.span():
        spans.append(external_daypart.span())
    remainder = text
    for start, end in sorted(spans, reverse=True):
        remainder = remainder[:start] + " " + remainder[end:]
    return due, remainder


def ParseReminderRequest(query: str, now: datetime | None = None) -> tuple[str, str]:
    """Return a reminder title and local ISO due time from a voice request."""
    if not query or not query.strip():
        raise ValueError("Please tell me what to remind you about and when.")
    current_time = now or datetime.now().astimezone()
    if current_time.tzinfo is None:
        current_time = current_time.astimezone()
    due_at, remainder = _extract_due_time(query.strip(), current_time)
    title = re.sub(
        r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?"
        r"(?:(?:i|we)\s+(?:want|need)\s+you\s+to\s+)?",
        "",
        remainder,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"^(?:remind(?:\s+me)?\b|reminder(?:\s+for)?\b|"
        r"set\s+(?:a\s+)?reminder(?:\s+for\s+me)?\b|"
        r"(?:save|add)\s+(?:(?:a|an|the|this)\s+)?(?:reminder|event)|"
        r"schedule(?:\s+(?:a|an|the)\s+)?(?:reminder|event)?|"
        r"plan\s+for(?:\s+me)?(?:\s+to)?)\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"^(?:(?:the|a|an|to|about|that|for)\s+)+",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"\s+(?:to\s+)?(?:open|opens|opening)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = title.strip(" \t\r\n.,!?")
    title = re.sub(r"\s+for\s+(?:me|us)\s*$", "", title, flags=re.IGNORECASE)
    title = title.strip(" \t\r\n.,!?")
    if not title:
        raise ValueError("What should I remind you about?")
    return title, due_at.isoformat(timespec="seconds")


def SaveReminder(title: str, due_at: str) -> dict:
    """Persist a single reminder or event and return its saved record."""
    if not title or not title.strip():
        raise ValueError("A reminder needs a description.")
    due = datetime.fromisoformat(due_at)
    reminder = {
        "id": secrets.token_hex(8),
        "title": title.strip(),
        "due_at": due.isoformat(timespec="seconds"),
        "notified": False,
    }
    with _STORE_LOCK:
        reminders = _read_reminders()
        reminders.append(reminder)
        _write_reminders(reminders)
    return reminder


def ListReminders() -> list[dict]:
    """Return saved reminders, ordered by due time."""
    with _STORE_LOCK:
        reminders = _read_reminders()
    return sorted(reminders, key=lambda item: item.get("due_at", ""))


def TakeDueReminders(now: datetime | None = None) -> list[dict]:
    """Mark and return reminders due now, including ones missed while AIKO was closed."""
    current_time = now or datetime.now().astimezone()
    due_reminders = []
    with _STORE_LOCK:
        reminders = _read_reminders()
        changed = False
        for reminder in reminders:
            if reminder.get("notified"):
                continue
            try:
                due_at = datetime.fromisoformat(reminder["due_at"])
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("A saved reminder has an invalid due time.") from error
            if due_at <= current_time:
                due_reminders.append(reminder)
                reminder["notified"] = True
                changed = True
        if changed:
            _write_reminders(reminders)
    return due_reminders
