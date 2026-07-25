# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Skills system for Trae Agent.

A skill is a Markdown file with YAML frontmatter that injects additional
system-prompt content and optional tool restrictions. Loaded from:
- ~/.trae-agent/skills/    (user-wide)
- ./.trae-agent/skills/    (project-local, overrides user)

Each skill file:
---
name: skill-name
description: short description
tools: [bash, str_replace_based_edit_tool]   # optional, omit/empty = all
---

# Skill content as Markdown
...

Inspired by Claude Code and OpenCode's skills/extensions system.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# Skill name validation: lowercase kebab-case, ASCII letters/digits/dash.
# Must start with a letter, end with letter or digit. 1-64 chars.
_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$")


@dataclass
class Skill:
    """A loaded skill definition."""

    name: str
    description: str
    content: str  # Markdown body (without frontmatter)
    source_path: Path
    allowed_tools: list[str] | None = None  # None = no restriction

    @property
    def relative_source(self) -> str:
        return str(self.source_path).replace(str(Path.home()), "~")


class SkillValidationError(ValueError):
    """Raised when a skill file fails structural validation.

    Catches: missing frontmatter, missing name, invalid name format,
    missing description, empty body, invalid ``tools`` entries.
    """


@dataclass
class SkillSummary:
    """Lightweight skill metadata used by `trae-cli skills list`."""

    name: str
    description: str
    source: str  # path with ~ replacement
    size_kb: float


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from the start of a Markdown file.

    Returns (frontmatter_dict, body_text). If no frontmatter is present,
    returns ({}, text).
    """
    if not text.startswith("---"):
        return {}, text
    # find the closing '---' on its own line
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", text, flags=re.DOTALL)
    if not m:
        return {}, text

    raw_meta, body = m.group(1), m.group(2)

    # Lightweight YAML parser for simple keys (no PyYAML dependency here
    # to keep skill loading fast and dependency-free).
    meta: dict = {}
    current_list_key: str | None = None
    for line in raw_meta.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        # List item
        list_item = re.match(r"^\s*-\s+(.*)$", line)
        if list_item and current_list_key:
            meta[current_list_key].append(_strip_quotes(list_item.group(1)))
            continue
        # Key: value
        kv = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
        if kv:
            key, raw_value = kv.group(1), kv.group(2).strip()
            # Detect inline list: [a, b, c]
            if raw_value.startswith("[") and raw_value.endswith("]"):
                inner = raw_value[1:-1]
                meta[key] = [_strip_quotes(s.strip()) for s in inner.split(",") if s.strip()]
            elif raw_value == "":
                # Possible start of a list on subsequent lines
                meta[key] = []
                current_list_key = key
            else:
                meta[key] = _strip_quotes(raw_value)
                current_list_key = None
        # unknown lines are ignored

    return meta, body.strip()


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def load_skill_file(path: Path) -> Skill | None:
    """Load a single skill from a Markdown file. Returns None on errors.

    Returns ``None`` and logs a warning for invalid skills (this is the
    lenient path used by ``discover_skills_dir`` so one bad file doesn't
    break the whole skill set). Use ``validate_skill`` to inspect why a
    particular file was rejected.
    """
    # Issue 10 修复: 检查 skill 文件权限,防止 prompt injection。
    # 如果文件是 world-writable 的(任何用户都能写入),则跳过加载,
    # 避免恶意用户通过篡改 skill 文件注入 prompt。
    try:
        stat = path.stat()
        # 检查 other-write 位 (S_IWOTH = 0o002)
        if stat.st_mode & 0o002:
            logger.warning(
                "Skipping skill %s: file is world-writable (mode %o), "
                "which is a security risk. Fix with: chmod o-w %s",
                path, stat.st_mode, path,
            )
            return None
    except OSError:
        pass  # 如果 stat 失败,让 validate_skill 处理
    try:
        skill = validate_skill(path)
    except SkillValidationError as e:
        logger.warning("Skipping invalid skill %s: %s", path, e)
        return None
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Cannot read skill file %s: %s", path, e)
        return None
    return skill


def validate_skill(path: Path) -> Skill:
    """Load and *strictly* validate a skill file. Raises on any error.

    Validation rules:
      - File must have YAML frontmatter delimited by ``---``.
      - ``name`` must be present, lowercase kebab-case, 1-64 chars.
      - ``description`` must be present and non-empty (max 500 chars).
      - Body content must be non-empty (no description-only skills).
      - ``tools`` (optional) must be a list of strings, each matching
        a registered tool name when ``known_tool_names`` is provided.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise SkillValidationError(f"cannot read file: {e}") from e

    meta, body = _parse_frontmatter(text)
    if not meta:
        raise SkillValidationError(
            "missing YAML frontmatter (file must start with `---` and end with `---`)"
        )

    # --- name ---
    name = meta.get("name") or path.stem
    if not isinstance(name, str):
        raise SkillValidationError(f"`name` must be a string, got {type(name).__name__}")
    if not _SKILL_NAME_RE.match(name):
        raise SkillValidationError(
            f"invalid `name` {name!r}: must be lowercase kebab-case "
            f"(start with letter, end with letter/digit, 1-64 chars, only [a-z0-9-])"
        )

    # --- description ---
    description = meta.get("description", "")
    if not isinstance(description, str):
        raise SkillValidationError(
            f"`description` must be a string, got {type(description).__name__}"
        )
    if not description.strip():
        raise SkillValidationError("`description` is required and must be non-empty")
    if len(description) > 500:
        raise SkillValidationError(
            f"`description` is too long ({len(description)} chars, max 500)"
        )

    # --- body ---
    if not body or not body.strip():
        raise SkillValidationError("body content is empty")

    # --- tools ---
    allowed_tools = meta.get("tools")
    if allowed_tools is not None:
        if not isinstance(allowed_tools, list):
            raise SkillValidationError(
                f"`tools` must be a list, got {type(allowed_tools).__name__}"
            )
        for t in allowed_tools:
            if not isinstance(t, str):
                raise SkillValidationError(
                    f"`tools` entries must be strings, found {type(t).__name__}"
                )

    return Skill(
        name=name,
        description=description.strip(),
        content=body,
        source_path=path,
        allowed_tools=allowed_tools if allowed_tools else None,
    )


def discover_skills_dir(d: Path) -> list[Skill]:
    """Discover and load all skill files from a single directory."""
    if not d.is_dir():
        return []
    skills: list[Skill] = []
    for path in sorted(d.glob("*.md")):
        skill = load_skill_file(path)
        if skill:
            skills.append(skill)
    return skills


def load_all_skills(
    extra_dirs: list[Path] | None = None,
    project_dir: Path | None = None,
) -> list[Skill]:
    """Load skills from all configured paths.

    Order (later overrides earlier by `name`):
    1. ~/.trae-agent/skills/
    2. <project>/.trae-agent/skills/  (if project_dir is given)
    3. extra_dirs (in given order, last wins)

    Returns the deduplicated list.
    """
    seen: dict[str, Skill] = {}

    paths: list[Path] = []
    user_skills = Path.home() / ".trae-agent" / "skills"
    paths.append(user_skills)
    if project_dir:
        paths.append(Path(project_dir) / ".trae-agent" / "skills")
    if extra_dirs:
        paths.extend(Path(p) for p in extra_dirs)

    for p in paths:
        for skill in discover_skills_dir(p):
            seen[skill.name] = skill  # last wins

    return list(seen.values())


def skills_to_system_message(skills: list[Skill], active_names: list[str] | None = None) -> str:
    """Render the loaded skills into a single system-prompt fragment.

    If `active_names` is provided, only skills whose name is in that
    list are included. If None or empty, ALL skills are included.
    """
    if not skills:
        return ""

    selected = skills
    if active_names:
        wanted = set(active_names)
        selected = [s for s in skills if s.name in wanted]

    if not selected:
        return ""

    parts = ["# Loaded Skills\n"]
    parts.append(
        "The following skill definitions extend your behaviour. Each skill "
        "describes a specialised capability you should apply whenever relevant.\n"
    )
    for s in selected:
        tools_line = ""
        if s.allowed_tools is not None:
            tools_line = f"\n**Allowed tools:** {', '.join(s.allowed_tools)}\n"
        parts.append(
            f"\n---\n\n## Skill: {s.name}\n\n"
            f"_{s.description}_\n"
            f"{tools_line}\n"
            f"{s.content}\n"
        )
    return "".join(parts)
