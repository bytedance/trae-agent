# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from enum import Enum

from ..tools.base import ToolCall, ToolResult
from ..utils.llm_basics import LLMResponse, LLMUsage


class AgentState(Enum):
    """Agent execution states."""

    IDLE = "idle"
    THINKING = "thinking"
    CALLING_TOOL = "calling_tool"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentStep:
    """Represents a single step in agent execution."""

    step_number: int
    state: AgentState
    thought: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None
    llm_response: LLMResponse | None = None
    reflection: str | None = None
    error: str | None = None
    extra: dict[str, object] | None = None
    llm_usage: LLMUsage | None = None


@dataclass
class AgentExecution:
    """Represents a complete agent execution."""

    task: str
    steps: list[AgentStep]
    final_result: str | None = None
    success: bool = False
    total_tokens: LLMUsage | None = None
    execution_time: float = 0.0


class AgentError(Exception):
    """Base class for agent errors."""

    def __init__(self, message: str):
        self.message: str = message
        super().__init__(self.message)
