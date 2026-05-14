# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""GlobalStateManager — long-term persistent state outside the conversation flow.

Each phase (Planner → Coder → Reviewer) reads from and writes to this
entity, providing a durable *north star* that survives compression and
phase transitions without being truncated.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ── Global state schema ───────────────────────────────────────────────────


@dataclass
class GlobalStateSchema:
    """Schema of the persistent state that travels with the entire task.

    Stored as a structured markdown file (``WORKSPACE_STATE.md``) in the
    project workspace, readable by both the orchestrator and (optionally)
    the developer for debugging.
    """

    task: str = ""
    project_path: str = ""

    # --- Planner-owned sections ---
    architecture_analysis: str = ""
    plan: str = ""

    # --- Coder-owned sections ---
    progress_log: list[str] = field(default_factory=list)
    design_decisions: list[str] = field(default_factory=list)

    # --- Reviewer-owned sections ---
    review_verdict: str = ""

    # --- Cross-cutting ---
    snapshot_history: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Serialize to a diff-friendly structured markdown document."""
        lines: list[str] = [
            "# WORKSPACE STATE",
            f"- **Task**: {self.task}",
            f"- **Project**: {self.project_path}",
            "",
            "## Architecture Analysis",
            _escape_md_lines(self.architecture_analysis or "(not yet analysed)"),
            "",
            "## Plan",
            _escape_md_lines(self.plan or "(not yet planned)"),
            "",
            "## Progress Log",
        ]
        if self.progress_log:
            lines.extend(f"- {_escape_md_lines(entry)}" for entry in self.progress_log)
        else:
            lines.append("(no progress yet)")

        lines.extend(
            [
                "",
                "## Design Decisions",
            ]
        )
        if self.design_decisions:
            lines.extend(f"- {_escape_md_lines(d)}" for d in self.design_decisions)
        else:
            lines.append("(no decisions recorded)")

        lines.extend(
            [
                "",
                "## Review Verdict",
                _escape_md_lines(self.review_verdict or "(not yet reviewed)"),
            ]
        )
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str) -> "GlobalStateSchema":
        """Deserialize from structured markdown.

        Accumulates all lines within a ``##`` section, preserving multi-
        paragraph content for ``architecture_analysis``, ``plan``, and
        ``review_verdict`` (no single-line truncation).

        Handles partially-written or corrupted input by logging a warning
        and returning a blank schema.
        """
        import logging

        logger = logging.getLogger(__name__)

        state = cls()
        current_section = ""

        # Accumulators for multi-line string sections
        arch_lines: list[str] = []
        plan_lines: list[str] = []
        review_lines: list[str] = []

        try:
            for line in text.splitlines():
                if line.startswith("## "):
                    # Flush the previous section before switching
                    _flush_text_section(
                        state, current_section, arch_lines, plan_lines, review_lines
                    )
                    # Reset accumulators for the new section
                    arch_lines, plan_lines, review_lines = [], [], []
                    current_section = line.removeprefix("## ").strip()
                elif line.startswith("- **Task**"):
                    state.task = _extract_colon_value(line)
                elif line.startswith("- **Project**"):
                    state.project_path = _extract_colon_value(line)
                else:
                    _accrue_content(
                        state,
                        current_section,
                        line,
                        arch_lines,
                        plan_lines,
                        review_lines,
                    )

            # Flush the final section
            _flush_text_section(state, current_section, arch_lines, plan_lines, review_lines)

        except Exception:
            logger.warning(
                "Failed to parse WORKSPACE_STATE.md, returning blank state",
                exc_info=True,
            )
            return cls()

        return state


# ── from_markdown helpers ─────────────────────────────────────────────────


def _extract_colon_value(line: str) -> str:
    """Return the text after the first ``: `` separator, stripped."""
    return line.split(":", 1)[-1].strip()


def _escape_md_lines(text: str) -> str:
    """Escape lines that start with ``## `` to prevent section injection.

    LLM-generated content (plan, analysis, verdict) may contain lines that
    look like markdown section headers.  Prepending ``\\`` prevents them
    from being parsed as ``## Section`` boundaries during deserialization,
    while preserving readability.
    """
    return "\n".join(f"\\{line}" if line.startswith("## ") else line for line in text.splitlines())


def _flush_text_section(
    state: GlobalStateSchema,
    section_name: str,
    arch_lines: list[str],
    plan_lines: list[str],
    review_lines: list[str],
) -> None:
    """Join accumulated lines for a text section and assign it to the state."""
    match section_name:
        case "Architecture Analysis":
            state.architecture_analysis = "\n".join(arch_lines).strip()
        case "Plan":
            state.plan = "\n".join(plan_lines).strip()
        case "Review Verdict":
            state.review_verdict = "\n".join(review_lines).strip()


def _accrue_content(
    state: GlobalStateSchema,
    section_name: str,
    line: str,
    arch_lines: list[str],
    plan_lines: list[str],
    review_lines: list[str],
) -> None:
    """Route a content line to the correct accumulator or parser.

    ``progress_log`` and ``design_decisions`` are parsed inline (list items
    prefixed with ``- ``).  Multi-line text sections accumulate into their
    respective lists for later ``_flush_text_section``.
    """
    if not line or line.startswith("#"):
        return

    match section_name:
        case "Architecture Analysis":
            arch_lines.append(line)
        case "Plan":
            plan_lines.append(line)
        case "Progress Log":
            if line.startswith("- "):
                state.progress_log.append(line.removeprefix("- "))
        case "Design Decisions":
            if line.startswith("- "):
                state.design_decisions.append(line.removeprefix("- "))
        case "Review Verdict":
            review_lines.append(line)


# ── Storage backend interface (pluggable) ──────────────────────────────────


class GlobalStateBackend(ABC):
    """Abstract storage backend for the global state.

    Default implementation is file-based, but could be swapped for
    Redis, S3, or an in-memory store for testing.
    """

    @abstractmethod
    async def read(self) -> str: ...

    @abstractmethod
    async def write(self, content: str) -> None: ...


class FileBackend(GlobalStateBackend):
    """Persist global state as ``.trae-state/WORKSPACE_STATE.md``."""

    def __init__(self, workspace_path: str) -> None:
        resolved_workspace = Path(workspace_path).resolve()
        self._path = (resolved_workspace / ".trae-state" / "WORKSPACE_STATE.md").resolve()
        if not str(self._path).startswith(str(resolved_workspace)):
            raise ValueError(
                f"Workspace state path {self._path} is outside workspace {resolved_workspace}"
            )

    async def read(self) -> str:
        try:
            return self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    async def write(self, content: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(content, encoding="utf-8")


# ── GlobalStateManager ────────────────────────────────────────────────────


class GlobalStateManager:
    """Long-lived, cross-phase state coordinator.

    Usage::

        gsm = GlobalStateManager(workspace_path="/repo")
        await gsm.load()

        # Planner initialises
        gsm.update_section("architecture_analysis", "...", phase="planning")

        # Coder reads the plan, writes progress
        plan = gsm.read_section("plan")
        gsm.log_progress("Implemented fix for X", phase="coding")

        # Reviewer reads everything and writes verdict
        gsm.update_section("review_verdict", "...", phase="reviewing")

        await gsm.persist()
    """

    # Phase-level write permissions (only Planner may write to "plan", etc.)
    _WRITE_PERMISSIONS: dict[str, set[str]] = {
        "planning": {"architecture_analysis", "plan"},
        "coding": {"progress_log", "design_decisions"},
        "reviewing": {"review_verdict"},
    }

    def __init__(self, backend: GlobalStateBackend | None = None) -> None:
        self._state = GlobalStateSchema()
        self._backend = backend or FileBackend("/tmp")
        self._dirty = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def load(self) -> None:
        """Load state from the backend.  If no state file exists, start blank."""
        raw = await self._backend.read()
        if raw:
            self._state = GlobalStateSchema.from_markdown(raw)
        self._dirty = False

    async def persist(self) -> None:
        """Flush in-memory state to the backend."""
        if not self._dirty:
            return
        await self._backend.write(self._state.to_markdown())
        self._dirty = False

    # ── Read operations ─────────────────────────────────────────────────

    def read_section(self, section: str) -> str:
        """Get the raw text content of a state section."""
        return str(getattr(self._state, section, ""))

    def get_full_state(self) -> GlobalStateSchema:
        """Return the entire state object (read-only access intended)."""
        return self._state

    def get_snapshot_history(self) -> list[str]:
        """Return a list of snapshot identifiers created so far."""
        return list(self._state.snapshot_history)

    # ── Write operations ────────────────────────────────────────────────

    def update_section(self, section: str, content: str, phase: str) -> None:
        """Write to a state section.

        Raises ``PermissionError`` if the given phase does not have write
        access to the requested section.
        """
        allowed = self._WRITE_PERMISSIONS.get(phase, set())
        if section not in allowed:
            raise PermissionError(
                f"Phase '{phase}' cannot write to section '{section}'. Allowed: {allowed}"
            )

        if section in ("progress_log", "design_decisions", "snapshot_history"):
            # List-type sections: append rather than replace
            getattr(self._state, section).append(content)
        else:
            setattr(self._state, section, content)
        self._dirty = True

    def log_progress(self, message: str, phase: str) -> None:
        """Convenience: append a timestamped progress entry."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._state.progress_log.append(f"[{timestamp}] [{phase}] {message}")
        self._dirty = True

    # ── Snapshot / rollback ─────────────────────────────────────────────

    def create_snapshot(self, label: str = "") -> str:
        """Capture a point-in-time snapshot that can be rolled back to."""
        snapshot_id = str(uuid.uuid4())[:8]
        entry = f"{snapshot_id}: {label or 'no label'}"
        self._state.snapshot_history.append(entry)
        self._dirty = True
        return snapshot_id

    def has_snapshot(self, snapshot_id: str) -> bool:
        return any(s.startswith(snapshot_id) for s in self._state.snapshot_history)

    # ── Initialisation ──────────────────────────────────────────────────

    def initialize(self, task: str, project_path: str) -> None:
        """Bootstrap the global state with task metadata.

        Called once by the orchestrator before the Planning phase.
        """
        self._state.task = task
        self._state.project_path = project_path
        self._dirty = True

    def is_initialized(self) -> bool:
        """Check whether ``initialize()`` has been called."""
        return bool(self._state.task)
