---
"trae-agent": minor
---

### New Features

- **Micro-Compression for OrchestratorAgent**: PLANNING / CODING / REVIEWING
  phases now integrate micro-compression with dual-trigger model:
  - SEMANTIC: natural-boundary keywords ("step completed", "moving on",
    "summarize", "next step", "here is a summary")
  - FORCED: every 10 steps or 3 consecutive tool errors
- **Safe atomic cut** (`find_safe_cut`): backtracking Algorithm B guarantees
  `tool_call` / `tool_result` atomic pairs are never split during compression,
  preventing 400 errors from providers that validate call chains.
- **Lazy-load refs**: tool outputs exceeding 1024 characters are replaced
  with `[lazy-ref:hash]` placeholders in compressed summaries.

### Security

- **`FileBackend` path traversal prevention**: resolved path is validated
  to ensure it stays within the workspace directory; `read()` uses
  `try/except FileNotFoundError` instead of TOCTOU-prone `exists()` check.
- **Markdown injection prevention**: `_escape_md_lines()` escapes `## `-prefixed
  lines in LLM-generated content to prevent section-boundary injection.
- **Sensitive data TODO**: explicit hook marker for future content scrubber
  integration in the summarization path.
- **`CompressionContext.last_message`**: new field enables semantic trigger
  evaluation from the last assistant response text.

### Refactoring

- **`BaseAgent._compress_messages`** delegates to `MicroCompressionStrategy`
  with proper `last_compression_step` state tracking (方案 B), eliminating
  the per-call instantiation overhead and redundant step-interval checks.
  Includes `_reset_llm_client_history()` call for client-side state consistency.
  (Addresses findings F-1, F-4, F-5.)
- **`MicroCompressionStrategy`** moved to `BaseAgent.__init__` as a shared
  singleton instance (matching `OrchestratorAgent.__init__` pattern).

### Bug Fixes

- **`MicroCompressionStrategy.compress()` report trigger**: now dynamically
  detects SEMANTIC vs FORCED trigger via `_detect_trigger()`, replacing the
  previously hardcoded `CompressionTrigger.FORCED`.
- **`MicroCompressionStrategy.should_compress()`**: dual-trigger evaluation
  (semantic OR forced) instead of forced-only.

### Testing

- `tests/agent/test_orchestrator_compression.py` — 4 tests (TC-1–TC-4)
  covering step-interval trigger, consecutive error trigger, client history
  reset, and no-trigger boundary condition.
- `tests/test_phase2_compression.py` — 55→87 tests (32 new) covering
  `find_safe_cut` edge cases, `from_markdown` error recovery,
  `MicroCompressionStrategy` semantic/forced triggers, `_escape_md_lines`.
- `tests/agent/test_context_compression.py` — updated 2 tests for unified
  `MicroCompressionStrategy` format.

### Design Decisions

- **`BaseAgent._compress_messages` intentional limitations**: The single-phase
  ReAct loop deliberately passes `consecutive_errors=0` and `last_message=None`
  to `CompressionContext`. Error tracking is the `OrchestratorAgent`'s
  responsibility (it has per-step visibility into tool results). Semantic
  triggering requires `last_assistant_message` capture which the
  `OrchestratorAgent`'s `_run_phase()` maintains explicitly between iterations.
  The base agent compresses only on step-interval forced triggers — any
  richer triggering belongs in the orchestrator, which has the necessary
  execution context.
