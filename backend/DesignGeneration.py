import json
import logging
import math
import os
from pathlib import Path
from typing import Any

import cohere
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_PARTS = 32
MAX_POSITION = 10.0
MAX_SIZE = 10.0
MIN_SIZE = 0.05
_logger = logging.getLogger(__name__)


def _provider_config() -> tuple[str | None, str]:
    env_values = dotenv_values(PROJECT_ROOT / ".env")
    api_key = (
        os.environ.get("CohereApiKey")
        or os.environ.get("COHERE_API_KEY")
        or env_values.get("CohereApiKey")
    )
    model = (
        os.environ.get("CohereModel")
        or os.environ.get("COHERE_MODEL")
        or env_values.get("CohereModel")
        or "command-a-03-2025"
    )
    return api_key, model


def _validate_generated_parts(response: str) -> list[dict[str, Any]]:
    try:
        design = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError("The AI returned invalid JSON for the 3D design.") from error
    if not isinstance(design, dict) or not isinstance(design.get("parts"), list):
        raise ValueError("The AI response must contain a parts list.")
    parts = design["parts"]
    if not 1 <= len(parts) <= MAX_PARTS:
        raise ValueError(f"The AI design must contain between 1 and {MAX_PARTS} parts.")

    validated_parts = []
    for index, part in enumerate(parts, start=1):
        if not isinstance(part, dict):
            raise ValueError(f"AI-generated part {index} must be an object.")
        name = part.get("name")
        shape = part.get("shape")
        position = part.get("position")
        size = part.get("size")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"AI-generated part {index} needs a name.")
        if shape not in {"box", "sphere", "cylinder"}:
            raise ValueError(
                f"AI-generated part {index} has an unsupported shape; "
                "use box, sphere, or cylinder."
            )
        if (
            not isinstance(position, list)
            or not isinstance(size, list)
            or len(position) != 3
            or len(size) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or isinstance(value, float) and not math.isfinite(value)
                for value in position + size
            )
        ):
            raise ValueError(
                f"AI-generated part {index} needs three finite position and size values."
            )
        if any(abs(value) > MAX_POSITION for value in position):
            raise ValueError(
                f"AI-generated part {index} is outside the supported design bounds."
            )
        if any(value < MIN_SIZE or value > MAX_SIZE for value in size):
            raise ValueError(
                f"AI-generated part {index} has a size outside the supported range."
            )
        validated_parts.append({
            "name": name.strip()[:80],
            "shape": shape,
            "position": position,
            "size": size,
        })
    return validated_parts


def generate_design_parts(prompt: str) -> list[dict[str, Any]]:
    api_key, model = _provider_config()
    if not api_key:
        raise RuntimeError(
            "AI 3D generation requires CohereApiKey in .env or COHERE_API_KEY "
            "in the environment."
        )

    system_prompt = (
        "Create a recognizable 3D design from the user's description. Return only "
        "a JSON object with a 'parts' array. Each part must have exactly these "
        "fields: 'name' (short string), 'shape' ('box', 'sphere', or 'cylinder'), "
        "'position' ([x, y, z]), and 'size' ([width, depth, height]). Positions "
        "are part centers; sizes must be between 0.05 and 10; every coordinate "
        "must be between -10 and 10. Use at most 32 purposeful parts. Build the "
        "recognizable silhouette and defining features of the requested object; "
        "do not return one generic box for a complex request. Keep related parts "
        "aligned and appropriately scaled. Use z as vertical and place the base "
        "near z=0. A part's color and material are not supported."
    )
    try:
        completion = cohere.ClientV2(
            api_key=api_key,
            timeout=45,
            max_retries=0,
        ).chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt.strip()},
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
            temperature=0.2,
        )
    except TypeError as error:
        _logger.exception("The installed Cohere SDK is incompatible with 3D generation.")
        raise RuntimeError(
            "The installed Cohere SDK is incompatible with 3D generation. "
            "Update dependencies with `python -m pip install -r requirements.txt`, "
            "then restart AIKO."
        ) from error
    except Exception as error:
        _logger.exception("AI 3D design generation request failed.")
        status_code = getattr(error, "status_code", None)
        if status_code == 401:
            message = "Cohere rejected its API key. Check your Cohere credentials."
        elif status_code == 403:
            message = "The configured Cohere model is not available to this account."
        elif status_code == 404:
            message = f"The configured Cohere model ({model}) is unavailable."
        elif status_code == 429:
            message = "The Cohere quota or rate limit was reached. Try again later."
        else:
            message = (
                f"The Cohere 3D design request failed ({type(error).__name__}). "
                "Check the connection and Cohere configuration."
            )
        raise RuntimeError(message) from error

    try:
        response = completion.message.content[0].text
    except (AttributeError, IndexError, TypeError) as error:
        raise ValueError("Cohere returned an invalid 3D design response.") from error
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Cohere returned an empty 3D design response.")
    return _validate_generated_parts(response)
