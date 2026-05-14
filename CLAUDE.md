# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- `make uv-sync` — Install all dependencies (including test/eval extras) via uv
- `make test` — Run full pytest suite (skips external-service tests: Ollama, OpenRouter, Google)
- `uv run pytest tests/path/to/test.py -k "test_name" -s` — Run a single test
- `trae-cli run "<task>"` — Run the agent on a task
- `trae-cli interactive` — Interactive conversational mode
- `make fix-format` — Auto-fix formatting with ruff
- `make pre-commit` or `make uv-pre-commit` — Run pre-commit hooks (ruff, codespell, mypy)
- `uv run ruff check .` — Lint check only
- `uv run mypy trae_agent/` — Type check

## Code Architecture

### Package: `trae_agent/`

**`agent/`** — Core agent loop:
- `base_agent.py` — Abstract `BaseAgent` with step iteration, state management, and callbacks
- `trae_agent.py` — `TraeAgent`, the concrete implementation
- `docker_manager.py` — Docker container lifecycle for sandboxed execution
- `agent.py` — `Agent` facade class: unified entry, MCP init, trajectory recording, CLI console
- `agent_basics.py` — `AgentStep`, `AgentExecution`, `AgentStepState`, `AgentState`, `AgentError`

**`tools/`** — Tool implementations the agent can call:
- `base.py` — `Tool(ABC)`, `ToolCall`, `ToolResult`, `ToolExecResult`, `ToolParameter`, `ToolExecutor` base classes
- `bash_tool.py` — Persistent bash session (120s timeout, auto-restart)
- `edit_tool.py` / `edit_tool_cli.py` — `TextEditorTool` for file editing (view/create/str_replace/insert). CLI variant uses a compiled Go binary.
- `json_edit_tool.py` / `json_edit_tool_cli.py` — `JSONEditTool` with JSONPath support
- `sequential_thinking_tool.py` — Structured reasoning with thought revision and branching
- `task_done_tool.py` — Task completion signal
- `ckg_tool.py` + `ckg/ckg_database.py` — Code Knowledge Graph
- `mcp_tool.py` — MCP tool wrapper
- `docker_tool_executor.py` — Tool execution inside Docker
- `__init__.py` — Tools registry mapping names to `Tool` subclasses

**`utils/`** — Supporting infrastructure:
- `config.py` — Config loading (YAML/JSON/env/CLI). Config classes: `ModelProvider`, `ModelConfig`, `AgentConfig`, `TraeAgentConfig`, `MCPServerConfig`, `LakeviewConfig`
- `llm_clients/` — Provider-specific clients: Anthropic, OpenAI, Google, Azure, Doubao, Ollama, OpenRouter, plus `openai_compatible_base.py` for OpenAI-compatible APIs
- `cli/` — Console output rendering (rich/textual and simple variants)
- `trajectory_recorder.py` — JSON recording of all LLM interactions and agent steps
- `mcp_client.py` — MCP client for external tool servers
- `constants.py` — `LOCAL_STORAGE_PATH = Path.home() / ".trae-agent"`

**`prompt/agent_prompt.py`** — System prompts (`TRAE_AGENT_SYSTEM_PROMPT`)

**`cli.py`** — Main asyncclick CLI entry point (`trae-cli`). Commands: `run`, `interactive`, `show-config`, `tools`

### Key Patterns
- **Tools registry**: All tools are registered in `trae_agent/tools/__init__.py` as `dict[str, type[Tool]]`
- **LLM clients**: Each provider client extends `base_client.py` patterns; OpenAI-compatible clients use `openai_compatible_base.py`
- **Config**: YAML config (`trae_config.yaml`) parsed into `@dataclass` classes. Priority: CLI > ENV > Config
- **Docker mode**: When `--docker-image` is set, tools execute inside containers managed by `DockerManager` + `DockerToolExecutor`. Uses pexpect for persistent shell interaction.
- **Trajectory recording**: Every run can output a JSON trajectory file via `--trajectory-file` for post-hoc analysis
- **Agent system**: `Agent` (facade) → `BaseAgent` (abstract, core loop) → `TraeAgent` (concrete, SWE tasks, MCP, git patches)

### Provider Recommendation
Anthropic (Claude) is the primary recommended provider. Set `--provider anthropic --model claude-sonnet-4-20250514`.

### Evaluation (`evaluation/`)
- `run_evaluation.py` supports three modes: `expr` (patch gen), `eval` (eval only), `e2e` (end-to-end)
- `setup.sh` clones and configures SWE-bench / SWE-bench-Live / Multi-SWE-bench harnesses

## Code Conventions

### File Header
Every `.py` file starts with copyright and a one-line module docstring:
```python
# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""One-line module description."""
```
Modified third-party code must retain original copyright and annotate changes (see `bash_tool.py` for the pattern).

### Imports
Grouped and sorted: standard library → third-party → local, groups separated by blank lines:
```python
import asyncio
import os
from typing import override

import yaml
from click.testing import CliRunner

from trae_agent.tools.base import Tool, ToolCallArguments
```

### Type Annotations
- Mandatory everywhere. Use Python 3.10+ syntax: `str | None` (not `Optional[str]`), `list[str]` (not `List[str]`)
- Complex types use `TypeAlias` (`from typing import TypeAlias`)
- Method overrides must use `@override` (`from typing import override`)
- `__init__` must have `-> None` return type
- Abstract methods use `@abstractmethod`; implementations use `@override`
- Pyright ignore comments: `# pyright: ignore[reportX]`

### Naming
| Kind | Style | Examples |
|------|-------|----------|
| Classes | PascalCase | `TextEditorTool`, `BaseAgent`, `DockerManager` |
| Methods/functions | snake_case | `get_name()`, `execute_task()` |
| Private/internal | leading `_` | `_session`, `_run_llm_step()` |
| Constants | UPPER_CASE | `SNIPPET_LINES`, `TRAE_AGENT_SYSTEM_PROMPT` |
| Module-level type aliases | PascalCase | `ToolCallArguments`, `ParamSchemaValue` |
| Tool registry names | snake_case | `"str_replace_based_edit_tool"` |

### Dataclasses
Use `@dataclass` for data containers, not plain classes or dicts:
```python
@dataclass
class ToolResult:
    call_id: str
    name: str
    success: bool
    result: str | None = None
    error: str | None = None
```

### Abstract Base Classes
Use `ABC` + `@abstractmethod`. Subclasses must add `@override`:
```python
class Tool(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        ...
```
Note: Ruff B027 flags bare `pass` in non-abstract methods in base classes. Use `return None` instead (see `base.py:179`).

### Async Patterns
- All IO operations use `async/await`
- Concurrent tasks use `asyncio.create_task`
- Cleanup uses `contextlib.suppress(Exception)`
- Parallel independent tasks use `asyncio.gather`

### Error Handling
- Custom exception classes: `ToolError`, `AgentError`, `ConfigError` (all inherit `Exception`)
- Tool execution failures return `ToolExecResult(error=..., error_code=-1)` — never raise inside execute()
- Non-critical cleanup uses `contextlib.suppress(Exception)` (see `base_agent.py:196`, `trae_agent.py:91`)
- Exception chaining: `raise ... from e` or `raise ... from None`

### match/case Dispatch
Command dispatch uses Python 3.10+ match/case:
```python
match command:
    case "view":
        return await self._view_handler(arguments, _path)
    case "create":
        return self._create_handler(arguments, _path)
    case _:
        return ToolExecResult(error=f"Unrecognized command {command}", error_code=-1)
```

## Testing

### Framework
Use `unittest.TestCase` (sync) or `unittest.IsolatedAsyncioTestCase` (async), with `unittest.mock`.

### Style
```python
class TestTextEditorTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = TextEditorTool()

    async def test_create_file(self):
        self.mock_file_system(exists=False)
        result = await self.tool.execute(
            ToolCallArguments({"command": "create", "path": "test.txt", "file_text": "content"})
        )
        self.assertIn("created successfully", result.output)
```

- Mock helpers use `self.addCleanup(patcher.stop)` for cleanup
- CLI tests use `CliRunner` from `click.testing`
- External service tests (Ollama, OpenRouter, Google) are skipped by default via `SKIP_*_TEST=true`

## Pre-commit Hooks

Run via `make uv-pre-commit`. Order:
1. `trailing-whitespace` — strip trailing whitespace
2. `end-of-file-fixer` — ensure final newline
3. `check-yaml` / `check-toml` — syntax check
4. `check-added-large-files` — large file guard
5. `detect-private-key` — secret leakage
6. `ruff --fix` — lint + auto-fix
7. `ruff-format` — formatting
8. `codespell` — spell check (excludes `*.jsonl`)
9. `mypy` — type check (excludes `evaluation/patch_selection`), types-PyYAML as additional dep

### Ruff Configuration (from `pyproject.toml`)
```toml
[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["B", "SIM", "C4", "E4", "E9", "E7", "F", "I"]
```
- **B**: bugbear — potential bugs
- **SIM**: simplify — code simplification
- **C4**: comprehensions — comprehension best practices
- **E4/E7/E9/F**: pycodestyle/pyflakes — syntax & style errors
- **I**: isort — import ordering

### Pyright / Mypy
Mypy runs via pre-commit. Pyright comments handle edge cases:
```python
# pyright: ignore[reportAttributeAccessIssue]
# pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
```

## Design Principles

- **Single responsibility**: each file/class focused on one concern
- **Minimal changes**: fix only what's broken; no unrelated refactoring
- **No comments by default**: only add when WHY is non-obvious (hidden constraint, subtle invariant, workaround for a specific issue)
- **Minimal docstrings**: properties and simple methods don't need docstrings; complex public APIs get a short one-liner
- **pathlib** over `os.path` for file paths
- **f-strings** for string formatting
- **Python 3.12+**: leverage new syntax (`@override`, `match/case`, `TypeAlias`, generic syntax)

## CLI Guidelines

Use `asyncclick` (not `click`):
```python
import asyncclick as click

@click.group()
def cli():
    """Short description."""
    pass

@cli.command()
@click.argument("task", required=False)
@click.option("--option-name", "-o", help="Description")
async def subcommand(task, option_name):
    """Command description."""
    ...
```

Entry point in `pyproject.toml`: `trae-cli = "trae_agent.cli:main"`

## Environment

- Python >= 3.12
- Dependency management: `uv` (not pip/pipenv)
- Dev setup: `make install-dev`
- Build system: Hatchling
