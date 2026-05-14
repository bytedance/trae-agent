# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Shared types for all three compression layers."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

from trae_agent.utils.llm_clients.llm_basics import LLMMessage

# ── Compression triggers ───────────────────────────────────────────────────


class CompressionTrigger(Enum):
    """What triggered a compression operation."""

    SEMANTIC = "semantic"  # Model-detected natural boundary (e.g., "step completed")
    FORCED = "forced"  # Safety threshold exceeded (steps / error count)
    PHASE_TRANSITION = "phase_transition"  # Handoff between Planner/Coder/Reviewer
    MANUAL = "manual"  # Explicitly requested by agent code


# ── Micro-compression context ─────────────────────────────────────────────


@dataclass
class CompressionContext:
    """Snapshot of loop state used by compressors to decide *whether* to act.

    Passed into the compressor at every ReAct iteration so it can evaluate
    triggers without coupling to the full message list.
    """

    step_number: int
    message_count: int
    consecutive_errors: int
    phase_name: str
    last_message: str | None = None
    last_compression_step: int = 0


# ── Compression report (returned alongside the compressed message list) ────


@dataclass
class CompressionReport:
    """Diagnostic output from a compression operation.

    Records what happened so the orchestrator can log, trace, and learn
    from compression behaviour.
    """

    trigger: CompressionTrigger
    tokens_saved: int
    messages_compressed: int
    strategy_name: str
    safe_cut_adjusted: bool  # True if cut was shifted to protect tool_call pairs


# ── Session-level handoff summary ─────────────────────────────────────────


@dataclass
class SessionSummary:
    """Structured output of a between-phase session compression.

    Replaces the current raw-text handoff with a semantically organised
    digest that becomes the root context of the next phase.
    """

    phase: str
    key_achievements: list[str] = field(default_factory=list)
    remaining_issues: list[str] = field(default_factory=list)
    design_decisions: list[str] = field(default_factory=list)
    trial_paths: list[str] = field(default_factory=list)
    raw_summary: str = ""


# ── Lazy-load reference ───────────────────────────────────────────────────


LazyRef: TypeAlias = str
"""A placeholder like ``[lazy-ref:<hash>]`` that can be rehydrated on demand.

Used by micro-compression to defer large tool outputs (file views, grep
results) until the model actually references them, keeping the active
message window lean.  Call ``resolve_lazy_ref`` with the hash to retrieve
the full content.
"""


def find_safe_cut(
    messages: list[LLMMessage],
    tail_target: int,
    min_head: int,
) -> int:
    """Walk backward from the tentative cut to find a boundary that never
    splits a ``tool_call`` / ``tool_result`` atomic pair.

    **Defence-in-depth (Approach B from PR review 2.2):** we skip *both*
    ``tool_result`` and ``tool_call`` messages when searching for the cut
    point, so the tail never starts in the middle of an atomic pair.
    Combined with Approach A (adding assistant messages with tool_calls
    to the message list), this guarantees provider-level correctness.

    Args:
        messages: Full conversation so far.
        tail_target: Desired number of messages to keep as working set.
        min_head: Minimum messages to preserve from the front (system prompt etc.).

    Returns:
        The safe cut index (inclusive start of tail), guaranteed to
        not land on a ``tool_result`` or ``tool_call`` message.
        Minimum return value is ``min_head``.
    """
    cut = len(messages) - tail_target
    while cut > min_head:
        msg = messages[cut]
        if msg.tool_result is not None:
            cut -= 1
            continue
        if msg.tool_call is not None:
            cut -= 1
            continue
        break
    return max(cut, min_head)
