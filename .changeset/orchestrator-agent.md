---
"trae-agent": minor
---

## Phase 4 — OrchestratorAgent: Multi-Phase Execution Architecture

### Breaking Changes

- **`AgentType` enum**: New member `OrchestratorAgent = "orchestrator_agent"`. Consumers that match exhaustively on `AgentType` must add a case.
- **`AgentStepState` enum**: 5 new values — `PLANNING`, `CODING`, `REVIEWING`, `WAITING`, `RETRYING` (10 total). Consumers that match exhaustively must add cases.
- **`BaseAgent`**:
  - New `allow_mcp_servers: list[str] | None` attribute (default `None`).
  - New `initialise_mcp()` async method (no-op base, overridden by `TraeAgent`).
  - New abstract method pattern: `cleanup_mcp_clients()` already existed; `initialise_mcp()` added alongside it for symmetry.

### New Features

- **`OrchestratorAgent`** (`trae_agent/agent/orchestrator_agent.py`):
  - 3-phase execution flow: `PLANNING → CODING → REVIEWING`
  - Each phase runs an isolated ReAct loop with:
    - Fresh message context (no cross-phase message bleed)
    - Per-phase system prompt (`PLANNER_SYSTEM_PROMPT`, `CODER_SYSTEM_PROMPT`, `REVIEWER_SYSTEM_PROMPT`)
    - Per-phase tool permission isolation via `PHASE_TOOL_NAMES` dict
    - Structured text handoff between phases (no raw message sharing)
  - Phase completion signals:
    - PLANNING: "plan completed" in LLM response content
    - CODING: `task_done` tool call detected
    - REVIEWING: `**Pass**`, `**Fail**`, or `## Review Verdict` in content
  - `MAX_STEPS_PER_PHASE = 30` inner-loop bound
  - Error handling: LLM exceptions caught per-phase, returned as error string (execution continues to remaining phases)

- **`Agent` facade** (`trae_agent/agent/agent.py`):
  - Routes `AgentType.OrchestratorAgent` to `OrchestratorAgent` via match/case
  - `self.agent` type widened from `TraeAgent` to `BaseAgent`

- **Context compression** (`BaseAgent._compress_messages`):
  - Deterministic summarization triggered at `step_number % 10 == 0` AND `len(messages) > 30`
  - Preserves: system prompt + last 15 messages verbatim
  - Compresses middle section: extracts tool result outcomes (success/failure) and assistant "plan"/"approach" content
  - Injects `Context Summary` message at position 1

- **LLM client history reset** (`BaseAgent._reset_llm_client_history`):
  - Resets `self._llm_client.client.message_history = []` after compression
  - Wrapped in `contextlib.suppress(AttributeError)` for client variants without `message_history`

### Bug Fixes

- **`TraeAgent.reflect_on_result`**: Replaced bare `return None` with error-specific reflection guidance strings (timeout, not found, permission denied, default)
- **`BaseAgent._tool_call_handler`**: Fixed handling of `None` and empty `tool_calls`:
  - `None` (no tool_call field): if substantive content (>20 chars), treat as thinking; else nudge LLM
  - Empty list: if content exists, pass through; else push "not completed" message
- **`BaseAgent._run_llm_step`**: Fixed `tool_calls = getattr(llm_response, 'tool_calls', [])` — was returning `None` from Anthropic responses, now correctly defaults to empty list

### Tool Isolation

- **`PHASE_TOOL_NAMES`** per phase:
  - PLANNING: `str_replace_based_edit_tool`, `sequentialthinking` (read-only, no bash)
  - CODING: All `TraeAgentToolNames` (full tool access including `bash`, `task_done`)
  - REVIEWING: `str_replace_based_edit_tool`, `bash`, `sequentialthinking` (no `task_done`)

### Testing

- `tests/agent/test_agent_basics.py` — 8 tests for `AgentStepState` new values
- `tests/agent/test_context_compression.py` — 11 tests covering threshold, preservation, failure summaries, client history reset
- `tests/agent/test_orchestrator_agent.py` — 23 tests covering phase constants, completion detection, tool isolation, context handoff, full 3-phase execution, error handling, AgentType registration
- `tests/agent/test_trae_agent.py` — 7 existing tests (no regressions)
