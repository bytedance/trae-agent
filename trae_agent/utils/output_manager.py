"""Output directory manager — project-based file organization.

Directory structure:
    ~/Desktop/trae-agent-outputs/
    ├── my-project/                    # 项目文件夹
    │   ├── conversation_001/          # 对话文件夹
    │   │   ├── generated_image.png
    │   │   └── trajectory.json
    │   └── conversation_002/
    │       └── ...
    └── another-project/
        └── ...

If user specifies a local folder, files go directly there (no subfolders).

Usage:
    # New project
    trae-cli project new my-project

    # List projects
    trae-cli project list

    # Use existing project
    trae-cli project use my-project

    # Specify output directory directly
    trae-cli run "任务" --output-dir /path/to/folder
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

# Module-level state
_current_project: str | None = None
_current_conversation: str | None = None
_output_dir_override: str | None = None

BASE_DIR = Path.home() / "Desktop" / "trae-agent-outputs"


def _get_projects_index() -> Path:
    """Get the projects index file."""
    index = BASE_DIR / ".projects.json"
    if not index.exists():
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text("{}")
    return index


def _load_projects() -> dict:
    """Load projects index."""
    index = _get_projects_index()
    return json.loads(index.read_text())


def _save_projects(projects: dict):
    """Save projects index."""
    index = _get_projects_index()
    index.write_text(json.dumps(projects, indent=2, ensure_ascii=False))


def new_project(name: str, output_dir: str | None = None) -> Path:
    """Create a new project.

    Args:
        name: Project name.
        output_dir: Optional custom output directory. If set, files go here directly.

    Returns:
        Project directory path.
    """
    projects = _load_projects()

    if output_dir:
        project_dir = Path(output_dir).expanduser().resolve()
        project_dir.mkdir(parents=True, exist_ok=True)
    else:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        safe_name = safe_name.strip("_") or "default"
        project_dir = BASE_DIR / safe_name
        project_dir.mkdir(parents=True, exist_ok=True)

    projects[name] = {
        "dir": str(project_dir),
        "created": datetime.now().isoformat(),
        "conversations": projects.get(name, {}).get("conversations", []),
    }
    _save_projects(projects)

    return project_dir


def list_projects() -> dict:
    """List all projects."""
    return _load_projects()


def get_project_dir(name: str) -> Path | None:
    """Get project directory by name."""
    projects = _load_projects()
    if name in projects:
        return Path(projects[name]["dir"])
    return None


def set_current_project(name: str | None):
    """Set the current active project."""
    global _current_project
    _current_project = name


def get_current_project() -> str | None:
    """Get current project name."""
    return _current_project


def set_output_dir_override(path: str | None):
    """Set a direct output directory override (bypasses project system)."""
    global _output_dir_override
    _output_dir_override = path


def new_conversation(project_name: str | None = None) -> str:
    """Create a new conversation within a project.

    Returns:
        Conversation ID (e.g. 'conversation_001')
    """
    global _current_conversation

    project = project_name or _current_project
    if not project:
        # No project set, use default
        project = "default"
        new_project(project)

    projects = _load_projects()
    if project not in projects:
        new_project(project)
        projects = _load_projects()

    convos = projects[project].get("conversations", [])
    conv_num = len(convos) + 1
    conv_id = f"conversation_{conv_num:03d}"

    convos.append({
        "id": conv_id,
        "created": datetime.now().isoformat(),
    })
    projects[project]["conversations"] = convos
    _save_projects(projects)

    _current_conversation = conv_id
    return conv_id


def get_output_dir(
    project_name: str | None = None,
    working_dir: str | None = None,
) -> Path:
    """Get the output directory for generated files.

    Priority:
    1. If output_dir_override is set, use it directly (no subfolders)
    2. If project is set, use project/conversation structure
    3. Auto-detect from working_dir
    """
    # Direct override — use as-is
    if _output_dir_override:
        out = Path(_output_dir_override).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        return out

    project = project_name or _current_project

    if project:
        # Use project directory
        project_dir = get_project_dir(project)
        if project_dir is None:
            project_dir = new_project(project)

        # Add conversation subfolder if active
        if _current_conversation:
            conv_dir = project_dir / _current_conversation
            conv_dir.mkdir(parents=True, exist_ok=True)
            return conv_dir

        return project_dir

    # Auto-detect from working_dir
    if working_dir:
        name = Path(working_dir).name
    else:
        name = Path.cwd().name

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    safe_name = safe_name.strip("_") or "default"

    out = BASE_DIR / safe_name
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate_output_path(
    filename: str | None = None,
    extension: str = ".png",
    project_name: str | None = None,
    working_dir: str | None = None,
) -> Path:
    """Generate a full output path for a new file."""
    output_dir = get_output_dir(project_name, working_dir)

    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"generated_{ts}"

    if not extension.startswith("."):
        extension = "." + extension

    if filename.endswith(extension):
        filename = filename[: -len(extension)]

    return output_dir / f"{filename}{extension}"
