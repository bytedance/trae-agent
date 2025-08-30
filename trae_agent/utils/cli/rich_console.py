# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Rich CLI Console implementation using Textual TUI."""

import asyncio
import os
from typing import override

from rich.panel import Panel
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Header, Input, RichLog, Static

from trae_agent.agent.agent_basics import AgentExecution, AgentStep, AgentStepState
from trae_agent.utils.cli.cli_console import (
    AGENT_STATE_INFO,
    CLIConsole,
    ConsoleMode,
    ConsoleStep,
    generate_agent_step_table,
)
from trae_agent.utils.config import LakeviewConfig


class TokenDisplay(Static):
    """Widget to display real-time token usage."""

    total_tokens: reactive[int] = reactive(0)
    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)

    @override
    def render(self) -> Text:
        """Render the token display."""
        if self.total_tokens > 0:
            return Text(
                f"Tokens: {self.total_tokens:,} total | "
                + f"Input: {self.input_tokens:,} | "
                + f"Output: {self.output_tokens:,}",
                style="bold blue",
            )
        return Text("Tokens: 0 total", style="dim")

    def update_tokens(self, agent_execution: AgentExecution):
        """Update token counts from agent execution."""
        if agent_execution and agent_execution.total_tokens:
            self.input_tokens = agent_execution.total_tokens.input_tokens
            self.output_tokens = agent_execution.total_tokens.output_tokens
            self.total_tokens = self.input_tokens + self.output_tokens


class RichConsoleApp(App[None]):
    """Textual app for the rich console."""

    CSS_PATH = "rich_console.tcss"

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, console_impl: "RichCLIConsole"):
        super().__init__()
        self.console_impl: "RichCLIConsole" = console_impl
        self.execution_log: RichLog | None = None
        self.task_input: Input | None = None
        self.task_display: Static | None = None
        self.token_display: TokenDisplay | None = None
        self.current_task: str | None = None
        self.is_running_task: bool = False

        self.options: list[str] = ["help", "exit", "status", "clear"]

    @override
    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header(show_clock=True)

        # Top container for agent execution
        with Container(id="execution_container"):
            yield RichLog(id="execution_log", wrap=True, markup=True)

        # Bottom container for input/task display
        with Container(id="input_container"):
            if self.console_impl.mode == ConsoleMode.INTERACTIVE:
                yield Input(
                    placeholder="Enter your task...",
                    id="task_input",
                    suggester=SuggestFromList(self.options, case_sensitive=True),
                )
                yield Static("", id="task_display", classes="task_display")
            else:
                yield Static("", id="task_display", classes="task_display")

        # Footer container for token usage
        with Container(id="footer_container"):
            yield TokenDisplay(id="token_display")

        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.title = "Trae Agent CLI"

        self.execution_log = self.query_one("#execution_log", RichLog)
        self.token_display = self.query_one("#token_display", TokenDisplay)
        self.task_display = self.query_one("#task_display", Static)

        if self.console_impl.mode == ConsoleMode.INTERACTIVE:
            self.task_input = self.query_one("#task_input", Input)
            _ = self.task_input.focus()

        # Show initial task in RUN mode
        if self.console_impl.mode == ConsoleMode.RUN and self.console_impl.initial_task:
            self.task_display.update(
                Panel(self.console_impl.initial_task, title="Task", border_style="blue")
            )

    @on(Input.Submitted, "#task_input")
    def handle_task_input(self, event: Input.Submitted) -> None:
        """Handle task input submission in interactive mode."""
        if self.is_running_task:
            return

        task = event.value.strip()
        if not task:
            return

        handlers: dict = {
            "exit": self._exit_handler,
            "quit": self._exit_handler,
            "help": self._help_handler,
            "clear": self._clear_handler,
            "status": self._status_handler,
        }

        handler = handlers.get(task.lower())
        if handler:
            handler(event) if task.lower() not in ["exit", "quit"] else handler()
            return

        # Execute the task
        self.current_task = task
        if self.task_display:
            _ = self.task_display.update(Panel(task, title="Current Task", border_style="green"))
        event.input.value = ""
        self.is_running_task = True

        # Start task execution
        _ = asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: str):
        """Execute a task using the agent."""
        try:
            if not hasattr(self.console_impl, "agent") or not self.console_impl.agent:
                if self.execution_log:
                    _ = self.execution_log.write("[red]Error: Agent not available[/red]")
                return

            # Get working directory
            working_dir = os.getcwd()
            if self.console_impl.mode == ConsoleMode.INTERACTIVE:
                # For interactive mode, we might want to ask for working directory
                # For now, use current directory
                pass

            task_args = {
                "project_path": working_dir,
                "issue": task,
                "must_patch": "false",
            }

            if self.execution_log:
                _ = self.execution_log.write(f"[blue]Executing task: {task}[/blue]")

            # Execute the task
            _ = await self.console_impl.agent.run(task, task_args)

            if self.execution_log:
                _ = self.execution_log.write("[green]Task completed successfully![/green]")

        except Exception as e:
            if self.execution_log:
                _ = self.execution_log.write(f"[red]Error executing task: {e}[/red]")
        finally:
            self.is_running_task = False
            if self.console_impl.mode == ConsoleMode.RUN:
                # In run mode, exit after task completion
                await asyncio.sleep(1)  # Brief pause to show completion
                _ = self.exit()
            else:
                # In interactive mode, clear task display and re-enable input
                if self.task_display:
                    _ = self.task_display.update("")
                if self.task_input:
                    _ = self.task_input.focus()

    def log_agent_step(self, agent_step: AgentStep):
        """Log an agent step to the execution log."""
        color, _ = AGENT_STATE_INFO.get(agent_step.state, ("white", "❓"))

        # Create step display
        step_content = generate_agent_step_table(agent_step)

        if self.execution_log:
            _ = self.execution_log.write(
                Panel(step_content, title=f"Step {agent_step.step_number}", border_style=color)
            )

    def _help_handler(self, event: Input.Submitted):
        if self.execution_log:
            self.execution_log.write(
                Panel(
                    """[bold]Available Commands:[/bold]

• Type any task description to execute it
• 'status' - Show agent status
• 'clear' - Clear the execution log
• 'exit' or 'quit' - End the session""",
                    title="Help",
                    border_style="yellow",
                )
            )
        event.input.value = ""

    def _clear_handler(self, event: Input.Submitted):
        if self.execution_log:
            _ = self.execution_log.clear()
        event.input.value = ""

    def _status_handler(self, event: Input.Submitted):
        if hasattr(self.console_impl, "agent") and self.console_impl.agent:
            agent_info = getattr(self.console_impl.agent, "agent_config", None)
            if agent_info and self.execution_log:
                _ = self.execution_log.write(
                    Panel(
                        f"""[bold]Provider:[/bold] {agent_info.model.model_provider.provider}
[bold]Model:[/bold] {agent_info.model.model}
[bold]Working Directory:[/bold] {os.getcwd()}""",
                        title="Agent Status",
                        border_style="blue",
                    )
                )
        else:
            if self.execution_log:
                _ = self.execution_log.write("[yellow]Agent not initialized[/yellow]")
        event.input.value = ""

    def _exit_handler(self):
        self.exit()

    async def action_quit(self) -> None:
        """Quit the application."""
        self.console_impl.should_exit = True
        _ = self.exit()


class RichCLIConsole(CLIConsole):
    """Rich CLI console using Textual for TUI interface."""

    def __init__(
        self, mode: ConsoleMode = ConsoleMode.RUN, lakeview_config: LakeviewConfig | None = None
    ):
        """Initialize the rich CLI console."""
        super().__init__(mode, lakeview_config)
        self.app: RichConsoleApp | None = None
        self.should_exit: bool = False
        self.initial_task: str | None = None
        self._is_running: bool = False

        # Agent context for interactive mode
        self.agent = None
        self.trae_agent_config = None
        self.config_file = None
        self.trajectory_file = None

    @override
    async def start(self):
        """Start the rich console application."""
        # Prevent multiple starts of the same app
        if self._is_running:
            return

        self._is_running = True

        try:
            if self.app is None:
                self.app = RichConsoleApp(self)

            # Run the textual app
            await self.app.run_async()
        finally:
            self._is_running = False

    @override
    def update_status(
        self, agent_step: AgentStep | None = None, agent_execution: AgentExecution | None = None
    ):
        """Update the console with agent status."""
        if agent_step and self.app:
            if agent_step.step_number not in self.console_step_history:
                # update step history
                self.console_step_history[agent_step.step_number] = ConsoleStep(agent_step)

            if (
                agent_step.state in [AgentStepState.COMPLETED, AgentStepState.ERROR]
                and not self.console_step_history[agent_step.step_number].agent_step_printed
            ):
                self.app.log_agent_step(agent_step)
                self.console_step_history[agent_step.step_number].agent_step_printed = True

        if agent_execution:
            self.agent_execution = agent_execution
            if self.app and self.app.token_display:
                self.app.token_display.update_tokens(agent_execution)

    @override
    def print_task_details(self, details: dict[str, str]):
        """Print initial task configuration details."""
        if self.app and self.app.execution_log:
            content = "\n".join([f"[bold]{key}:[/bold] {value}" for key, value in details.items()])
            _ = self.app.execution_log.write(
                Panel(content, title="Task Details", border_style="blue")
            )

    @override
    def print(self, message: str, color: str = "blue", bold: bool = False):
        """Print a message to the console."""
        if self.app and self.app.execution_log:
            formatted_message = f"[bold]{message}[/bold]" if bold else message
            formatted_message = f"[{color}]{formatted_message}[/{color}]"
            _ = self.app.execution_log.write(formatted_message)

    @override
    def get_task_input(self) -> str | None:
        """Get task input from user (for interactive mode)."""
        # This method is not used in rich console as input is handled by the TUI
        return None

    @override
    def get_working_dir_input(self) -> str:
        """Get working directory input from user (for interactive mode)."""
        # For now, return current directory. Could be enhanced with a dialog
        return os.getcwd()

    @override
    def stop(self):
        """Stop the console and cleanup resources."""
        self.should_exit = True
        if self.app:
            _ = self.app.exit()

    def set_agent_context(self, agent, trae_agent_config, config_file, trajectory_file) -> None:
        """Set the agent context for task execution in interactive mode."""
        self.agent = agent
        self.trae_agent_config = trae_agent_config
        self.config_file = config_file
        self.trajectory_file = trajectory_file

    def set_initial_task(self, task: str):
        """Set the initial task for RUN mode."""
        self.initial_task = task
