# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Context compression strategies — micro (in-loop) and session (phase handoff).

Each strategy implements the ``ContextCompressor`` interface and is
responsible for:

- **Deciding** whether compression should fire (``should_compress``).
- **Executing** compression safely (``compress``), with a hard guarantee
  that ``tool_call`` / ``tool_result`` atomic pairs are never split.

The orchestrator owns the lifecycle: it checks micro-compression after
every ReAct step and triggers session-compression at phase boundaries.
"""

import re
from abc import ABC, abstractmethod
from typing import override

from trae_agent.compression.types import (
    CompressionContext,
    CompressionReport,
    CompressionTrigger,
    LazyRef,
    SessionSummary,
    find_safe_cut,
)
from trae_agent.tools.resolve_lazy_ref_tool import register_lazy_ref
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

# ── Interface ──────────────────────────────────────────────────────────────


class ContextCompressor(ABC):
    """Interface for all compression strategies.

    Every compressor must answer two questions:
    1. **Should we compress?** — evaluated at each ReAct iteration.
    2. **How to compress?** — produce a new message list + diagnostic report.
    """

    @abstractmethod
    def should_compress(self, ctx: CompressionContext) -> bool:
        """Return ``True`` when the strategy believes compression is warranted."""
        ...

    @abstractmethod
    def compress(
        self,
        messages: list[LLMMessage],
        ctx: CompressionContext,
    ) -> tuple[list[LLMMessage], CompressionReport]:
        """Produce a compressed message list.

        **Contract:**
        - Must never split a ``tool_call`` from its ``tool_result``.
        - Must preserve the system prompt(s) at index 0.
        - Returns ``(new_messages, report)``.
        """
        ...


# ── Layer 1: Micro-compression (in-loop safety net) ───────────────────────


class MicroCompressionStrategy(ContextCompressor):
    """Frequent, narrow-gauge compression inside a single ReAct loop.

    Dual-trigger model (``SEMANTIC ∨ FORCED``):

    *Semantic trigger* — fires when the model's response contains keywords
    indicating a natural sub-task boundary (e.g., "step completed", "moving
    on to the next step").

    *Forced trigger* — fires every N steps or when consecutive errors exceed
    a threshold, acting as a safety net against unbounded context growth or
    error spirals.

    **Lazy-load integration:** Large tool outputs (``str_replace_based_edit_tool``
    views, ``bash`` stdout) are replaced with content-hash references that the
    model can re-fetch on demand, keeping the active window lean.
    """

    # ── Configuration ──────────────────────────────────────────────────

    SEMANTIC_KEYWORDS: set[str] = {
        "step completed",
        "moving on",
        "next step",
        "summarize",
        "let me summarize",
        "here is a summary",
        "overview of what",
    }

    FORCED_STEP_INTERVAL: int = 10  # Steps since last compression
    FORCED_MAX_ERRORS: int = 3  # Consecutive tool errors
    MIN_HEAD: int = 1  # Always preserve system prompt
    TAIL_TARGET: int = 15  # Messages to keep as working set

    LARGE_OUTPUT_THRESHOLD: int = 1024  # Characters — beyond this, lazy-load

    def __init__(
        self,
        step_interval: int = FORCED_STEP_INTERVAL,
        max_errors: int = FORCED_MAX_ERRORS,
    ) -> None:
        self._step_interval = step_interval
        self._max_errors = max_errors

    @property
    def step_interval(self) -> int:
        """Public read-only access to the step interval threshold."""
        return self._step_interval

    # ── Public interface ───────────────────────────────────────────────

    def _has_semantic_trigger(self, ctx: CompressionContext) -> bool:
        """Check if the last assistant message contains semantic keywords."""
        if not ctx.last_message:
            return False
        lower = ctx.last_message.lower()
        return any(kw in lower for kw in self.SEMANTIC_KEYWORDS)

    def _detect_trigger(self, ctx: CompressionContext) -> CompressionTrigger:
        """Determine which trigger caused compression to fire.

        Semantic takes precedence over forced because the model-chosen
        boundary yields higher-quality compression.
        """
        if self._has_semantic_trigger(ctx):
            return CompressionTrigger.SEMANTIC
        return CompressionTrigger.FORCED

    @override
    def should_compress(self, ctx: CompressionContext) -> bool:
        """Dual-trigger: semantic boundary OR safety threshold.

        ``SEMANTIC`` — fires when the model's last response contains keywords
        indicating a natural sub-task boundary (e.g., "step completed").
        ``FORCED`` — fires every N steps or when consecutive errors exceed
        a threshold, acting as a safety net against unbounded context growth.
        """
        has_semantic = self._has_semantic_trigger(ctx)
        has_forced = (
            ctx.step_number - ctx.last_compression_step >= self._step_interval
            or ctx.consecutive_errors >= self._max_errors
        )
        return has_semantic or has_forced

    @override
    def compress(
        self,
        messages: list[LLMMessage],
        ctx: CompressionContext,
    ) -> tuple[list[LLMMessage], CompressionReport]:
        # 1. Find atomicity-safe cut point
        safe_cut = find_safe_cut(messages, self.TAIL_TARGET, self.MIN_HEAD)
        adjusted = safe_cut != len(messages) - self.TAIL_TARGET

        compressible = messages[self.MIN_HEAD : safe_cut]
        head = messages[: self.MIN_HEAD]
        tail = messages[safe_cut:]

        # 2. Build deterministic summary from compressible region
        summary_parts: list[str] = []
        lazy_refs: list[LazyRef] = []

        for msg in compressible:
            if msg.tool_result:
                tr = msg.tool_result
                label = "✓" if tr.success else "✗"
                detail = ""
                if tr.result:
                    if len(tr.result) > self.LARGE_OUTPUT_THRESHOLD:
                        ref = register_lazy_ref(tr.result)
                        lazy_refs.append(ref)
                        detail = f"[lazy-ref:{ref[:12]}] {_scrub_sensitive_data(tr.result)[:80]}..."
                    else:
                        detail = _scrub_sensitive_data(tr.result)[:120]
                elif tr.error:
                    detail = _scrub_sensitive_data(tr.error)[:120]
                if detail:
                    summary_parts.append(f"{label} {tr.name}: {detail}")
            elif msg.content and len(msg.content) > 20:
                lower = msg.content.lower()
                if any(
                    kw in lower
                    for kw in ("plan", "approach", "strategy", "fix", "change", "implement")
                ):
                    summary_parts.append(f"→ {msg.content[:200]}")

        summary_text = (
            "\n".join(summary_parts) if summary_parts else "(see last messages for context)"
        )

        # 3. Attach lazy-load references as a footnote
        if lazy_refs:
            ref_lines = "\n".join(
                f"  - {ref[:24]}...  ({len(ref)} bytes hashed)" for ref in lazy_refs
            )
            summary_text += f"\n\n**Lazy-loaded references (re-fetch on demand):**\n{ref_lines}"

        compressed: list[LLMMessage] = [
            head[0],  # system prompt
            LLMMessage(
                role="user",
                content=(
                    f"[Micro-Compression — before step {ctx.step_number}]:\n"
                    f"{summary_text}\n\n"
                    "The above is a compressed summary of earlier steps. "
                    "Continue working on the task."
                ),
            ),
            *tail,
        ]

        report = CompressionReport(
            trigger=self._detect_trigger(ctx),
            tokens_saved=_estimate_tokens_saved(compressible),
            messages_compressed=len(compressible),
            strategy_name="micro_compression",
            safe_cut_adjusted=adjusted,
        )

        return compressed, report


# ── Layer 2: Session compression (phase handoff) ──────────────────────────


class SessionCompressionStrategy(ContextCompressor):
    """Between-phase handoff compression.

    At the boundary between Planner → Coder or Coder → Reviewer, this
    strategy produces a structured ``SessionSummary`` with:

    - Key achievements (what got done).
    - Remaining issues (what's still open).
    - Design decisions made during the phase.
    - Trial paths (approaches tried and abandoned — critical for avoiding
      repeated dead-ends in the next phase).

    The summary becomes the root User message of the next phase, replacing
    the entire raw-message history.  This is the "fork" mechanism: the new
    phase starts from the summary, not from the raw transcript.
    """

    # Signals that a message contains a design decision worth recording
    _DECISION_SIGNALS = {"decision", "chose", "using", "adopt", "pattern", "architecture"}
    _TRIAL_SIGNALS = {"tried", "attempted", "didn't work", "failed", "error", "reverting"}

    @override
    def should_compress(self, ctx: CompressionContext) -> bool:
        """Session compression only fires at phase transitions.

        The orchestrator calls this with ``ctx.phase_name`` set to the
        **incoming** phase; we always return True because the caller
        already determined a transition is happening.
        """
        return True

    @override
    def compress(
        self,
        messages: list[LLMMessage],
        ctx: CompressionContext,
    ) -> tuple[list[LLMMessage], CompressionReport]:
        summary = self._build_summary(messages, ctx.phase_name)

        # The new root = [system prompt, user message with summary]
        # Preserve the system prompt from the original list
        system_prompt = (
            messages[0]
            if messages and messages[0].role == "system"
            else LLMMessage(role="system", content="")
        )

        compressed: list[LLMMessage] = [
            system_prompt,
            LLMMessage(
                role="user",
                content=(
                    f"[Session Handoff — {ctx.phase_name} phase completed]\n\n"
                    f"{summary.raw_summary}\n\n"
                    "The above summarises the previous phase's work. "
                    "Continue with your role's objective."
                ),
            ),
        ]

        report = CompressionReport(
            trigger=CompressionTrigger.PHASE_TRANSITION,
            tokens_saved=_estimate_tokens_saved(messages[1:]),  # everything except system prompt
            messages_compressed=len(messages) - 1,
            strategy_name="session_compression",
            safe_cut_adjusted=False,
        )

        return compressed, report

    def build_summary(self, messages: list[LLMMessage], phase_name: str) -> SessionSummary:
        """Public entry-point so the orchestrator can inspect the summary
        without calling ``compress()`` (e.g. to write it to GlobalStateManager)."""
        return self._build_summary(messages, phase_name)

    def _build_summary(self, messages: list[LLMMessage], phase_name: str) -> SessionSummary:
        summary = SessionSummary(phase=phase_name)

        for msg in messages:
            if msg.tool_result:
                tr = msg.tool_result
                if tr.success and tr.result:
                    # Heuristic: long successful outputs suggest real work
                    if len(tr.result) > 80:
                        summary.key_achievements.append(
                            f"{tr.name}: {_scrub_sensitive_data(tr.result)[:150]}"
                        )
                elif not tr.success and tr.error:
                    # Failed tools may indicate trial paths
                    summary.trial_paths.append(
                        f"{tr.name} error: {_scrub_sensitive_data(tr.error)[:150]}"
                    )
            elif msg.content:
                lower = msg.content.lower()
                if any(sig in lower for sig in self._DECISION_SIGNALS):
                    summary.design_decisions.append(msg.content[:200])
                if any(sig in lower for sig in self._TRIAL_SIGNALS):
                    summary.trial_paths.append(msg.content[:200])

        # Deduplicate and trim
        summary.key_achievements = _deduplicate(summary.key_achievements)
        summary.design_decisions = _deduplicate(summary.design_decisions)
        summary.trial_paths = _deduplicate(summary.trial_paths)

        # Build the raw text
        parts = [f"## {phase_name.title()} Phase Summary"]
        if summary.key_achievements:
            parts.append("### Key Achievements")
            parts.extend(f"- {a}" for a in summary.key_achievements[:5])
        if summary.remaining_issues:
            parts.append("### Remaining Issues")
            parts.extend(f"- {i}" for i in summary.remaining_issues[:3])
        if summary.design_decisions:
            parts.append("### Design Decisions")
            parts.extend(f"- {d}" for d in summary.design_decisions[:3])
        if summary.trial_paths:
            parts.append("### Trial Paths (avoided)")
            parts.extend(f"- {t}" for t in summary.trial_paths[:3])

        summary.raw_summary = "\n".join(parts)
        return summary


# ── Helpers ────────────────────────────────────────────────────────────────


def _estimate_tokens_saved(messages: list[LLMMessage]) -> int:
    """Rough heuristic: 1 token ≈ 4 characters."""
    total_chars = sum(len(msg.content or "") + len(str(msg.tool_result or "")) for msg in messages)
    return total_chars // 4


def _deduplicate(items: list[str]) -> list[str]:
    """Order-preserving deduplication by prefix similarity."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item[:80]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ── Sensitive data scrubber ──────────────────────────────────────────────────

# TODO: Replace these hardcoded patterns with a pluggable scrubber registry
# so downstream deployments can supply their own redaction rules (e.g. via
# env-var-based allow/deny lists, configurable regex sets, or remote
# detection services).

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # OpenAI / Anthropic API keys
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    # Bearer tokens (JWT, opaque tokens)
    re.compile(r"Bearer [A-Za-z0-9\-\._~+/]+"),
    # GitHub / GitLab personal access tokens
    re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}"),
    # Generic "secret" / "password" / "token" assignment in code context
    re.compile(r'(?i)(?:secret|password|token|api_key|apikey)\s*[:=]\s*["\']?\S{16,}'),
]


def _scrub_sensitive_data(text: str) -> str:
    """Redact common secret patterns from tool output before summarization.

    Operates on the truncated summary text only — the full original content
    remains available via lazy-ref re-fetch if needed.
    """
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    return text
