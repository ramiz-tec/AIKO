import base64
import ctypes
import io
import os
import re
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

import requests
from dotenv import dotenv_values
from PIL import Image, ImageGrab

from backend.ImageGeneration import OUTPUT_DIR


_LOCAL_VISION_URL = "http://127.0.0.1:11434/api/chat"
_LOCAL_VISION_MODEL = (
    os.environ.get("AIKO_LOCAL_VISION_MODEL")
    or dotenv_values(Path(__file__).resolve().parents[1] / ".env").get(
        "AIKO_LOCAL_VISION_MODEL"
    )
    or "moondream"
)
_CONTROL_TYPES = {
    "Button",
    "CheckBox",
    "Hyperlink",
    "MenuItem",
    "RadioButton",
    "TabItem",
}
_HIGH_IMPACT_CONTROL = re.compile(
    r"\b(?:send|submit|delete|remove|buy|purchase|pay|transfer|confirm|"
    r"post|publish|unsubscribe|place order)\b",
    re.IGNORECASE,
)
_IMAGE_DESCRIPTION_REQUEST = re.compile(
    r"(?:tell me (?:about|what(?:'s| is) in) |"
    r"what(?:'s| is) in |describe |explain |"
    r"what does (?:the |this |that |my )?)"
    r"(?:(?:the )?(?:this|that|my|last|selected) |"
    r"(?:the|this|that|my|last|selected) )?"
    r"(?:image|picture|photo|artwork)"
    r"(?: (?:you|i|he|she|we|aiko) (?:just )?(?:generated|made|created))?"
    r"(?: look like)?",
    re.IGNORECASE,
)


def parse_desktop_request(query: str) -> tuple[str, str] | None:
    """Recognize only direct, narrowly scoped desktop commands."""
    normalized = query.strip().strip(" \t\r\n.,!?")
    normalized = re.sub(
        r"^(?:please|can you|could you|would you|will you)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    lowered = normalized.casefold()
    if re.fullmatch(
        r"(?:(?:tell me )?what(?:'s| is| was) on (?:my )?screen|what am i looking at|"
        r"describe (?:(?:my|the) )?screen|what can you see on (?:my )?screen)",
        lowered,
    ):
        return "screen", ""
    if _IMAGE_DESCRIPTION_REQUEST.fullmatch(lowered):
        return "image", ""
    if re.fullmatch(
        r"(?:(?:open|create|start) )?(?:a )?(?:(?:new|another) )?"
        r"(?:browser )?tab",
        lowered,
    ):
        return "new_tab", ""
    if re.fullmatch(
        r"(?:close|close this|close the current|close current) "
        r"(?:browser )?tab",
        lowered,
    ):
        return "close_tab", ""

    click_request = re.fullmatch(
        r"(?:click|press|select) (?:on )?(?:the )?(?:option )?(.+)",
        normalized,
        re.IGNORECASE,
    )
    if click_request:
        control_name = click_request.group(1).strip().strip("\"'“”‘’")
        control_name = re.sub(
            r"\s+(?:button|link|option|tab|control)(?: on (?:the )?screen)?$",
            "",
            control_name,
            flags=re.IGNORECASE,
        ).strip().strip("\"'“”‘’")
        if control_name:
            return "click", control_name
    return None


def _capture_screen() -> str:
    if os.name != "nt":
        raise RuntimeError("On-demand screen capture is available only on Windows.")

    try:
        with _temporarily_hide_aiko_windows():
            image = ImageGrab.grab()
    except OSError as error:
        raise RuntimeError(f"Could not capture the desktop: {error}") from error

    image.thumbnail((512, 512))
    encoded_image = io.BytesIO()
    image.convert("RGB").save(encoded_image, format="JPEG", quality=65)
    return base64.b64encode(encoded_image.getvalue()).decode("ascii")


@contextmanager
def _temporarily_hide_aiko_windows():
    if os.name != "nt":
        raise RuntimeError("Desktop access is available only on Windows.")

    hidden_windows: list[int] = []
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND

    def hide_aiko_windows(hwnd: int, _unused: int) -> bool:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == os.getpid() and user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 0)
            hidden_windows.append(hwnd)
        return True

    callback = callback_type(hide_aiko_windows)
    try:
        if not user32.EnumWindows(callback, 0):
            raise RuntimeError("Windows could not enumerate AIKO's screen windows.")
        foreground_handle = user32.GetForegroundWindow()
        yield int(foreground_handle or 0)
    finally:
        for hwnd in hidden_windows:
            user32.ShowWindow(hwnd, 5)


def _analyze_image(image_data: str, prompt: str) -> str:
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                _LOCAL_VISION_URL,
                json={
                    "model": _LOCAL_VISION_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_data],
                        }
                    ],
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"temperature": 0.1, "num_predict": 96},
                },
                timeout=(3, 90),
                allow_redirects=False,
            )
    except requests.ConnectionError as error:
        raise RuntimeError(
            "The local vision model is unavailable. Install and start Ollama, "
            "then run `ollama pull moondream`."
        ) from error
    except requests.Timeout as error:
        raise RuntimeError("The local vision request timed out after 90 seconds.") from error

    if response.is_redirect:
        raise RuntimeError("The local vision endpoint redirected the screenshot request.")

    try:
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as error:
        raise RuntimeError(
            f"The local vision model returned an invalid response: {error}"
        ) from error

    if not isinstance(result, dict):
        raise RuntimeError("The local vision model returned an invalid response.")
    message = result.get("message")
    description = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(description, str) or not description.strip():
        raise RuntimeError("The local vision model returned an empty description.")
    return description.strip()


def describe_screen() -> str:
    """Capture one resized screenshot and analyze it using local Ollama."""
    screenshot = _capture_screen()
    return _analyze_image(
        screenshot,
        "What is visible on this computer screen? Answer in one or two concise "
        "sentences. Mention only the main things you can see.",
    )


def describe_generated_image(image_path: str, image_prompt: str = "") -> str:
    """Analyze the selected generated image without uploading or retaining it."""
    selected_path = Path(image_path).resolve()
    image_directory = OUTPUT_DIR.resolve()
    if not selected_path.is_relative_to(image_directory):
        raise ValueError("Only a selected AIKO-generated image can be described.")
    if not selected_path.is_file():
        raise RuntimeError("The selected generated image is no longer available.")

    try:
        with Image.open(selected_path) as image:
            image.thumbnail((768, 768))
            encoded_image = io.BytesIO()
            image.convert("RGB").save(encoded_image, format="JPEG", quality=72)
    except OSError as error:
        raise RuntimeError(f"Could not read the selected image: {error}") from error

    image_data = base64.b64encode(encoded_image.getvalue()).decode("ascii")
    prompt_context = ""
    if image_prompt:
        prompt_context = (
            "The user's original generation prompt was: "
            f"{image_prompt[:500]}\n"
        )
    return _analyze_image(
        image_data,
        f"{prompt_context}What objects and colors are visible in this image? "
        "Describe the picture briefly, based on the image itself.",
    )


def _target_window():
    if os.name != "nt":
        raise RuntimeError("Desktop controls are available only on Windows.")

    from pywinauto import Desktop

    with _temporarily_hide_aiko_windows() as foreground_handle:
        if not foreground_handle:
            raise RuntimeError("I couldn't identify the app behind AIKO.")
        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(
            foreground_handle,
            ctypes.byref(process_id),
        )
        if process_id.value == os.getpid():
            raise RuntimeError("I couldn't identify another app behind AIKO.")

    window = Desktop(backend="uia").window(handle=foreground_handle)
    if not window.exists():
        raise RuntimeError("The app behind AIKO closed before I could control it.")
    return window


def _is_browser_window(window) -> bool:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process_handle = kernel32.OpenProcess(
        0x1000,
        False,
        window.process_id(),
    )
    if not process_handle:
        return False

    try:
        executable_path = ctypes.create_unicode_buffer(32768)
        path_length = wintypes.DWORD(len(executable_path))
        if not kernel32.QueryFullProcessImageNameW(
            process_handle,
            0,
            executable_path,
            ctypes.byref(path_length),
        ):
            return False
        executable_name = os.path.basename(executable_path.value).casefold()
        return executable_name in {
            "brave.exe",
            "chrome.exe",
            "firefox.exe",
            "msedge.exe",
            "opera.exe",
            "vivaldi.exe",
        }
    finally:
        kernel32.CloseHandle(process_handle)


def _target_browser_window():
    window = _target_window()
    if not _is_browser_window(window):
        raise RuntimeError(
            "The app behind AIKO is not a supported browser. Bring your browser "
            "to the front, then try again."
        )
    return window


def _visible_control_matches(window, control_name: str):
    matches = []
    for control in window.descendants():
        element = control.element_info
        if (
            isinstance(element.name, str)
            and element.name.strip().casefold() == control_name.casefold()
            and element.control_type in _CONTROL_TYPES
            and control.is_visible()
            and control.is_enabled()
        ):
            matches.append(control)
    return matches


def open_new_tab() -> str:
    window = _target_browser_window()
    window.set_focus()
    from pywinauto.keyboard import send_keys

    send_keys("^t")
    return "Opened a new tab in the current app."


def close_current_tab() -> str:
    window = _target_browser_window()
    window.set_focus()
    from pywinauto.keyboard import send_keys

    send_keys("^w")
    return "Closed the current tab."


def click_control(control_name: str) -> str:
    if _HIGH_IMPACT_CONTROL.search(control_name):
        raise RuntimeError(
            "I won't activate a send, submit, purchase, deletion, or other "
            "high-impact control by voice. Please review and click it yourself."
        )

    window = _target_window()
    matches = _visible_control_matches(window, control_name)
    if not matches:
        raise RuntimeError(
            f"I couldn't find a visible, enabled button, link, option, or tab "
            f"named “{control_name}” in {window.window_text()}."
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"I found more than one control named “{control_name}” in "
            f"{window.window_text()}. Please be more specific."
        )

    window.set_focus()
    matches[0].click_input()
    return f"Clicked “{control_name}” in {window.window_text()}."
