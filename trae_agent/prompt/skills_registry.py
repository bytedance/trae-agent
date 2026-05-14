# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Dynamic SkillsRegistry — project context detection and architecture prompt mounting.

Detects the language, build system, and framework conventions of the target
project, then assembles context-specific architecture constraints into a prompt
fragment injected into the orchestrator's handoff messages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Detected project context ────────────────────────────────────────────────


@dataclass
class ProjectContext:
    """Inferred characteristics of the project under analysis."""

    language: str = "unknown"
    build_system: str = "unknown"
    has_tests: bool = False
    has_lint_config: bool = False
    has_ci_config: bool = False
    has_docker: bool = False
    has_changesets: bool = False
    frameworks: list[str] = field(default_factory=list)
    project_type: str = "unknown"  # library | cli | web | service


# ── Architecture constraint prompts ─────────────────────────────────────────


_ARCHITECTURE_PROMPTS: dict[str, str] = {
    "python": """
## Python architecture conventions
- Use `pyproject.toml` for project metadata; avoid `setup.py` for new code.
- Async I/O via `asyncio` — never block the event loop with sync calls.
- Type annotations are mandatory (`str | None`, not `Optional[str]`).
- Prefer pathlib over os.path; f-strings over % / .format().
- Ruff for linting (line-length 100), mypy for type checking.
- Use `@dataclass` for data containers. Use `@override` for method overrides.
""",
    "rust": """
## Rust architecture conventions
- Ownership and borrowing must be respected — no unnecessary clones.
- Use `thiserror` for library error types, `anyhow` for binary error handling.
- Prefer `impl Trait` in argument position; named generics for public APIs.
- Use `clap` for CLI argument parsing, `serde` for serialization.
- Run `cargo clippy` and `cargo fmt` before committing.
""",
    "go": """
## Go architecture conventions
- Use `context.Context` as the first parameter for all blocking/IO functions.
- Error handling: always check returned errors; never use `_` to discard them.
- Prefer table-driven tests with `testing.T`; use `go vet` before committing.
- Goroutine lifetime must be bounded — use `errgroup` or explicit cancellation.
- Avoid `init()` functions; prefer explicit initialization.
""",
    "typescript": """
## TypeScript architecture conventions
- Strict mode in tsconfig; avoid `any` — use `unknown` and type guards.
- Use `tsx` for React components, `.ts` for pure logic/modules.
- Async/await for promises; never use callbacks for async flow control.
- ESLint + Prettier for consistent formatting.
- Prefer named exports over default exports.
""",
    "javascript": """
## JavaScript architecture conventions
- Use ES modules (`import`/`export`) over CommonJS (`require`).
- JSDoc for public API documentation.
- Prefer `const` over `let`; never use `var`.
- Use `async/await` over raw promises where possible.
""",
}

# Single source of truth for language detection — both priority order and
# indicator lists are defined together.  This is the ONLY place to add or
# reorder languages.
_LANGUAGE_DETECTION_PRIORITY: list[tuple[str, list[str]]] = [
    ("python", ["pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "requirements.txt"]),
    ("rust", ["Cargo.toml"]),
    ("go", ["go.mod", "go.sum"]),
    ("typescript", ["tsconfig.json", "tsconfig.tsbuildinfo"]),
    ("javascript", ["package.json", ".eslintrc.js", "webpack.config.js"]),
]

# Derived mapping — kept for compatibility with downstream consumers.
# Adding a language? Only edit _LANGUAGE_DETECTION_PRIORITY above.
_LANGUAGE_DETECTORS: dict[str, list[str]] = dict(_LANGUAGE_DETECTION_PRIORITY)

_BUILD_SYSTEM_DETECTORS: dict[str, list[str]] = {
    "uv": ["uv.lock"],
    "pip": ["requirements.txt", "setup.py", "setup.cfg"],
    "poetry": ["poetry.lock", "pyproject.toml"],
    "cargo": ["Cargo.toml"],
    "go_modules": ["go.mod"],
    "npm": ["package-lock.json", "node_modules"],
    "yarn": ["yarn.lock"],
}

_FRAMEWORK_DETECTORS: dict[str, list[re.Pattern]] = {
    "django": [re.compile(r"django", re.IGNORECASE)],
    "flask": [re.compile(r"\bflask\b", re.IGNORECASE)],
    "fastapi": [re.compile(r"fastapi", re.IGNORECASE)],
    "react": [re.compile(r'"react"', re.IGNORECASE)],
    "nextjs": [re.compile(r'"next"', re.IGNORECASE)],
    "actix": [re.compile(r"\bactix\b", re.IGNORECASE)],
    "axum": [re.compile(r"\baxum\b", re.IGNORECASE)],
    "gin": [re.compile(r"github\.com/gin-gonic/gin")],
}

# ── Registry ────────────────────────────────────────────────────────────────


class SkillsRegistry:
    """Detect project context and assemble architecture-aware prompt fragments.

    Usage::

        registry = SkillsRegistry()
        ctx = registry.detect("/path/to/project")
        arch_prompt = registry.build_architecture_prompt(ctx)
    """

    def detect(self, project_path: str | Path) -> ProjectContext:
        """Scan the project directory and infer its characteristics."""
        root = Path(project_path).resolve()
        if not root.is_dir():
            return ProjectContext()

        # Collect the filenames present at the top level
        try:
            entries = {e.name for e in root.iterdir() if e.is_file() or e.is_symlink()}
        except OSError:
            entries = set()

        # Detect language (priority-ordered, first match wins)
        language = "unknown"
        for lang, indicators in _LANGUAGE_DETECTION_PRIORITY:
            if any(
                indicator in entries or root.joinpath(indicator).exists()
                for indicator in indicators
            ):
                language = lang
                break

        # Detect build system
        build_system = "unknown"
        for bs, indicators in _BUILD_SYSTEM_DETECTORS.items():
            if any(
                indicator in entries or root.joinpath(indicator).exists()
                for indicator in indicators
            ):
                build_system = bs
                break

        # Detect frameworks by scanning key config files
        frameworks: list[str] = []
        for fname in ("pyproject.toml", "Cargo.toml", "package.json", "go.mod"):
            fpath = root / fname
            if fpath.is_file():
                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                    for fw, patterns in _FRAMEWORK_DETECTORS.items():
                        if fw not in frameworks and any(p.search(text) for p in patterns):
                            frameworks.append(fw)
                except OSError:
                    pass

        # Project type heuristics
        project_type: str = "unknown"
        if root.joinpath("setup.py").exists() or root.joinpath("pyproject.toml").exists():
            project_type = "library"
        if (
            root.joinpath("cli.py").exists()
            or root.joinpath("main.go").exists()
            or root.joinpath("src", "main.rs").exists()
            or root.joinpath("cli.ts").exists()
        ):
            project_type = "cli"
        if root.joinpath("main.py").exists() or root.joinpath("app.py").exists():
            project_type = "service"
        if any(d.name == "migrations" for d in root.iterdir() if d.is_dir()):
            project_type = "web"

        return ProjectContext(
            language=language,
            build_system=build_system,
            has_tests=_has_tests(root),
            has_lint_config=_has_lint_config(root),
            has_ci_config=root.joinpath(".github").is_dir(),
            has_docker=root.joinpath("Dockerfile").exists()
            or root.joinpath("docker-compose.yml").exists(),
            has_changesets=root.joinpath(".changeset").is_dir(),
            frameworks=frameworks,
            project_type=project_type,
        )

    def build_architecture_prompt(self, ctx: ProjectContext | None) -> str:
        """Assemble a prompt fragment with architecture constraints for the detected project."""
        if ctx is None or ctx.language == "unknown":
            return ""

        parts = ["## Architecture Context"]

        # Language-specific conventions
        arch = _ARCHITECTURE_PROMPTS.get(ctx.language)
        if arch:
            parts.append(arch.strip())

        # Framework-specific notes
        if ctx.frameworks:
            parts.append(f"- Detected frameworks: {', '.join(sorted(ctx.frameworks))}")

        # Build system notes
        if ctx.build_system != "unknown":
            parts.append(f"- Build system: {ctx.build_system}")
            if ctx.build_system == "uv":
                parts.append("- Use `uv run <command>` instead of `python -m` or `pip`")
            elif ctx.build_system == "cargo":
                parts.append("- Use `cargo check`, `cargo test`, `cargo clippy`")

        # CI/test notes
        if ctx.has_ci_config:
            parts.append("- CI pipeline detected: check `.github/workflows/` for expected checks")
        if ctx.has_changesets:
            parts.append("- Changesets required: add or update entry in `.changeset/`")
        if ctx.has_docker:
            parts.append(
                "- Docker environment available — verify compatibility with container build"
            )
        if ctx.project_type != "unknown":
            parts.append(f"- Project type: {ctx.project_type}")

        return "\n".join(parts)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _has_tests(root: Path) -> bool:
    """Check for common test directory/file patterns."""
    candidates = [
        root / "tests",
        root / "test",
        root / "spec",
        root / "__tests__",
    ]
    if any(d.is_dir() for d in candidates):
        return True
    for f in root.iterdir():
        if f.is_file() and f.name.startswith(("test_", "test-", "spec_")):
            return True
    return False


def _has_lint_config(root: Path) -> bool:
    """Check for common linter/formatter config files."""
    indicators = {
        ".ruff.toml",
        "ruff.toml",
        ".flake8",
        ".pylintrc",
        ".eslintrc",
        ".eslintrc.js",
        ".eslintrc.json",
        ".prettierrc",
        ".prettierrc.js",
        ".golangci.yml",
        ".golangci.yaml",
        "clippy.toml",
    }
    return (
        any(root.joinpath(name).exists() for name in indicators)
        or root.joinpath("pyproject.toml").exists()
    )
