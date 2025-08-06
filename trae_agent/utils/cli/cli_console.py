# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Base CLI Console classes for Trae Agent."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from rich.panel import Panel
from rich.table import Table

from trae_agent.agent.agent_basics import AgentExecution, AgentStep, AgentStepState
from trae_agent.utils.config import LakeviewConfig
from trae_agent.utils.lake_view import LakeView


class ConsoleMode(Enum):
    """Console operation modes."""

    RUN = "run"  # Execute single task and exit
    INTERACTIVE = "interactive"  # Take multiple tasks from user input


class ConsoleType(Enum):
    """Available console types."""

    SIMPLE = "simple"  # Simple text-based console
    RICH = "rich"  # Rich textual-based console with TUI


AGENT_STATE_INFO = {
    AgentStepState.THINKING: ("blue", "🤔"),
    AgentStepState.CALLING_TOOL: ("yellow", "🔧"),
    AgentStepState.REFLECTING: ("magenta", "💭"),
    AgentStepState.COMPLETED: ("green", "✅"),
    AgentStepState.ERROR: ("red", "❌"),
}


@dataclass
class ConsoleStep:
    """Represents a console step with its display panel and lakeview information."""

    agent_step: AgentStep
    agent_step_printed: bool = False
    lake_view_panel_generator: asyncio.Task[Panel | None] | None = None


class CLIConsole(ABC):
    """Base class for CLI console implementations."""

    def __init__(
        self, mode: ConsoleMode = ConsoleMode.RUN, lakeview_config: LakeviewConfig | None = None
    ):
        """Initialize the CLI console.

        Args:
            config: Configuration object containing settings
            mode: Console operation mode (run or interactive)
        """
        self.mode: ConsoleMode = mode
        self.set_lakeview(lakeview_config)
        self.console_step_history: dict[int, ConsoleStep] = {}
        self.agent_execution: AgentExecution | None = None

    @abstractmethod
    async def start(self):
        """Start the console display. Should be implemented by subclasses."""
        pass

    @abstractmethod
    def update_status(
        self, agent_step: AgentStep | None = None, agent_execution: AgentExecution | None = None
    ):
        """Update the console with agent status.

        Args:
            agent_step: Current agent step information
            agent_execution: Complete agent execution information
        """
        pass

    @abstractmethod
    def print_task_details(self, details: dict[str, str]):
        """Print initial task configuration details."""
        pass

    @abstractmethod
    def print(self, message: str, color: str = "blue", bold: bool = False):
        """Print a message to the console."""
        pass

    @abstractmethod
    def get_task_input(self) -> str | None:
        """Get task input from user (for interactive mode).

        Returns:
            Task string or None if user wants to exit
        """
        pass

    @abstractmethod
    def get_working_dir_input(self) -> str:
        """Get working directory input from user (for interactive mode).

        Returns:
            Working directory path
        """
        pass

    @abstractmethod
    def stop(self):
        """Stop the console and cleanup resources."""
        pass

    def set_lakeview(self, lakeview_config: LakeviewConfig | None = None):
        """Set the lakeview configuration for the console."""
        if lakeview_config:
            self.lake_view: LakeView | None = LakeView(lakeview_config)
        else:
            self.lake_view = None


def generate_agent_step_table(agent_step: AgentStep) -> Table:
    """Log an agent step to the console."""
    color, emoji = AGENT_STATE_INFO.get(agent_step.state, ("white", "❓"))

    # Print the step state in a table
    table = Table(show_header=False, width=120)
    table.add_column("Step Number", style="cyan", width=15)
    table.add_column(f"{agent_step.step_number}", style="green", width=105)

    # Add status row
    table.add_row(
        "Status",
        f"[{color}]{emoji} Step {agent_step.step_number}: {agent_step.state.value.title()}[/{color}]",
    )

    # Add LLM response row
    if agent_step.llm_response and agent_step.llm_response.content:
        table.add_row("LLM Response", f"💬 {agent_step.llm_response.content}")

    # Add tool calls row
    if agent_step.tool_calls:
        tool_names = [f"[cyan]{call.name}[/cyan]" for call in agent_step.tool_calls]
        table.add_row("Tools", f"🔧 {', '.join(tool_names)}")

        for tool_call in agent_step.tool_calls:
            # Build a tool call table with tool name, arguments and result
            tool_call_table = Table(show_header=False, width=100)
            tool_call_table.add_column("Arguments", style="green", width=50)
            tool_call_table.add_column("Result", style="green", width=50)
            tool_result_str = ""
            for tool_result in agent_step.tool_results or []:
                if tool_result.call_id == tool_call.call_id:
                    tool_result_str = tool_result.result or ""
                    break
            tool_call_table.add_row(f"{tool_call.arguments}", f"{tool_result_str}")
            table.add_row(tool_call.name, tool_call_table)

    # Add reflection row
    if agent_step.reflection:
        table.add_row("Reflection", f"💭 {agent_step.reflection}")

    # Add error row
    if agent_step.error:
        table.add_row("Error", f"❌ {agent_step.error}")

    return table
