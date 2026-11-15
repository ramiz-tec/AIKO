import json
import math
import re
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from backend.DesignGeneration import generate_design_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT / "Data" / "Workspace"
PROJECT_TYPES = {
    "3D": {".aiko3d", ".obj", ".stl"},
    "Circuits": {".aikocircuit", ".brd", ".circ", ".ino", ".json", ".txt"},
}
PRIMITIVES = {"box", "sphere", "cylinder"}
WORKBENCH_STATE_FILE = ".aiko-workbench-state.json"


def _part(
    name: str,
    shape: str,
    position: tuple[float, float, float],
    size: tuple[float, float, float],
) -> dict[str, Any]:
    return {
        "name": name,
        "shape": shape,
        "position": list(position),
        "size": list(size),
    }


def ensure_workspace() -> Path:
    for folder_name in ("3D", "Circuits"):
        (WORKSPACE_ROOT / folder_name).mkdir(parents=True, exist_ok=True)
    return WORKSPACE_ROOT


def _project_directory(project_type: str) -> Path:
    if project_type not in PROJECT_TYPES:
        raise ValueError(f"Unknown workspace project type: {project_type}.")
    ensure_workspace()
    return WORKSPACE_ROOT / project_type


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w .()-]+", "_", name, flags=re.UNICODE).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "Untitled project"


def create_folder(
    name: str,
    project_type: str = "3D",
    parent: str | Path | None = None,
) -> Path:
    directory = _validated_target_directory(project_type, parent)
    folder = directory / _safe_name(name)
    folder.mkdir(exist_ok=False)
    return folder


def _validated_target_directory(project_type: str, folder: str | Path | None) -> Path:
    root = _project_directory(project_type).resolve()
    directory = (root if folder is None else Path(folder).resolve())
    if not directory.is_relative_to(root) or not directory.is_dir():
        raise ValueError("Choose a folder inside the selected workspace.")
    return directory


def load_workbench_transform(path: str | Path) -> dict[str, Any] | None:
    project_path = Path(path).expanduser().resolve(strict=True)
    workspace_root = WORKSPACE_ROOT.resolve()
    if not project_path.is_relative_to(workspace_root) or not project_path.is_file():
        raise ValueError("Workbench transforms can only be loaded for workspace files.")
    state_path = workspace_root / WORKBENCH_STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read saved hologram edits: {error}") from error
    if not isinstance(state, dict):
        raise ValueError("Saved hologram edits have an invalid format.")
    transform = state.get(str(project_path))
    if transform is None:
        return None
    _validate_workbench_transform(transform)
    return transform


def save_workbench_transform(
    path: str | Path,
    transform: dict[str, Any],
) -> None:
    save_workbench_transforms({str(path): transform})


def save_workbench_transforms(
    transforms: dict[str, dict[str, Any]],
) -> None:
    workspace_root = WORKSPACE_ROOT.resolve()
    saved_transforms = {}
    for path, transform in transforms.items():
        project_path = Path(path).expanduser().resolve(strict=True)
        if (
            not project_path.is_relative_to(workspace_root)
            or not project_path.is_file()
        ):
            raise ValueError(
                "Workbench transforms can only be saved for workspace files."
            )
        _validate_workbench_transform(transform)
        saved_transforms[str(project_path)] = {
            "offset": list(transform["offset"]),
            "scale": transform["scale"],
            "rotation": list(transform["rotation"]),
            **{
                key: transform[key]
                for key in ("reference_size", "fit_scale")
                if key in transform
            },
        }
    state_path = workspace_root / WORKBENCH_STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read saved hologram edits: {error}") from error
    if not isinstance(state, dict):
        raise ValueError("Saved hologram edits have an invalid format.")
    state.update(saved_transforms)
    temporary_path = state_path.with_name(f"{state_path.name}.tmp")
    try:
        temporary_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary_path.replace(state_path)
    except OSError as error:
        raise ValueError(f"Could not save hologram edits: {error}") from error


def _validate_workbench_transform(transform: Any) -> None:
    if not isinstance(transform, dict):
        raise ValueError("A saved hologram transform must be an object.")
    offset = transform.get("offset")
    rotation = transform.get("rotation")
    scale = transform.get("scale")
    if (
        not isinstance(offset, list)
        or len(offset) != 3
        or not isinstance(rotation, list)
        or len(rotation) != 3
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in offset + rotation
        )
        or any(abs(value) > 1000 for value in offset)
        or not isinstance(scale, (int, float))
        or isinstance(scale, bool)
        or not math.isfinite(scale)
        or scale < 0.1
        or scale > 10
    ):
        raise ValueError("The saved hologram transform is invalid.")
    for key in ("reference_size", "fit_scale"):
        value = transform.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("The saved hologram size reference is invalid.")


def import_project(
    source_path: str | Path,
    project_type: str = "3D",
    folder: str | Path | None = None,
) -> Path:
    source = Path(source_path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Choose a project file to import.")
    suffix = source.suffix.lower()
    if suffix not in PROJECT_TYPES.get(project_type, set()):
        raise ValueError(
            f"{suffix or 'This file'} is not a supported {project_type} workspace file."
        )

    destination_directory = _validated_target_directory(project_type, folder)
    destination = destination_directory / _safe_name(source.name)
    if destination.exists() and destination.samefile(source):
        return destination
    if destination.exists():
        destination = destination_directory / (
            f"{source.stem}_{len(list(destination_directory.iterdir())) + 1}{suffix}"
        )
    shutil.copy2(source, destination)
    if project_type == "3D":
        set_active_project(destination)
    return destination


def move_project(source_path: str | Path, destination_folder: str | Path) -> Path:
    source = Path(source_path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Only workspace files can be moved between folders.")
    project_type = next(
        (
            candidate
            for candidate in PROJECT_TYPES
            if source.is_relative_to((WORKSPACE_ROOT / candidate).resolve())
        ),
        None,
    )
    if project_type is None:
        raise ValueError("The file is not inside an AIKO workspace.")
    destination_directory = _validated_target_directory(
        project_type, destination_folder
    )
    destination = destination_directory / source.name
    if destination.exists():
        raise FileExistsError(f"A file named {source.name!r} already exists there.")
    active_project = get_active_project() if project_type == "3D" else None
    shutil.move(str(source), str(destination))
    if active_project == source:
        set_active_project(destination)
    return destination


def add_external_project(
    name: str,
    project_url: str,
    project_type: str = "3D",
    folder: str | Path | None = None,
) -> Path:
    if not re.fullmatch(r"https://www\.tinkercad\.com/things/[A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)?/?", project_url):
        raise ValueError("Enter a Tinkercad design URL.")
    directory = _validated_target_directory(project_type, folder)
    link_file = directory / f"{_safe_name(name)}.tinkercad.json"
    if link_file.exists():
        raise FileExistsError(f"A Tinkercad link named {name!r} already exists.")
    link_file.write_text(
        json.dumps({"name": name.strip() or "Tinkercad design", "url": project_url}, indent=2),
        encoding="utf-8",
    )
    return link_file


def list_projects(
    project_type: str = "3D",
    folder: str | Path | None = None,
) -> list[dict[str, Any]]:
    directory = _validated_target_directory(project_type, folder)
    projects = []
    for path in directory.iterdir():
        if path.is_dir():
            projects.append({"name": path.name, "path": str(path), "kind": "folder"})
        elif path.name.lower().endswith(".tinkercad.json"):
            try:
                details = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"Could not read Tinkercad link {path.name}: {error}") from error
            projects.append({
                "name": str(details.get("name") or path.stem),
                "path": str(path),
                "kind": "link",
                "url": str(details.get("url") or ""),
            })
        elif path.is_file() and path.suffix.lower() in PROJECT_TYPES[project_type]:
            projects.append({
                "name": path.stem,
                "path": str(path),
                "kind": "model" if project_type == "3D" else "circuit",
            })
    order_file = directory / ".aiko-order.json"
    try:
        order = json.loads(order_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        order = []
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read workspace item order: {error}") from error
    order_index = {
        str(path): index for index, path in enumerate(order) if isinstance(path, str)
    }
    return sorted(
        projects,
        key=lambda project: (
            0 if project["kind"] == "folder" else 1,
            order_index.get(project["path"], len(order) + 1),
            project["name"].casefold(),
        ),
    )


def save_item_order(folder: str | Path, project_type: str, paths: list[str]) -> None:
    directory = _validated_target_directory(project_type, folder)
    known_paths = {
        project["path"] for project in list_projects(project_type, directory)
    }
    if any(path not in known_paths for path in paths):
        raise ValueError("Workspace order can only include items in the current folder.")
    (directory / ".aiko-order.json").write_text(
        json.dumps(paths, indent=2),
        encoding="utf-8",
    )


def create_design(prompt: str, folder: str | Path | None = None) -> Path:
    if not prompt or not prompt.strip():
        raise ValueError("Describe the 3D project to create.")
    if folder is None:
        destination_directory = _project_directory("3D")
    else:
        destination_directory = _validated_target_directory("3D", folder)

    parts = generate_design_parts(prompt.strip())
    safe_prompt = _safe_name(prompt)[:48]
    path = destination_directory / f"{safe_prompt}.aiko3d"
    if path.exists():
        path = destination_directory / f"{safe_prompt}_{len(list(destination_directory.glob(safe_prompt + '*'))) + 1}.aiko3d"
    save_design(path, {"name": safe_prompt, "prompt": prompt.strip(), "parts": parts})
    set_active_project(path)
    return path


def set_active_project(path: str | Path) -> Path:
    project_path = Path(path).expanduser().resolve(strict=True)
    project_root = (WORKSPACE_ROOT / "3D").resolve()
    if not project_path.is_relative_to(project_root) or not project_path.is_file():
        raise ValueError("The active project must be a file in the 3D workspace.")
    ensure_workspace()
    (WORKSPACE_ROOT / ".aiko-active-project.json").write_text(
        json.dumps({"path": str(project_path)}, indent=2),
        encoding="utf-8",
    )
    return project_path


def get_active_project() -> Path | None:
    active_file = WORKSPACE_ROOT / ".aiko-active-project.json"
    try:
        details = json.loads(active_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read the active workspace project: {error}") from error
    project_path = details.get("path") if isinstance(details, dict) else None
    if not isinstance(project_path, str):
        raise ValueError("The active workspace project entry is invalid.")
    resolved = Path(project_path).resolve()
    root = (WORKSPACE_ROOT / "3D").resolve()
    return resolved if resolved.is_relative_to(root) and resolved.is_file() else None


def clear_active_project() -> None:
    active_file = WORKSPACE_ROOT / ".aiko-active-project.json"
    try:
        active_file.unlink(missing_ok=True)
    except OSError as error:
        raise ValueError(f"Could not close the active workspace project: {error}") from error


def remove_project(path: str | Path) -> Path:
    project_path = Path(path).expanduser().resolve(strict=True)
    root = WORKSPACE_ROOT.resolve()
    trash = (WORKSPACE_ROOT / ".Trash").resolve()
    if (
        not project_path.is_relative_to(root)
        or project_path.is_relative_to(trash)
        or not project_path.is_file()
    ):
        raise ValueError("Only workspace files can be moved to the workspace trash.")
    trash.mkdir(parents=True, exist_ok=True)
    destination = trash / project_path.name
    if destination.exists():
        destination = trash / f"{project_path.stem}_{len(list(trash.iterdir())) + 1}{project_path.suffix}"
    shutil.move(str(project_path), str(destination))
    if get_active_project() == project_path:
        (WORKSPACE_ROOT / ".aiko-active-project.json").unlink(missing_ok=True)
    return destination


def find_project(name: str) -> Path:
    target = name.strip().casefold()
    if not target:
        raise ValueError("Provide the exact workspace file name to remove.")
    ensure_workspace()
    candidate = Path(name).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise FileNotFoundError(f"No workspace file named {name!r} was found.") from error
        if (
            resolved.is_file()
            and any(
                resolved.is_relative_to((WORKSPACE_ROOT / project_type).resolve())
                for project_type in PROJECT_TYPES
            )
        ):
            return resolved
        raise ValueError("The requested file must be inside an AIKO workspace folder.")
    matches = [
        path
        for project_type in PROJECT_TYPES
        for path in (WORKSPACE_ROOT / project_type).rglob("*")
        if path.is_file()
        and not path.name.startswith(".")
        and (
            path.name.casefold() == target
            or path.stem.casefold() == target
        )
    ]
    if not matches:
        raise FileNotFoundError(f"No workspace file named {name!r} was found.")
    if len(matches) > 1:
        raise ValueError(f"More than one workspace file is named {name!r}; use a full path.")
    return matches[0]


def parse_workspace_command(query: str) -> tuple[str, str] | None:
    normalized = query.strip().strip(" \t\r\n.,!?")
    normalized = re.sub(
        r"^(?:please|can you|could you|would you)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:(?:i|we)\s+(?:want|wanna|need)\s+to\s+|"
        r"(?:i|we)\s+(?:want|wanna|need)\s+|"
        r"(?:i|we)(?:\s+would|\s*['’]d)\s+like\s+to\s+|"
        r"let(?:'|’)s\s+|lets\s+)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:tell me|show me)\s+(?=(?:what|describe|list)\b)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = normalized.strip(" \t\r\n.,!?")

    if re.fullmatch(
        r"(?:what (?:am i|i['’]m|im) working on|"
        r"what(?:'s| is) on (?:the |my )?workbench|"
        r"what (?:is|are) in (?:the |my )?(?:workspace|workbench)|"
        r"what (?:files|folders|projects) (?:are|do i have) "
        r"(?:in|inside) (?:my |the )?(?:workspace|workbench)|"
        r"what project am i working on|"
        r"what do i have on (?:the |my )?workbench|"
        r"describe (?:the )?workspace|"
        r"list (?:the )?(?:workspace )?(?:files|projects))",
        normalized,
        re.IGNORECASE,
    ):
        return "describe", ""

    creation_request = re.fullmatch(
        r"(?:(?:i|we)\s+(?:want|wanna|need)\s+to\s+|"
        r"(?:i|we)\s+(?:want|need)\s+|"
        r"(?:i|we)(?:\s+would|\s*['’]d)\s+like\s+to\s+|"
        r"(?:i\s+)?need\s+|let(?:'|’)s\s+|lets\s+|help me\s+)?"
        r"(?:(?:work on|start|create|make|design)\s+)?"
        r"(?:a\s+)?(?:(?:new|another)\s+)?(?:3d\s+)?"
        r"(?:design|project|model)"
        r"(?:\s+(?:of|for|called|named)\s+(.+))?",
        normalized,
        re.IGNORECASE,
    )
    if creation_request:
        description = (creation_request.group(1) or "").strip()
        return "create", description

    resume_request = re.fullmatch(
        r"(?:go(?:ing)? back to|return to|resume|work on|open|load|select)\s+"
        r"(?:(?:my|the|a)\s+)?(?:project|design)\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if resume_request:
        return "open_project", resume_request.group(1).strip(" \"'")
    if re.fullmatch(
        r"(?:go(?:ing)? back to|return to|resume)\s+"
        r"(?:(?:my|the|a)\s+)?(?:project|design)",
        normalized,
        re.IGNORECASE,
    ):
        return "open_project", ""

    exact_commands = (
        (r"(?:open|show)\s+(?:the\s+)?workspace", "open", ""),
        (r"(?:close|hide)\s+(?:the\s+)?workspace", "close_workspace", ""),
        (r"(?:go\s+)?back(?:\s+to\s+the\s+parent\s+folder)?", "back", ""),
        (r"(?:snap|combine)\s+(?:the\s+)?holograms?", "combine", ""),
        (r"(?:clear|empty)\s+(?:the\s+)?workbench", "clear_workbench", ""),
        (r"(?:exit|leave)\s+(?:the\s+)?focus", "exit_focus", ""),
        (r"(?:remove|close)\s+(?:the\s+)?last\s+hologram", "remove_last_hologram", ""),
        (
            r"(?:remove|close)\s+(?:the\s+)?(?:selected|focused)\s+hologram",
            "remove_selected_hologram",
            "",
        ),
        (
            r"(?:rotate|enable)\s+(?:the\s+)?selected\s+rotation\s+mode",
            "toggle_rotation",
            "",
        ),
        (r"(?:rotate|enable)\s+rotate\s+selected", "toggle_rotation", ""),
        (r"rotate\s+selected(?:\s+items?)?", "toggle_rotation", ""),
        (
            r"(?:add|new|create|make)\s+(?:a\s+)?(?:new\s+)?folder",
            "create_folder",
            "",
        ),
        (r"import\s+(?:a\s+)?(?:workspace\s+)?file", "import_file", ""),
        (r"(?:remove|delete)\s+(?:a\s+)?(?:workspace\s+)?file", "remove_file", ""),
        (r"move\s+(?:a\s+)?part", "move_part", ""),
        (
            r"(?:open|load|select)\s+(?:a\s+)?(?:workspace\s+)?project",
            "open_project",
            "",
        ),
        (
            r"(?:add|create)\s+(?:a\s+)?(?:tinkercad\s+)?link",
            "add_link",
            "",
        ),
    )
    for pattern, action, payload in exact_commands:
        if re.fullmatch(pattern, normalized, re.IGNORECASE):
            return action, payload

    match = re.fullmatch(
        r"(?:add|new|create|make)\s+(?:a\s+)?(?:new\s+)?folder"
        r"(?:\s+(?:named|called)\s+|\s+)(.+)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "create_folder", match.group(1).strip(" \"'")

    match = re.fullmatch(
        r"(?:switch|change)\s+(?:to\s+)?(?:the\s+)?"
        r"(3d|3d designs?|circuits?)\s*(?:workspace|folder)?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        project_type = (
            "Circuits"
            if match.group(1).lower().startswith("circuit")
            else "3D"
        )
        return "switch_type", project_type

    match = re.fullmatch(
        r"(?:open|load|select)\s+(?:the\s+)?(?:workspace\s+)?"
        r"(?:project|design|file)\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "open_project", match.group(1).strip(" \"'")
    match = re.fullmatch(
        r"(?:open|load)\s+(?:the\s+)?folder\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "open_project", match.group(1).strip(" \"'")
    match = re.fullmatch(
        r"(?:open|load|select)\s+(.+?)\s+(?:project|design)\b",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "open_project", match.group(1).strip(" \"'")
    match = re.fullmatch(
        r"(?:close|unload)\s+(?:(?:the|my)\s+)?"
        r"(?:(?:selected|current|active)\s+)?project(?:\s+(.+))?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "close_project", (match.group(1) or "").strip(" \"'")
    match = re.fullmatch(
        r"(?:close|unload)\s+(?:the\s+)?project\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "close_project", match.group(1).strip(" \"'")

    match = re.fullmatch(
        r"(?:focus|zoom\s+in\s+on|select)\s+(?:the\s+)?"
        r"(?:hologram|project|design)(?:\s+named)?(?:\s+(.+))?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "focus_project", (match.group(1) or "").strip(" \"'")

    if re.fullmatch(
        r"(?:shrink|reduce|decrease|zoom\s+out)"
        r"(?:\s+(?:(?:the\s+)?(?:selected\s+)?(?:hologram|item|it|that)))?",
        normalized,
        re.IGNORECASE,
    ):
        return "shrink", ""
    if re.fullmatch(
        r"(?:enlarge|increase|grow|zoom\s+in)"
        r"(?:\s+(?:(?:the\s+)?(?:selected\s+)?(?:hologram|item|it|that)))?",
        normalized,
        re.IGNORECASE,
    ):
        return "enlarge", ""
    match = re.fullmatch(
        r"rotate\s+(?:(?:the\s+)?(?:selected\s+)?(?:hologram|item|it|that)\s+)?"
        r"(?:(?:around|along|on)\s+)?([xyz])(?:\s+axis)?"
        r"(?:\s+by)?(?:\s+(-?\d+(?:\.\d+)?))?(?:\s+degrees?)?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "rotate", f"{match.group(1).lower()} {match.group(2) or '15'}"

    match = re.fullmatch(
        r"(?:add|create)\s+(?:a\s+)?(?:tinkercad\s+)?link\s+"
        r"(?:named\s+)?(.+?)\s+(?:at|url)\s+"
        r"(https://www\.tinkercad\.com/things/\S+)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip(" \"'")
        url = match.group(2).rstrip(".,!?")
        return "add_link", f"{name}|{url}"

    match = re.fullmatch(
        r"import\s+(?:workspace\s+)?(?:file\s+)?(.+)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "import_file", match.group(1).strip(" \"'")
    if re.fullmatch(
        r"(?:export|save)\s+(?:the\s+)?(?:design\s+)?(?:as\s+)?stl",
        normalized,
        re.IGNORECASE,
    ):
        return "export_stl", ""
    if re.fullmatch(
        r"(?:open|create|start)\s+(?:a\s+)?"
        r"(?:(?:new|another)\s+)?(?:browser\s+)?tab",
        normalized,
        re.IGNORECASE,
    ):
        return None
    match = re.fullmatch(
        r"move\s+(?:the\s+)?part\s+(.+?)\s+(?:along\s+)?([xyz])"
        r"(?:\s+axis)?\s+(?:to|at|by)\s+(-?\d+(?:\.\d+)?)",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return "move_part", "|".join(match.groups())

    if re.match(
        r"^(?:(?:make|create|generate)\s+(?:me\s+)?"
        r"(?:(?:an?|new)\s+){0,2})?(?:images?|pictures?)\b",
        normalized,
        re.IGNORECASE,
    ):
        return None
    design_match = re.fullmatch(
        r"(?:new|create|make)\s+(?:a\s+)?(?:new\s+)?(?:3d\s+)?"
        r"(?:design|model|project)\s+"
        r"(?:(?:of|for|called|named)\s+)?(.+)",
        normalized,
        re.IGNORECASE,
    )
    if design_match:
        return "create", design_match.group(1).strip()
    create_match = re.fullmatch(
        r"(?:create|generate|make|design)\s+(?:me\s+)?(?:an?\s+)?"
        r"(?:3d\s+)?(?:design|model|project)\s+"
        r"(?:(?:of|for|called|named)\s+)?(.+)",
        normalized,
        re.IGNORECASE,
    )
    if create_match:
        return "create", create_match.group(1).strip()
    blueprint_match = re.fullmatch(
        r"(?:(?:create|generate|make|design)\s+(?:me\s+)?"
        r"(?:(?:an?|new)\s+){0,2})?blueprint"
        r"(?:\s+(?:of|for)\s*(.*))?",
        normalized,
        re.IGNORECASE,
    )
    if blueprint_match:
        subject = (blueprint_match.group(1) or "").strip()
        return "create", f"blueprint of {subject}" if subject else ""
    item_match = re.fullmatch(
        r"(?:generate|create|make|design)\b"
        r"(?:(?:\s+(?:me|us|a|an|the|new|3d|design|model|item|object|project|of|for|called|named)))*"
        r"\s*(.*)",
        normalized,
        re.IGNORECASE,
    )
    if item_match:
        return "create", item_match.group(1).strip()
    add_match = re.fullmatch(
        r"add\s+(?:a\s+)?(box|sphere|cylinder)(?:\s+part)?"
        r"(?:\s+to\s+(?:my\s+|the\s+)?(?:current\s+|selected\s+)?"
        r"(?:3d\s+)?(?:design|project|hologram))?",
        normalized,
        re.IGNORECASE,
    )
    if add_match:
        return "add_part", add_match.group(1).casefold()
    if re.fullmatch(
        r"add\s+(?:a\s+)?(?:part|primitive)"
        r"(?:\s+to\s+(?:my\s+|the\s+)?(?:current\s+|selected\s+)?"
        r"(?:3d\s+)?(?:design|project|hologram))?",
        normalized,
        re.IGNORECASE,
    ):
        return "add_part", ""
    if re.fullmatch(
        r"(?:remove|delete)\s+(?:the\s+)?(?:last\s+|selected\s+)?part"
        r"(?:\s+from\s+(?:my\s+|the\s+)?(?:current\s+|selected\s+)?"
        r"(?:3d\s+)?(?:design|project|hologram))?",
        normalized,
        re.IGNORECASE,
    ):
        return "remove_part", "last"
    import_file = re.fullmatch(
        r"import\s+(?:workspace\s+)?file\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if import_file:
        return "import_file", import_file.group(1).strip().strip("\"'")
    if re.fullmatch(
        r"remove\s+(?:the\s+)?(?:last\s+)?part\s+from\s+"
        r"(?:my\s+|the\s+)?(?:current\s+|selected\s+)?(?:3d\s+)?"
        r"(?:design|project)",
        normalized,
        re.IGNORECASE,
    ):
        return "remove_part", "last"
    remove_file = re.fullmatch(
        r"(?:remove|delete)\s+(?:the\s+)?(?:workspace\s+)?file\s+(.+)",
        normalized,
        re.IGNORECASE,
    )
    if remove_file:
        return "remove_file", remove_file.group(1).strip().strip("\"'")
    if re.fullmatch(r"open\s+(?:the\s+)?workspace", normalized, re.IGNORECASE):
        return "open", ""
    return None


def load_design(path: str | Path) -> dict[str, Any]:
    project_path = Path(path).resolve(strict=True)
    if project_path.suffix.lower() != ".aiko3d":
        raise ValueError("Only AIKO parametric 3D projects can be edited.")
    try:
        design = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read the 3D project: {error}") from error
    if not isinstance(design, dict) or not isinstance(design.get("parts"), list):
        raise ValueError("The 3D project has an invalid part list.")
    return design


def save_design(path: str | Path, design: dict[str, Any]) -> None:
    project_path = Path(path).resolve()
    if project_path.suffix.lower() != ".aiko3d":
        raise ValueError("AIKO projects must use the .aiko3d extension.")
    parts = design.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("A 3D project must contain at least one part.")
    for part in parts:
        _validate_part(part)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(json.dumps(design, indent=2), encoding="utf-8")


def _validate_part(part: Any) -> None:
    if not isinstance(part, dict) or part.get("shape") not in PRIMITIVES:
        raise ValueError("Parts must use a supported box, sphere, or cylinder shape.")
    position = part.get("position")
    size = part.get("size")
    if (
        not isinstance(position, list)
        or not isinstance(size, list)
        or len(position) != 3
        or len(size) != 3
        or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in position + size)
        or any(value <= 0 or value > 1000 for value in size)
    ):
        raise ValueError("Parts need three finite position and size values.")


def add_part(path: str | Path, shape: str, name: str | None = None) -> dict[str, Any]:
    shape = shape.casefold()
    if shape not in PRIMITIVES:
        raise ValueError("Choose a box, sphere, or cylinder part.")
    design = load_design(path)
    part = {
        "name": _safe_name(name or f"{shape.title()} {len(design['parts']) + 1}"),
        "shape": shape,
        "position": [0.0, 0.0, float(len(design["parts"]))],
        "size": [1.0, 1.0, 1.0],
    }
    design["parts"].append(part)
    save_design(path, design)
    return part


def remove_part(path: str | Path, index: int) -> dict[str, Any]:
    design = load_design(path)
    if len(design["parts"]) <= 1:
        raise ValueError("A 3D project must keep at least one part.")
    if index < 0 or index >= len(design["parts"]):
        raise IndexError("Choose a valid part to remove.")
    removed = design["parts"].pop(index)
    save_design(path, design)
    return removed


def load_mesh(path: str | Path) -> list[tuple[tuple[float, float, float], ...]]:
    mesh_path = Path(path).resolve(strict=True)
    if mesh_path.suffix.lower() == ".obj":
        return _load_obj(mesh_path)
    if mesh_path.suffix.lower() == ".stl":
        return _load_stl(mesh_path)
    if mesh_path.suffix.lower() == ".aiko3d":
        return mesh_from_design(load_design(mesh_path))
    if mesh_path.suffix.lower() == ".brd":
        return _load_eagle_board(mesh_path)
    raise ValueError(
        "Preview supports OBJ, STL, EAGLE board (.brd), and AIKO 3D projects."
    )


def load_mesh_with_materials(
    path: str | Path,
) -> tuple[
    list[tuple[tuple[float, float, float], ...]],
    list[str] | None,
]:
    mesh_path = Path(path).resolve(strict=True)
    if mesh_path.suffix.lower() == ".brd":
        return _load_eagle_board(mesh_path, with_materials=True)
    return load_mesh(mesh_path), None


def load_mesh_for_workbench(
    path: str | Path,
) -> tuple[
    list[tuple[tuple[float, float, float], ...]],
    list[str] | None,
]:
    mesh_path = Path(path).resolve(strict=True)
    suffix = mesh_path.suffix.lower()
    if suffix == ".obj":
        return _load_obj(mesh_path, normalize=False), None
    if suffix == ".stl":
        return _load_stl(mesh_path, normalize=False), None
    if suffix == ".aiko3d":
        return mesh_from_design(load_design(mesh_path), normalize=False), None
    if suffix == ".brd":
        return _load_eagle_board(
            mesh_path, with_materials=True, normalize=False
        )
    raise ValueError(
        "Workbench supports OBJ, STL, EAGLE board (.brd), and AIKO 3D projects."
    )


_BOX_FACES = (
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
)


def _append_box(
    triangles: list[tuple[tuple[float, float, float], ...]],
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
    z_bounds: tuple[float, float],
) -> None:
    x_min, x_max = x_bounds
    y_min, y_max = y_bounds
    z_min, z_max = z_bounds
    vertices = [
        (x_min, y_min, z_min),
        (x_max, y_min, z_min),
        (x_max, y_max, z_min),
        (x_min, y_max, z_min),
        (x_min, y_min, z_max),
        (x_max, y_min, z_max),
        (x_max, y_max, z_max),
        (x_min, y_max, z_max),
    ]
    triangles.extend(
        tuple(vertices[index] for index in face) for face in _BOX_FACES
    )


def _append_oriented_box(
    triangles: list[tuple[tuple[float, float, float], ...]],
    corners: list[tuple[float, float]],
    z_bounds: tuple[float, float],
) -> None:
    vertices = [
        (x, y, z)
        for z in z_bounds
        for x, y in corners
    ]
    triangles.extend(
        tuple(vertices[index] for index in face) for face in _BOX_FACES
    )


def _append_footprint_line(
    triangles: list[tuple[tuple[float, float, float], ...]],
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
    z_bounds: tuple[float, float],
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return
    offset_x = -dy / length * width / 2
    offset_y = dx / length * width / 2
    corners = [
        (start[0] + offset_x, start[1] + offset_y),
        (end[0] + offset_x, end[1] + offset_y),
        (end[0] - offset_x, end[1] - offset_y),
        (start[0] - offset_x, start[1] - offset_y),
    ]
    z = z_bounds[1]
    points = [(x, y, z) for x, y in corners]
    triangles.extend((
        (points[0], points[2], points[1]),
        (points[0], points[3], points[2]),
    ))


def _append_annulus(
    triangles: list[tuple[tuple[float, float, float], ...]],
    center: tuple[float, float],
    outer_radius: float,
    inner_radius: float,
    z_bounds: tuple[float, float],
    segments: int = 8,
) -> None:
    inner_radius = max(0.0, min(inner_radius, outer_radius * 0.9))
    for index in range(segments):
        angle0 = math.tau * index / segments
        angle1 = math.tau * (index + 1) / segments
        outer0 = (
            center[0] + outer_radius * math.cos(angle0),
            center[1] + outer_radius * math.sin(angle0),
        )
        outer1 = (
            center[0] + outer_radius * math.cos(angle1),
            center[1] + outer_radius * math.sin(angle1),
        )
        inner0 = (
            center[0] + inner_radius * math.cos(angle0),
            center[1] + inner_radius * math.sin(angle0),
        )
        inner1 = (
            center[0] + inner_radius * math.cos(angle1),
            center[1] + inner_radius * math.sin(angle1),
        )
        _, top = z_bounds
        triangles.extend((
            ((outer0[0], outer0[1], top),
             (outer1[0], outer1[1], top),
             (inner1[0], inner1[1], top)),
            ((outer0[0], outer0[1], top),
             (inner1[0], inner1[1], top),
             (inner0[0], inner0[1], top)),
        ))


def _append_cylinder(
    triangles: list[tuple[tuple[float, float, float], ...]],
    center: tuple[float, float],
    radius: float,
    z_bounds: tuple[float, float],
    segments: int = 16,
) -> None:
    bottom, top = z_bounds
    for index in range(segments):
        angle0 = math.tau * index / segments
        angle1 = math.tau * (index + 1) / segments
        center_bottom = (center[0], center[1], bottom)
        center_top = (center[0], center[1], top)
        bottom0 = (
            center[0] + radius * math.cos(angle0),
            center[1] + radius * math.sin(angle0),
            bottom,
        )
        bottom1 = (
            center[0] + radius * math.cos(angle1),
            center[1] + radius * math.sin(angle1),
            bottom,
        )
        top0 = (bottom0[0], bottom0[1], top)
        top1 = (bottom1[0], bottom1[1], top)
        triangles.extend((
            (center_bottom, bottom1, bottom0),
            (center_top, top0, top1),
            (bottom0, bottom1, top1),
            (bottom0, top1, top0),
        ))


def _eagle_number(value: str | None, description: str) -> float:
    try:
        number = float(value) if value is not None else math.nan
    except ValueError as error:
        raise ValueError(f"Invalid {description} in EAGLE board.") from error
    if not math.isfinite(number):
        raise ValueError(f"Invalid {description} in EAGLE board.")
    return number


def _eagle_package_bounds(package: ET.Element) -> tuple[float, float, float, float]:
    x_values = []
    y_values = []
    for shape in package:
        if shape.tag == "wire":
            x_values.extend((
                _eagle_number(shape.get("x1"), "package coordinate"),
                _eagle_number(shape.get("x2"), "package coordinate"),
            ))
            y_values.extend((
                _eagle_number(shape.get("y1"), "package coordinate"),
                _eagle_number(shape.get("y2"), "package coordinate"),
            ))
        elif shape.tag == "rectangle":
            x_values.extend((
                _eagle_number(shape.get("x1"), "package coordinate"),
                _eagle_number(shape.get("x2"), "package coordinate"),
            ))
            y_values.extend((
                _eagle_number(shape.get("y1"), "package coordinate"),
                _eagle_number(shape.get("y2"), "package coordinate"),
            ))
        elif shape.tag == "circle":
            x = _eagle_number(shape.get("x"), "package coordinate")
            y = _eagle_number(shape.get("y"), "package coordinate")
            radius = _eagle_number(shape.get("radius"), "package radius")
            x_values.extend((x - radius, x + radius))
            y_values.extend((y - radius, y + radius))
        elif shape.tag in {"pad", "smd"}:
            x = _eagle_number(shape.get("x"), "pad coordinate")
            y = _eagle_number(shape.get("y"), "pad coordinate")
            diameter = max(
                _eagle_number(shape.get("diameter", "0"), "pad diameter"),
                _eagle_number(shape.get("dx", "0"), "pad width"),
                _eagle_number(shape.get("dy", "0"), "pad height"),
            )
            x_values.extend((x - diameter / 2, x + diameter / 2))
            y_values.extend((y - diameter / 2, y + diameter / 2))
    if not x_values or not y_values:
        return -2.5, 2.5, -2.5, 2.5
    return min(x_values), max(x_values), min(y_values), max(y_values)


def _eagle_element_rotation(element: ET.Element) -> tuple[float, bool]:
    match = re.fullmatch(r"(M)?R([-+]?\d+(?:\.\d+)?)", element.get("rot", "R0"))
    if match is None:
        raise ValueError("Unsupported component rotation in EAGLE board.")
    return math.radians(float(match.group(2))), match.group(1) is not None


def _load_eagle_board(
    path: Path,
    with_materials: bool = False,
    normalize: bool = True,
) -> (
    list[tuple[tuple[float, float, float], ...]]
    | tuple[list[tuple[tuple[float, float, float], ...]], list[str]]
):
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ValueError(f"Could not read EAGLE board: {error}") from error
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("EAGLE board is too large to preview (20 MB maximum).")
    try:
        xml_text = content.decode("utf-8-sig")
        xml_text = re.sub(r"<!DOCTYPE[^>]*>", "", xml_text, count=1)
        eagle = ET.fromstring(xml_text)
    except (UnicodeDecodeError, ET.ParseError) as error:
        raise ValueError(f"Could not parse EAGLE board XML: {error}") from error
    board = eagle.find("./drawing/board")
    if eagle.tag != "eagle" or board is None:
        raise ValueError("The .brd file is not an EAGLE board export.")

    dimension_wires = [
        wire for wire in board.findall("./plain/wire")
        if wire.get("layer") == "20"
    ]
    coordinates = [
        (
            _eagle_number(wire.get(key_x), "board coordinate"),
            _eagle_number(wire.get(key_y), "board coordinate"),
        )
        for wire in dimension_wires
        for key_x, key_y in (("x1", "y1"), ("x2", "y2"))
    ]
    packages = {
        package.get("name"): package
        for package in board.findall("./libraries/library/packages/package")
        if package.get("name")
    }
    elements = board.findall("./elements/element")
    if coordinates:
        x_bounds = min(point[0] for point in coordinates), max(
            point[0] for point in coordinates
        )
        y_bounds = min(point[1] for point in coordinates), max(
            point[1] for point in coordinates
        )
    elif elements:
        positions = [
            (
                _eagle_number(element.get("x"), "component coordinate"),
                _eagle_number(element.get("y"), "component coordinate"),
            )
            for element in elements
        ]
        x_bounds = min(x for x, _ in positions) - 5, max(
            x for x, _ in positions
        ) + 5
        y_bounds = min(y for _, y in positions) - 5, max(
            y for _, y in positions
        ) + 5
    else:
        raise ValueError("The EAGLE board has no outline or placed components.")
    if x_bounds[1] <= x_bounds[0] or y_bounds[1] <= y_bounds[0]:
        raise ValueError("The EAGLE board outline has no area.")

    material_groups: dict[
        str, list[tuple[tuple[float, float, float], ...]]
    ] = {
        material: []
        for material in (
            "board",
            "arduino",
            "lcd_body",
            "lcd_screen",
            "pot_body",
            "pot_knob",
            "battery",
            "generic",
            "pads",
            "copper",
            "unrouted",
        )
    }
    board_bottom = -1.6
    board_top = 0.0
    triangles = material_groups["board"]
    _append_box(triangles, x_bounds, y_bounds, (board_bottom, board_top))

    for element in elements:
        package = packages.get(element.get("package"))
        if package is None:
            continue
        x = _eagle_number(element.get("x"), "component coordinate")
        y = _eagle_number(element.get("y"), "component coordinate")
        angle, mirrored = _eagle_element_rotation(element)
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        local_x_min, local_x_max, local_y_min, local_y_max = (
            _eagle_package_bounds(package)
        )
        corners = []
        for local_x, local_y in (
            (local_x_min, local_y_min),
            (local_x_max, local_y_min),
            (local_x_max, local_y_max),
            (local_x_min, local_y_max),
        ):
            if mirrored:
                local_x = -local_x
            corners.append((
                x + local_x * cos_angle - local_y * sin_angle,
                y + local_x * sin_angle + local_y * cos_angle,
            ))
        label = f"{element.get('name', '')} {element.get('value', '')} {package.get('name', '')}".casefold()
        is_arduino = any(keyword in label for keyword in ("arduino", "uno"))
        is_lcd = any(keyword in label for keyword in ("lcd", "display"))
        is_potentiometer = any(keyword in label for keyword in ("pot", "trimmer"))
        is_battery = any(keyword in label for keyword in ("battery", "9v"))
        if is_arduino:
            body_material = "arduino"
        elif is_lcd:
            body_material = "lcd_body"
        elif is_potentiometer:
            body_material = "pot_body"
        elif is_battery:
            body_material = "battery"
        else:
            body_material = "generic"
        if is_arduino:
            component_height = 2.0
        elif is_lcd:
            component_height = 5.0
        elif is_potentiometer:
            component_height = 4.0
        elif is_battery:
            component_height = 2.5
        else:
            component_height = min(
                6.0,
                max(2.0, min(local_x_max - local_x_min, local_y_max - local_y_min) * 0.35),
            )
        component_bottom = board_top + 0.35
        component_top = component_bottom + component_height
        component_center = (
            x + (local_x_min + local_x_max) / 2 * cos_angle
              - (local_y_min + local_y_max) / 2 * sin_angle,
            y + (local_x_min + local_x_max) / 2 * sin_angle
              + (local_y_min + local_y_max) / 2 * cos_angle,
        )
        if is_potentiometer:
            triangles = material_groups["pot_body"]
            circles = package.findall("circle")
            radius = max(
                (
                    _eagle_number(circle.get("radius"), "component radius")
                    for circle in circles
                ),
                default=min(local_x_max - local_x_min, local_y_max - local_y_min) / 2,
            )
            circle = next(iter(circles), None)
            if circle is not None:
                local_center_x = _eagle_number(circle.get("x"), "component coordinate")
                local_center_y = _eagle_number(circle.get("y"), "component coordinate")
                component_center = (
                    x + (-local_center_x if mirrored else local_center_x) * cos_angle
                      - local_center_y * sin_angle,
                    y + (-local_center_x if mirrored else local_center_x) * sin_angle
                      + local_center_y * cos_angle,
                )
            _append_cylinder(
                triangles, component_center, radius * 0.82,
                (component_bottom, component_top), segments=12,
            )
            triangles = material_groups["pot_knob"]
            _append_cylinder(
                triangles, component_center, radius * 0.58,
                (component_top, component_top + 1.4), segments=12,
            )
        else:
            triangles = material_groups[body_material]
            _append_oriented_box(
                triangles, corners, (component_bottom, component_top)
            )
            if is_lcd:
                triangles = material_groups["lcd_screen"]
                screen_center_x = (local_x_min + local_x_max) / 2
                screen_center_y = (local_y_min + local_y_max) / 2
                screen_half_width = (local_x_max - local_x_min) * 0.32
                screen_half_height = (local_y_max - local_y_min) * 0.20
                screen_corners = []
                for local_x, local_y in (
                    (screen_center_x - screen_half_width, screen_center_y - screen_half_height),
                    (screen_center_x + screen_half_width, screen_center_y - screen_half_height),
                    (screen_center_x + screen_half_width, screen_center_y + screen_half_height),
                    (screen_center_x - screen_half_width, screen_center_y + screen_half_height),
                ):
                    screen_corners.append((
                        x + local_x * cos_angle - local_y * sin_angle,
                        y + local_x * sin_angle + local_y * cos_angle,
                    ))
                _append_oriented_box(
                    triangles,
                    screen_corners,
                    (component_top + 0.04, component_top + 0.12),
                )
                triangles = material_groups["lcd_body"]
                bezel_half_width = screen_half_width + 1.2
                bezel_half_height = screen_half_height + 1.2
                bezel_outer = []
                bezel_inner = []
                for half_width, half_height, corners_out in (
                    (bezel_half_width, bezel_half_height, bezel_outer),
                    (screen_half_width, screen_half_height, bezel_inner),
                ):
                    for local_x, local_y in (
                        (screen_center_x - half_width, screen_center_y - half_height),
                        (screen_center_x + half_width, screen_center_y - half_height),
                        (screen_center_x + half_width, screen_center_y + half_height),
                        (screen_center_x - half_width, screen_center_y + half_height),
                    ):
                        corners_out.append((
                            x + local_x * cos_angle - local_y * sin_angle,
                            y + local_x * sin_angle + local_y * cos_angle,
                        ))
                for index in range(4):
                    next_index = (index + 1) % 4
                    side = [
                        bezel_outer[index],
                        bezel_outer[next_index],
                        bezel_inner[next_index],
                        bezel_inner[index],
                    ]
                    _append_oriented_box(
                        triangles, side,
                        (component_top + 0.13, component_top + 0.35),
                    )

        pad_z = (board_top + 0.06, board_top + 0.15)
        triangles = material_groups["pads"]
        for pad in package.findall("pad"):
            local_pad_x = _eagle_number(pad.get("x"), "pad coordinate")
            local_pad_y = _eagle_number(pad.get("y"), "pad coordinate")
            pad_x, pad_y = (
                (-local_pad_x if mirrored else local_pad_x),
                local_pad_y,
            )
            pad_center = (
                x + pad_x * cos_angle - pad_y * sin_angle,
                y + pad_x * sin_angle + pad_y * cos_angle,
            )
            drill = _eagle_number(pad.get("drill", "0"), "pad drill")
            diameter = _eagle_number(
                pad.get("diameter") or str(max(1.8, drill * 1.8)),
                "pad diameter",
            )
            if drill > 0 and diameter > drill:
                _append_annulus(
                    triangles, pad_center, diameter / 2, drill / 2, pad_z
                )
            else:
                _append_cylinder(triangles, pad_center, diameter / 2, pad_z, 8)

        for smd in package.findall("smd"):
            local_pad_x = _eagle_number(smd.get("x"), "SMD coordinate")
            local_pad_y = _eagle_number(smd.get("y"), "SMD coordinate")
            center_x = -local_pad_x if mirrored else local_pad_x
            pad_center = (
                x + center_x * cos_angle - local_pad_y * sin_angle,
                y + center_x * sin_angle + local_pad_y * cos_angle,
            )
            half_width = _eagle_number(smd.get("dx"), "SMD width") / 2
            half_height = _eagle_number(smd.get("dy"), "SMD height") / 2
            pad_corners = []
            for local_x, local_y in (
                (-half_width, -half_height),
                (half_width, -half_height),
                (half_width, half_height),
                (-half_width, half_height),
            ):
                if mirrored:
                    local_x = -local_x
                pad_corners.append((
                    pad_center[0] + local_x * cos_angle - local_y * sin_angle,
                    pad_center[1] + local_x * sin_angle + local_y * cos_angle,
                ))
            _append_oriented_box(
                triangles, pad_corners, pad_z
            )

        detail_z = (component_top + 0.04, component_top + 0.10)
        triangles = material_groups[body_material]
        for wire in package.findall("wire"):
            if wire.get("layer") not in {"21", "51"}:
                continue
            start_x = _eagle_number(wire.get("x1"), "footprint coordinate")
            start_y = _eagle_number(wire.get("y1"), "footprint coordinate")
            end_x = _eagle_number(wire.get("x2"), "footprint coordinate")
            end_y = _eagle_number(wire.get("y2"), "footprint coordinate")
            if mirrored:
                start_x, end_x = -start_x, -end_x
            start = (
                x + start_x * cos_angle - start_y * sin_angle,
                y + start_x * sin_angle + start_y * cos_angle,
            )
            end = (
                x + end_x * cos_angle - end_y * sin_angle,
                y + end_x * sin_angle + end_y * cos_angle,
            )
            width = max(
                0.12,
                _eagle_number(wire.get("width", "0"), "footprint line width"),
            )
            _append_footprint_line(triangles, start, end, width, detail_z)

        for circle in package.findall("circle"):
            if circle.get("layer") not in {"21", "51"}:
                continue
            local_x = _eagle_number(circle.get("x"), "footprint coordinate")
            local_y = _eagle_number(circle.get("y"), "footprint coordinate")
            if mirrored:
                local_x = -local_x
            circle_center = (
                x + local_x * cos_angle - local_y * sin_angle,
                y + local_x * sin_angle + local_y * cos_angle,
            )
            radius = _eagle_number(circle.get("radius"), "footprint radius")
            width = max(
                0.12,
                _eagle_number(circle.get("width", "0"), "footprint line width"),
            )
            _append_annulus(
                triangles, circle_center, radius, max(0.01, radius - width),
                detail_z, segments=12,
            )

        for rectangle in package.findall("rectangle"):
            if rectangle.get("layer") not in {"21", "51"}:
                continue
            local_corners = (
                (
                    _eagle_number(rectangle.get(key_x), "footprint coordinate"),
                    _eagle_number(rectangle.get(key_y), "footprint coordinate"),
                )
                for key_x, key_y in (
                    ("x1", "y1"), ("x2", "y1"),
                    ("x2", "y2"), ("x1", "y2"),
                )
            )
            world_corners = []
            for local_x, local_y in local_corners:
                if mirrored:
                    local_x = -local_x
                world_corners.append((
                    x + local_x * cos_angle - local_y * sin_angle,
                    y + local_x * sin_angle + local_y * cos_angle,
                ))
            for index in range(4):
                _append_footprint_line(
                    triangles,
                    world_corners[index],
                    world_corners[(index + 1) % 4],
                    0.10,
                    detail_z,
                )

    for signal in board.findall("./signals/signal"):
        for wire in signal.findall("wire"):
            start_x = _eagle_number(wire.get("x1"), "signal coordinate")
            start_y = _eagle_number(wire.get("y1"), "signal coordinate")
            end_x = _eagle_number(wire.get("x2"), "signal coordinate")
            end_y = _eagle_number(wire.get("y2"), "signal coordinate")
            dx = end_x - start_x
            dy = end_y - start_y
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            layer = wire.get("layer")
            triangles = material_groups[
                "unrouted" if layer == "19" else "copper"
            ]
            _append_footprint_line(
                triangles,
                (start_x, start_y),
                (end_x, end_y),
                max(0.12, _eagle_number(wire.get("width", "0"), "signal width")),
                (board_top + 0.02, board_top + 0.06),
            )

    grouped_triangles = [
        (triangle, material)
        for material, material_triangles in material_groups.items()
        for triangle in material_triangles
    ]
    triangles = [triangle for triangle, _ in grouped_triangles]
    normalized_mesh = _normalize_mesh(triangles) if normalize else triangles
    if with_materials:
        return normalized_mesh, [
            material for _, material in grouped_triangles
        ]
    return normalized_mesh


def _load_obj(
    path: Path,
    normalize: bool = True,
) -> list[tuple[tuple[float, float, float], ...]]:
    vertices = []
    triangles = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Could not read OBJ file: {error}") from error
    for line_number, line in enumerate(lines, start=1):
        fields = line.strip().split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "v" and len(fields) >= 4:
            try:
                vertex = tuple(float(value) for value in fields[1:4])
            except ValueError as error:
                raise ValueError(f"Invalid OBJ vertex on line {line_number}.") from error
            if any(not math.isfinite(value) for value in vertex):
                raise ValueError(f"Invalid OBJ vertex on line {line_number}.")
            vertices.append(vertex)
        elif fields[0] == "f" and len(fields) >= 4:
            try:
                raw_face = [int(field.split("/", 1)[0]) for field in fields[1:]]
                if any(index == 0 for index in raw_face):
                    raise ValueError
                face = raw_face
                face = [
                    index - 1 if index > 0 else len(vertices) + index
                    for index in face
                ]
                if any(index < 0 or index >= len(vertices) for index in face):
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"Invalid OBJ face on line {line_number}.") from error
            triangles.extend(
                (vertices[face[0]], vertices[face[index]], vertices[face[index + 1]])
                for index in range(1, len(face) - 1)
            )
    if not triangles:
        raise ValueError("The OBJ file does not contain any triangle faces.")
    return _normalize_mesh(triangles) if normalize else triangles


def _load_stl(
    path: Path,
    normalize: bool = True,
) -> list[tuple[tuple[float, float, float], ...]]:
    data = path.read_bytes()
    triangles = []
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            for index in range(count):
                offset = 84 + index * 50 + 12
                vertices = struct.unpack_from("<9f", data, offset)
                triangles.append(tuple(
                    tuple(vertices[start:start + 3])
                    for start in (0, 3, 6)
                ))
    if not triangles:
        try:
            tokens = data.decode("ascii").split()
            coordinates = [
                (float(tokens[index + 1]), float(tokens[index + 2]), float(tokens[index + 3]))
                for index, token in enumerate(tokens[:-3])
                if token.casefold() == "vertex"
            ]
        except (UnicodeDecodeError, ValueError, IndexError) as error:
            raise ValueError("The STL file is neither valid binary nor ASCII STL.") from error
        if len(coordinates) % 3:
            raise ValueError("The ASCII STL contains an incomplete triangle.")
        triangles = [
            tuple(coordinates[index:index + 3])
            for index in range(0, len(coordinates), 3)
        ]
    if not triangles:
        raise ValueError("The STL file does not contain any triangles.")
    return _normalize_mesh(triangles) if normalize else triangles


def mesh_from_design(
    design: dict[str, Any],
    normalize: bool = True,
) -> list[tuple[tuple[float, float, float], ...]]:
    triangles = []
    for part in design.get("parts", []):
        _validate_part(part)
        x, y, z = part["position"]
        width, depth, height = part["size"]
        width, depth, height = width / 2, depth / 2, height / 2
        if part["shape"] == "box":
            vertices = [
                (x - width, y - depth, z - height),
                (x + width, y - depth, z - height),
                (x + width, y + depth, z - height),
                (x - width, y + depth, z - height),
                (x - width, y - depth, z + height),
                (x + width, y - depth, z + height),
                (x + width, y + depth, z + height),
                (x - width, y + depth, z + height),
            ]
            faces = (
                (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
                (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
                (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
            )
            triangles.extend(tuple(vertices[index] for index in face) for face in faces)
        elif part["shape"] == "sphere":
            stacks = 8
            sides = 16
            rows = []
            for stack in range(stacks + 1):
                latitude = -math.pi / 2 + math.pi * stack / stacks
                radius = math.cos(latitude)
                height_offset = math.sin(latitude)
                rows.append([
                    (
                        x + width * radius * math.cos(2 * math.pi * side / sides),
                        y + depth * radius * math.sin(2 * math.pi * side / sides),
                        z + height * height_offset,
                    )
                    for side in range(sides)
                ])
            for stack in range(stacks):
                for side in range(sides):
                    next_side = (side + 1) % sides
                    triangles.extend((
                        (rows[stack][side], rows[stack][next_side], rows[stack + 1][next_side]),
                        (rows[stack][side], rows[stack + 1][next_side], rows[stack + 1][side]),
                    ))
        else:
            sides = 16
            lower = []
            upper = []
            for side in range(sides):
                angle = 2 * math.pi * side / sides
                lower.append((x + width * math.cos(angle), y + depth * math.sin(angle), z - height))
                upper.append((x + width * math.cos(angle), y + depth * math.sin(angle), z + height))
            for side in range(sides):
                next_side = (side + 1) % sides
                triangles.extend((
                    (lower[side], lower[next_side], upper[next_side]),
                    (lower[side], upper[next_side], upper[side]),
                    ((x, y, z - height), lower[next_side], lower[side]),
                    ((x, y, z + height), upper[side], upper[next_side]),
                ))
    return _normalize_mesh(triangles) if normalize else triangles


def export_design_to_stl(path: str | Path, output_path: str | Path) -> Path:
    design = load_design(path)
    triangles = mesh_from_design(design)
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = b"AIKO parametric 3D project".ljust(80, b"\0")
    content = bytearray(header + struct.pack("<I", len(triangles)))
    for triangle in triangles:
        a, b, c = triangle
        ab = tuple(b[index] - a[index] for index in range(3))
        ac = tuple(c[index] - a[index] for index in range(3))
        normal = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        length = math.sqrt(sum(value * value for value in normal)) or 1.0
        values = tuple(value / length for value in normal) + tuple(
            coordinate for vertex in triangle for coordinate in vertex
        )
        content.extend(struct.pack("<12fH", *values, 0))
    destination.write_bytes(content)
    return destination


def _normalize_mesh(
    triangles: list[tuple[tuple[float, float, float], ...]],
) -> list[tuple[tuple[float, float, float], ...]]:
    vertices = [vertex for triangle in triangles for vertex in triangle]
    if not vertices:
        return []
    mins = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maxs = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    center = [(minimum + maximum) / 2 for minimum, maximum in zip(mins, maxs)]
    scale = max(maximum - minimum for minimum, maximum in zip(mins, maxs)) or 1
    return [
        tuple(
            tuple((coordinate[axis] - center[axis]) / scale for axis in range(3))
            for coordinate in triangle
        )
        for triangle in triangles
    ]
