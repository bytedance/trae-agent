# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OrchestratorAgent — multi-agent orchestration with PLANNING → CODING → REVIEW phases."""

import logging
import time
from enum import Enum
from typing import override

from trae_agent.agent.agent_basics import AgentExecution, AgentState, AgentStep, AgentStepState
from trae_agent.agent.base_agent import BaseAgent
from trae_agent.agent.trae_agent import TraeAgentToolNames
from trae_agent.compression.compressor import MicroCompressionStrategy
from trae_agent.compression.types import CompressionContext
from trae_agent.prompt.agent_prompt import (
    CODER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
)
from trae_agent.prompt.skills_registry import ProjectContext, SkillsRegistry
from trae_agent.tools import tools_registry
from trae_agent.tools.base import Tool, ToolExecutor
from trae_agent.utils.config import AgentConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class OrchestratorPhase(Enum):
    """Phases in the 3-stage orchestration workflow."""

    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"


# Tool permissions per phase (subset of TraeAgentToolNames)
PHASE_TOOL_NAMES: dict[OrchestratorPhase, set[str]] = {
    OrchestratorPhase.PLANNING: {
        "str_replace_based_edit_tool",
        "sequentialthinking",
        "resolve_lazy_ref",
    },
    OrchestratorPhase.CODING: set(TraeAgentToolNames),
    OrchestratorPhase.REVIEWING: {
        "str_replace_based_edit_tool",
        "bash",
        "sequentialthinking",
        "resolve_lazy_ref",
    },
}

# Max steps per phase (inner loop bound)
MAX_STEPS_PER_PHASE: int = 30


class OrchestratorAgent(BaseAgent):
    """Multi-agent orchestrator with isolated PLANNING → CODING → REVIEW phases.

    Each phase runs its own ReAct loop with fresh context.  The only data
    that flows across phases is a structured text handoff — no raw messages
    are shared.
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        docker_config: dict | None = None,
        docker_keep: bool = True,
    ):
        super().__init__(agent_config, docker_config, docker_keep)
        self._micro_compressor = MicroCompressionStrategy()
        self._skills_registry = SkillsRegistry()
        self._project_context: ProjectContext | None = None
        self._project_path: str = ""
        self._task: str = ""

    # ── Public API ────────────────────────────────────────────────────

    @override
    def new_task(
        self,
        task: str,
        extra_args: dict[str, str] | None = None,
        tool_names: list[str] | None = None,
    ):
        """Create a new task for the orchestrator."""
        self._task = task

        if tool_names is None:
            # Build all available tools — per-phase filtering happens at runtime
            provider = self._model_config.model_provider.provider
            self._tools = [
                tools_registry[name](model_provider=provider) for name in TraeAgentToolNames
            ]

        self._initial_messages = []
        self._initial_messages.append(LLMMessage(role="system", content=self.get_system_prompt()))

        user_message = ""
        if extra_args:
            if "project_path" in extra_args:
                self._project_path = extra_args["project_path"]
                self._project_context = self._skills_registry.detect(self._project_path)
                user_message += f"[Project root path]:\n{self._project_path}\n\n"
            if "issue" in extra_args:
                user_message += (
                    f"[Problem statement]: We are currently solving the following "
                    f"issue within our repository.\n{extra_args['issue']}\n"
                )
        else:
            user_message += task

        if user_message:
            self._initial_messages.append(LLMMessage(role="user", content=user_message))

    @override
    async def execute_task(self) -> AgentExecution:
        """Execute the task through all three phases."""
        start_time = time.time()

        execution = AgentExecution(task=self._task, steps=[])
        execution.agent_state = AgentState.RUNNING

        # ── Phase 1: Planning ──────────────────────────────────────
        plan = await self._run_phase(
            phase=OrchestratorPhase.PLANNING,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            handoff_context=self._build_initial_context(),
            execution=execution,
        )

        # ── Phase 2: Coding ─────────────────────────────────────────
        code_result = await self._run_phase(
            phase=OrchestratorPhase.CODING,
            system_prompt=CODER_SYSTEM_PROMPT,
            handoff_context=self._build_coding_context(plan),
            execution=execution,
        )

        # ── Phase 3: Review ─────────────────────────────────────────
        review_result = await self._run_phase(
            phase=OrchestratorPhase.REVIEWING,
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            handoff_context=self._build_review_context(code_result),
            execution=execution,
        )

        execution.final_result = (
            f"## Plan\n{plan}\n\n## Result\n{code_result}\n\n## Review\n{review_result}"
        )
        execution.success = True
        execution.agent_state = AgentState.COMPLETED
        execution.execution_time = time.time() - start_time

        return execution

    # ── Phase runner ──────────────────────────────────────────────────

    async def _run_phase(
        self,
        phase: OrchestratorPhase,
        system_prompt: str,
        handoff_context: str,
        execution: AgentExecution,
    ) -> str:
        """Run a single phase with isolated context and per-phase tools."""
        phase_tools = self._build_phase_tools(phase)
        phase_executor = ToolExecutor(phase_tools)

        # Start with a fresh message list for this phase
        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=handoff_context),
        ]

        step_number = 1
        last_compression_step = 0
        last_assistant_message: str | None = None
        consecutive_errors = 0
        pre_phase_step_count = len(execution.steps)  # C4: track step offset for reviewer bash check

        while step_number <= MAX_STEPS_PER_PHASE:
            # ── Micro-compression check (before every LLM call) ──────
            ctx = CompressionContext(
                step_number=step_number,
                message_count=len(messages),
                consecutive_errors=consecutive_errors,
                phase_name=phase.value,
                last_compression_step=last_compression_step,
                last_message=last_assistant_message,
            )

            if self._micro_compressor.should_compress(ctx):
                messages, report = self._micro_compressor.compress(messages, ctx)
                logger.info(
                    "Compression triggered: %s, tokens_saved=%d, strategy=%s, step=%d",
                    report.trigger.value,
                    report.tokens_saved,
                    report.strategy_name,
                    step_number,
                )
                self._reset_llm_client_history()
                last_compression_step = step_number

            step = AgentStep(step_number=step_number, state=AgentStepState(phase.value))
            self._update_cli_console(step, execution)

            try:
                llm_response = self._llm_client.chat(messages, self._model_config, phase_tools)
            except Exception as e:
                step.state = AgentStepState.ERROR
                execution.steps.append(step)
                return f"[{phase.value.title()} phase error: {e}]"

            step.llm_response = llm_response
            self._update_cli_console(step, execution)

            # Capture last assistant text for next compression check
            last_assistant_message = llm_response.content or None

            # Check for phase completion
            if self._phase_complete(phase, llm_response):
                # C4: Reviewer must have run bash before verdict
                if phase == OrchestratorPhase.REVIEWING and not self._reviewer_executed_bash(
                    execution, pre_phase_step_count
                ):
                    reminder = (
                        "You have not executed any CI commands. Before providing your verdict, "
                        "you MUST call `bash` to run the test suite, lint, and type checks. "
                        "Execute them now."
                    )
                    messages.append(LLMMessage(role="user", content=reminder))
                    consecutive_errors = 0
                    step_number += 1
                    continue
                self._record_handler(step, messages)
                self._update_cli_console(step, execution)
                execution.steps.append(step)
                return llm_response.content

            # Handle tool calls
            tool_calls = llm_response.tool_calls
            if tool_calls:
                step.state = AgentStepState.CALLING_TOOL
                step.tool_calls = tool_calls
                self._update_cli_console(step, execution)

                tool_results = await phase_executor.sequential_tool_call(tool_calls)
                step.tool_results = tool_results
                self._update_cli_console(step, execution)

                # Track consecutive errors for forced compression trigger
                has_error = any(not tr.success for tr in tool_results)
                consecutive_errors = consecutive_errors + 1 if has_error else 0

                for tr in tool_results:
                    messages.append(LLMMessage(role="user", tool_result=tr))

                step.state = AgentStepState.COMPLETED
                self._record_handler(step, messages)
                self._update_cli_console(step, execution)
                execution.steps.append(step)
            else:
                # LLM thinking without tool calls — capture response and continue
                if llm_response.content:
                    messages.append(LLMMessage(role="assistant", content=llm_response.content))
                consecutive_errors = 0
                step.state = AgentStepState.COMPLETED
                self._record_handler(step, messages)
                self._update_cli_console(step, execution)
                execution.steps.append(step)

            step_number += 1

        # Phase exceeded max steps — return whatever we have
        return f"[{phase.value.title()} phase exceeded max steps, continuing with partial result]"

    # ── Phase detection ───────────────────────────────────────────────

    @staticmethod
    def _reviewer_executed_bash(execution: AgentExecution, pre_phase_step_count: int) -> bool:
        """Check whether the reviewer actually called ``bash`` during the current phase.

        Returns ``False`` if the reviewer tries to emit a verdict without having
        executed any CI commands — used to enforce the C4 "steel discipline" rule.
        """
        reviewing_steps = execution.steps[pre_phase_step_count:]
        for step in reviewing_steps:
            if step.tool_calls and any(tc.name == "bash" for tc in step.tool_calls):
                return True
        return False

    def _phase_complete(self, phase: OrchestratorPhase, response: LLMResponse) -> bool:
        """Check whether the current phase has signalled completion."""
        content = (response.content or "").lower()

        match phase:
            case OrchestratorPhase.PLANNING:
                return (
                    "plan completed" in content
                    and "</plan_details>" in content
                    and "</plan_approach>" in content
                )
            case OrchestratorPhase.CODING:
                if response.tool_calls:
                    return any(tc.name == "task_done" for tc in response.tool_calls)
                return False
            case OrchestratorPhase.REVIEWING:
                return (
                    "**pass**" in content
                    or "**fail**" in content
                    or "## review verdict" in content
                    or "<review_verdict>" in content
                )

    # ── Context builders (phase handoff) ──────────────────────────────

    def _build_initial_context(self) -> str:
        """Build the handoff context for the Planning phase."""
        parts: list[str] = ["## Task"]
        parts.append(self._task)

        if self._project_path:
            parts.append(f"\n## Project Root\n{self._project_path}")

        arch = self._skills_registry.build_architecture_prompt(self._project_context)
        if arch:
            parts.append(f"\n{arch}")

        return "\n".join(parts)

    def _build_coding_context(self, plan: str) -> str:
        """Build the handoff context for the Coding phase."""
        arch = self._skills_registry.build_architecture_prompt(self._project_context)
        arch_section = f"\n{arch}\n" if arch else ""
        return (
            f"## Task\n{self._task}\n\n"
            f"## Plan from Planner\n{plan}\n\n"
            f"{arch_section}"
            "Please implement the plan above. Execute the steps methodically, "
            "write tests, and verify the fix. Call `task_done` when finished."
        )

    def _build_review_context(self, code_result: str) -> str:
        """Build the handoff context for the Review phase."""
        arch = self._skills_registry.build_architecture_prompt(self._project_context)
        arch_section = f"\n{arch}\n" if arch else ""
        return (
            f"## Task\n{self._task}\n\n"
            f"## Changes Made\n{code_result}\n\n"
            f"{arch_section}"
            "Please review the changes above. Check for correctness, regressions, "
            "edge cases, and code quality. Provide a clear verdict."
        )

    # ── Tool helpers ──────────────────────────────────────────────────

    def _build_phase_tools(self, phase: OrchestratorPhase) -> list[Tool]:
        """Build the tool list restricted to the current phase."""
        allowed_names = PHASE_TOOL_NAMES[phase]
        return [tool for tool in self._tools if tool.get_name() in allowed_names]

    # ─── System prompt ────────────────────────────────────────────────

    def get_system_prompt(self) -> str:
        """Return the base system prompt for the orchestrator."""
        return (
            "You are an expert AI software engineering orchestrator. "
            "You will be guided through multiple phases — planning, coding, and review. "
            "Each phase has specific goals and tool access."
        )

    # ── Unused overrides ──────────────────────────────────────────────

    @override
    async def cleanup_mcp_clients(self) -> None:
        pass
