# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Brief integration sketch — Orchestrator using GlobalStateManager + ContextCompressor.

This is NOT a complete implementation.  It shows the wiring between the
existing ``OrchestratorAgent._run_phase()`` and the new compression layer.
"""

from trae_agent.agent.agent_basics import AgentExecution
from trae_agent.agent.orchestrator_agent import MAX_STEPS_PER_PHASE, OrchestratorPhase
from trae_agent.compression.compressor import (
    ContextCompressor,
    MicroCompressionStrategy,
    SessionCompressionStrategy,
)
from trae_agent.compression.global_state import GlobalStateManager
from trae_agent.compression.types import CompressionContext
from trae_agent.tools.base import Tool
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


class HybridOrchestrator:
    """Rough sketch of the 3x3 grid Orchestrator integration.

    Compare with the current ``OrchestratorAgent._run_phase()`` at
    ``trae_agent/agent/orchestrator_agent.py:149``.

    Key differences:
    - ``GlobalStateManager`` persists across all three phases.
    - ``MicroCompressionStrategy`` runs *inside* each ReAct loop.
    - ``SessionCompressionStrategy`` replaces the raw text handoff.
    """

    def __init__(self, global_state: GlobalStateManager) -> None:
        self._global_state = global_state

        # Layer 1 strategies — one per phase (each phase has different
        # compression sensitivity).
        self._micro_strategies: dict[str, ContextCompressor] = {
            "planning": MicroCompressionStrategy(
                step_interval=15,  # Planner loops tend to be short, compress less
                max_errors=3,
            ),
            "coding": MicroCompressionStrategy(
                step_interval=10,  # Coder has long ReAct loops, compress more
                max_errors=3,
            ),
            "reviewing": MicroCompressionStrategy(
                step_interval=12,
                max_errors=2,  # Reviewer errors are more suspicious
            ),
        }

        # Layer 2 strategy — shared across all phase transitions
        self._session_compressor = SessionCompressionStrategy()

    # ── Phase runner (abridged) ────────────────────────────────────────

    async def run_phase(
        self,
        phase: OrchestratorPhase,
        system_prompt: str,
        messages: list[LLMMessage],
        phase_tools: list[Tool],
        execution: AgentExecution,
    ) -> str:
        """Run a single phase with micro-compression inside the loop."""
        micro = self._micro_strategies[phase.value]
        last_compression_step = 0
        step_number = 1

        while step_number <= MAX_STEPS_PER_PHASE:
            # ── Micro-compression check (before every LLM call) ──────
            ctx = CompressionContext(
                step_number=step_number,
                message_count=len(messages),
                consecutive_errors=self._count_consecutive_errors(execution),
                phase_name=phase.value,
                last_compression_step=last_compression_step,
            )

            if micro.should_compress(ctx):
                messages, report = micro.compress(messages, ctx)
                last_compression_step = step_number

            # ── LLM call (unchanged from current TraeAgent logic) ──────
            # llm_response = self._llm_client.chat(messages, model_config, phase_tools)
            # ... tool execution, response handling (same as OrchestratorAgent._run_phase) ...
            _ = step_number  # placeholder for the real loop body
            step_number += 1

        return "(phase output placeholder)"

    # ── Phase transition (session compression) ─────────────────────────

    async def transition_to(
        self,
        next_phase: OrchestratorPhase,
        messages: list[LLMMessage],
    ) -> list[LLMMessage]:
        """Compress the outgoing phase into a session summary and fork context."""

        # 1. Run session compression → structured summary
        ctx = CompressionContext(
            step_number=0,
            message_count=len(messages),
            consecutive_errors=0,
            phase_name=next_phase.value,
        )
        new_messages, report = self._session_compressor.compress(messages, ctx)

        # 2. Write key findings to GlobalStateManager
        summary = self._session_compressor.build_summary(messages, next_phase.value)
        # (Phase-specific write logic—sketch only)
        if next_phase == OrchestratorPhase.CODING:
            self._global_state.log_progress(
                f"Planner handoff: {len(summary.key_achievements)} analyses completed",
                phase=next_phase.value,
            )
        elif next_phase == OrchestratorPhase.REVIEWING:
            self._global_state.log_progress(
                f"Coder handoff: {len(summary.key_achievements)} achievements",
                phase=next_phase.value,
            )

        return new_messages

    # ── Helpers ────────────────────────────────────────────────────────

    def _count_consecutive_errors(self, execution: AgentExecution) -> int:
        count = 0
        for step in reversed(execution.steps):
            if step.error:
                count += 1
            else:
                break
        return count

    # Placeholder to indicate this is a sketch
    _llm_client = None  # type: ignore[assignment]
    model_config = None  # type: ignore[assignment]
