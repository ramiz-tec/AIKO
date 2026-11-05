import hmac
import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from groq import Groq
from pydantic import BaseModel, Field
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from backend import ImageGeneration
from backend.ImageGeneration import GenerateImage
from backend.Reminders import ListReminders, SaveReminder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_dotenv_values = dotenv_values(PROJECT_ROOT / ".env")
_API_KEY_HEADER = APIKeyHeader(name="X-AIKO-API-Key", auto_error=False)
_logger = logging.getLogger(__name__)
_groq_api_key = (
    os.environ.get("GroqApiKey")
    or os.environ.get("GROQ_API_KEY")
    or _dotenv_values.get("GroqApiKey")
)
_groq_model = (
    os.environ.get("GroqModel")
    or os.environ.get("GROQ_MODEL")
    or _dotenv_values.get("GroqModel")
    or "openai/gpt-oss-120b"
)
_assistant_name = (
    os.environ.get("AssistantName")
    or _dotenv_values.get("AssistantName")
    or "AIKO"
)
_username = os.environ.get("Username") or _dotenv_values.get("Username") or "User"
_groq_client = Groq(api_key=_groq_api_key) if _groq_api_key else None
_chat_history: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
_chat_lock = threading.Lock()
_chat_system_message = (
    f"You are {_assistant_name}, a helpful voice assistant for {_username}. "
    "Be friendly, concise, and direct. Do not claim to have performed actions "
    "that were not done."
)

app = FastAPI(
    title="AIKO API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(default="iphone", min_length=1, max_length=64)


class ChatResponse(BaseModel):
    reply: str


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)


class ImageResponse(BaseModel):
    prompt: str
    image_urls: list[str]


class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_at: datetime


class ReminderResponse(BaseModel):
    id: str
    title: str
    due_at: datetime
    notified: bool


def _configured_api_key() -> str | None:
    return os.environ.get("AIKO_API_TOKEN") or _dotenv_values.get("AIKO_API_TOKEN")


def require_api_key(
    supplied_key: str | None = Security(_API_KEY_HEADER),
) -> None:
    expected_key = _configured_api_key()
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="The API is not configured. Set AIKO_API_TOKEN on the server.",
        )
    if not supplied_key or not hmac.compare_digest(
        supplied_key.encode("utf-8"),
        expected_key.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _reminder_response(reminder: dict) -> ReminderResponse:
    return ReminderResponse(
        id=str(reminder["id"]),
        title=str(reminder["title"]),
        due_at=datetime.fromisoformat(reminder["due_at"]),
        notified=bool(reminder.get("notified", False)),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(request: ChatRequest) -> ChatResponse:
    if _groq_client is None:
        raise HTTPException(
            status_code=503,
            detail="The chat service is not configured. Set GroqApiKey on the server.",
        )
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="A chat message is required.")

    with _chat_lock:
        history = _chat_history.get(request.session_id)
        if history is None:
            if len(_chat_history) >= 100:
                _chat_history.popitem(last=False)
            history = []
            _chat_history[request.session_id] = history
        else:
            _chat_history.move_to_end(request.session_id)
        history.append({"role": "user", "content": message})
        history[:] = history[-20:]
        try:
            completion = _groq_client.chat.completions.create(
                model=_groq_model,
                messages=[
                    {"role": "system", "content": _chat_system_message},
                    *history,
                ],
                max_tokens=1024,
                temperature=0.7,
            )
        except Exception as error:
            history.pop()
            _logger.exception("AIKO chat provider request failed.")
            raise HTTPException(
                status_code=502,
                detail="The chat provider request failed. Check the server logs.",
            ) from error

        try:
            reply = (completion.choices[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError) as error:
            history.pop()
            _logger.exception("AIKO chat provider returned an invalid response.")
            raise HTTPException(
                status_code=502,
                detail="The chat provider returned an invalid response.",
            ) from error
        if not reply:
            history.pop()
            raise HTTPException(
                status_code=502,
                detail="The chat provider returned an empty response.",
            )
        history.append({"role": "assistant", "content": reply})
        return ChatResponse(reply=reply)


@app.post(
    "/v1/images",
    response_model=ImageResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_images(request: ImageRequest) -> ImageResponse:
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="An image description is required.")
    try:
        paths = GenerateImage(prompt)
    except (RuntimeError, ValueError) as error:
        _logger.exception("AIKO image generation failed.")
        raise HTTPException(status_code=502, detail=str(error)) from error
    image_urls = [
        f"/v1/images/{Path(path).name}"
        for path in paths
    ]
    return ImageResponse(prompt=prompt, image_urls=image_urls)


@app.get(
    "/v1/images/{filename}",
    dependencies=[Depends(require_api_key)],
)
def get_image(filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Image not found.")
    image_path = (ImageGeneration.OUTPUT_DIR / filename).resolve()
    if image_path.parent != ImageGeneration.OUTPUT_DIR.resolve() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(image_path)


@app.get(
    "/v1/reminders",
    response_model=list[ReminderResponse],
    dependencies=[Depends(require_api_key)],
)
def get_reminders() -> list[ReminderResponse]:
    return [_reminder_response(reminder) for reminder in ListReminders()]


@app.post(
    "/v1/reminders",
    response_model=ReminderResponse,
    dependencies=[Depends(require_api_key)],
)
def create_reminder(request: ReminderRequest) -> ReminderResponse:
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="A reminder title is required.")
    if request.due_at.tzinfo is None or request.due_at.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="due_at must include a timezone offset.",
        )
    try:
        reminder = SaveReminder(
            title,
            request.due_at.isoformat(timespec="seconds"),
        )
    except (OSError, RuntimeError, ValueError) as error:
        _logger.exception("Could not save an AIKO reminder.")
        raise HTTPException(
            status_code=500,
            detail="Could not save the reminder. Check the server logs.",
        ) from error
    return _reminder_response(reminder)


app.mount("/", StaticFiles(directory=PROJECT_ROOT / "web", html=True), name="web")
