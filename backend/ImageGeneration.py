import base64
from concurrent.futures import ThreadPoolExecutor
import os
import re
import secrets
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_vars = dotenv_values(PROJECT_ROOT / ".env")
ACCOUNT_ID = (
    env_vars.get("Account_ID")
    or env_vars.get("CLOUDFLARE_ACCOUNT_ID")
    or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
)
API_TOKEN = (
    env_vars.get("API_Token")
    or env_vars.get("CLOUDFLARE_API_TOKEN")
    or os.environ.get("CLOUDFLARE_API_TOKEN")
)
IMAGE_MODEL = env_vars.get(
    "CLOUDFLARE_IMAGE_MODEL",
    "@cf/bytedance/stable-diffusion-xl-lightning",
)
OUTPUT_DIR = PROJECT_ROOT / "Data" / "Generated_Images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _image_bytes(response: requests.Response) -> bytes:
    content_type = response.headers.get("Content-Type", "").lower()
    if "application/json" in content_type:
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError("Cloudflare returned invalid JSON for an image.") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Cloudflare returned an invalid image response.")
        if not payload.get("success", True):
            errors = payload.get("errors", [])
            messages = [
                str(item.get("message", ""))
                for item in errors
                if isinstance(item, dict) and item.get("message")
            ]
            raise RuntimeError(
                "; ".join(messages) or "Cloudflare reported an image-generation error."
            )
        result = payload.get("result")
        encoded_image = result.get("image") if isinstance(result, dict) else None
        if not encoded_image:
            raise RuntimeError("Cloudflare's response did not contain generated image data.")
        try:
            image_data = base64.b64decode(encoded_image, validate=True)
        except (ValueError, TypeError) as error:
            raise RuntimeError("Cloudflare returned invalid base64 image data.") from error
    else:
        image_data = response.content

    if not image_data:
        raise RuntimeError("Cloudflare returned an empty image.")
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return image_data
    if image_data.startswith(b"\xff\xd8\xff"):
        return image_data
    raise RuntimeError(
        f"Cloudflare returned an unsupported image format ({content_type or 'unknown'})."
    )


def GenerateImage(
    prompt: str,
    size: str = "1024x1024",
    model: str = IMAGE_MODEL,
) -> list[str]:
    """Generate and save three seeded variations of a prompt with Cloudflare Workers AI."""
    if not prompt or not prompt.strip():
        raise ValueError("An image description is required.")
    if not ACCOUNT_ID:
        raise RuntimeError("Account_ID is missing from .env.")
    if not API_TOKEN:
        raise RuntimeError("API_Token is missing from .env.")

    size_match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not size_match:
        raise ValueError("Image size must use the WIDTHxHEIGHT format.")
    width, height = (int(value) for value in size_match.groups())
    if not (256 <= width <= 2048 and 256 <= height <= 2048):
        raise ValueError("Image width and height must each be between 256 and 2048.")

    endpoint = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{quote(ACCOUNT_ID, safe='')}/ai/run/{quote(model, safe='/@')}"
    )
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    safe_prompt = re.sub(r"[^A-Za-z0-9_-]+", "_", prompt.strip()[:30]).strip("_")
    safe_prompt = safe_prompt or "generated_image"
    seeds = set()
    while len(seeds) < 3:
        seeds.add(secrets.randbelow(2**31))

    def generate_image_data(seed: int) -> bytes:
        response = requests.post(
            endpoint,
            headers=headers,
            json={
                "prompt": prompt.strip(),
                "width": width,
                "height": height,
                "seed": seed,
            },
            timeout=120,
        )
        if not response.ok:
            try:
                error_payload = response.json()
                errors = error_payload.get("errors", [])
                details = "; ".join(
                    str(item.get("message", ""))
                    for item in errors
                    if isinstance(item, dict) and item.get("message")
                )
            except ValueError:
                details = ""
            message = details or response.reason
            raise RuntimeError(
                f"Cloudflare image request failed (HTTP {response.status_code}): {message}"
            )
        return _image_bytes(response)

    image_paths = []
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            image_data_list = list(executor.map(generate_image_data, seeds))

        for index, image_data in enumerate(image_data_list, start=1):
            extension = ".png" if image_data.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"
            image_path = OUTPUT_DIR / (
                f"{safe_prompt}_{secrets.token_hex(8)}_{index}{extension}"
            )
            image_path.write_bytes(image_data)
            image_paths.append(str(image_path))
    except Exception as error:
        for image_path in image_paths:
            Path(image_path).unlink(missing_ok=True)
        print(f"[ERROR] Cloudflare image generation failed ({type(error).__name__}): {error}")
        raise RuntimeError(f"Image generation failed: {error}") from error

    return image_paths


def ExtractImagePrompt(decision_text: str) -> str:
    """Extract the prompt from a `generate image(prompt)` intent."""
    match = re.search(
        r"generate\s+image\s*\((.*)\)\s*$",
        decision_text,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""
