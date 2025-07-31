# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
from dataclasses import dataclass

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from trae_agent.agent.agent_basics import AgentExecution, AgentState, AgentStep
from trae_agent.utils.config import Config, LakeviewConfig, TraeAgentConfig
from trae_agent.utils.lake_view import LakeView

AGENT_STATE_INFO = {
    AgentState.THINKING: ("blue", "🤔"),
    AgentState.CALLING_TOOL: ("yellow", "🔧"),
    AgentState.REFLECTING: ("magenta", "💭"),
    AgentState.COMPLETED: ("green", "✅"),
    AgentState.ERROR: ("red", "❌"),
    AgentState.IDLE: ("white", "⏸️"),
}


@dataclass
class ConsoleStep:
    panel: Panel
    lake_view_panel_generator: asyncio.Task[Panel | None] | None = None
    lake_view_generator_done: bool = False


class CLIConsole:
    """Console for displaying agent progress."""

    def __init__(self, config: Config | None):
        """Initialize the CLI console. Enable lakeview if config is provided and enable_lakeview is True."""
        self.console: Console = Console()
        self.live_display: Live | None = None
        self.config: Config | None = config
        self.trae_agent_config: TraeAgentConfig | None = config.trae_agent if config else None
        self.console_steps: dict[int, ConsoleStep] = {}
        self.lakeview_config: LakeviewConfig | None = config.lakeview if config else None
        self.lake_view: LakeView | None = (
            LakeView(self.lakeview_config) if self.lakeview_config else None
        )

        self.agent_step_history: list[AgentStep] = []
        self.agent_execution: AgentExecution | None = None

    def update_status(
        self,
        agent_step: AgentStep | None = None,
        agent_execution: AgentExecution | None = None,
    ):
        if agent_step:
            if len(self.agent_step_history) > 0:
                if agent_step.step_number > self.agent_step_history[-1].step_number:
                    self.agent_step_history.append(agent_step)
            else:
                self.agent_step_history.append(agent_step)

        self.agent_execution = agent_execution

    async def start(self):
        while True:
            if self.agent_execution and (
                self.lake_view is None
                or (
                    len(self.agent_execution.steps) == len(self.console_steps)
                    and all(step.lake_view_generator_done for step in self.console_steps.values())
                )
            ):
                break
            self.print_task_progress()
            await asyncio.sleep(3)

        self.print_task_progress()
        if self.live_display is not None:
            self.live_display.stop()
            self.live_display = None

    def print_task_details(
        self,
        task: str,
        working_dir: str,
        provider: str,
        model: str,
        max_steps: int,
        config_file: str,
        trajectory_file: str,
    ):
        self.console.print(
            Panel(
                f"""[bold]Task:[/bold] {task}
[bold]Working Directory:[/bold] {working_dir}
[bold]Provider:[/bold] {provider}
[bold]Model:[/bold] {model}
[bold]Max Steps:[/bold] {max_steps}
[bold]Config File:[/bold] {config_file}
[bold]Trajectory File:[/bold] {trajectory_file}""",
                title="Task Details",
                border_style="blue",
            )
        )

    def print(self, message: str, color: str = "blue", bold: bool = False):
        message = f"[bold]{message}[/bold]" if bold else message
        message = f"[{color}]{message}[/{color}]"
        self.console.print(message)

    def _create_compact_step_display(self, agent_step: AgentStep):
        step_content: list[str] = []
        color, emoji = AGENT_STATE_INFO.get(agent_step.state, ("white", "❓"))
        step_content.append(
            f"[{color}]{emoji} Step {agent_step.step_number}: {agent_step.state.value.title()}[/{color}]"
        )

        # Show brief LLM response if available
        if agent_step.llm_response and agent_step.llm_response.content:
            content = agent_step.llm_response.content
            if len(content) > 50:
                content = content[:47] + "..."
            step_content.append(f"💬 {content}")

        # Show tool summary
        if agent_step.tool_calls:
            tool_names = [f"[cyan]{call.name}[/cyan]" for call in agent_step.tool_calls]
            step_content.append(f"🔧 Tools: {', '.join(tool_names)}")

            # Show tool execution status
            if agent_step.tool_results:
                success_count = sum(1 for r in agent_step.tool_results if r.success)
                total_count = len(agent_step.tool_results)
                status = (
                    "[green]✅"
                    if success_count == total_count
                    else f"[yellow]⚠️ {success_count}/{total_count}[/yellow]"
                )
                step_content.append(f"Status: {status}")

        return Panel(
            "\n".join(step_content),
            title=f"Step {agent_step.step_number}",
            border_style=color,
            width=80,
        )

    async def _create_lakeview_step_display(self, agent_step: AgentStep) -> Panel | None:
        if self.lake_view is None:
            return None

        lake_view_step = await self.lake_view.create_lakeview_step(agent_step)

        if lake_view_step is None:
            return None

        color, _ = AGENT_STATE_INFO.get(agent_step.state, ("white", "❓"))

        return Panel(
            f"""[{lake_view_step.tags_emoji}] The agent [bold]{lake_view_step.desc_task}[/bold]
{lake_view_step.desc_details}""",
            title=f"Step {agent_step.step_number} (Lakeview)",
            border_style=color,
            width=80,
        )

    def _create_step_display(self, agent_step: AgentStep) -> Panel:
        """Create a panel for displaying the current step."""

        color, emoji = AGENT_STATE_INFO.get(agent_step.state, ("white", "❓"))

        # Build progressive step content
        step_content: list[str] = []
        step_content.append(f"[{color}]{emoji} State: {agent_step.state.value.title()}[/{color}]")

        # Show LLM response if available (truncated for readability)
        if agent_step.llm_response and agent_step.llm_response.content:
            step_content.append(
                f"\n[bold]💬 LLM Response:[/bold]\n{agent_step.llm_response.content}"
            )

        # Show tool calls
        if agent_step.tool_calls:
            step_content.append("\n[bold]🔧 Tool Calls:[/bold]")
            for i, tool_call in enumerate(agent_step.tool_calls):
                step_content.append(f"  {i + 1}. [cyan]{tool_call.name}[/cyan]")
                if tool_call.arguments:
                    step_content.append(f"     Args: {tool_call.arguments}")

        # Show tool results
        if agent_step.tool_calls and agent_step.tool_results:
            step_content.append("\n[bold]📋 Tool Results:[/bold]")
            for i, result in enumerate(agent_step.tool_results):
                status = "[green]✅ Success[/green]" if result.success else "[red]❌ Failed[/red]"
                step_content.append(f"  {i + 1}. {status}")
                if result.error:
                    step_content.append(f"     [red]Error:[/red] {result.error}")
                elif result.result:
                    step_content.append(f"     [green]Output:[/green] {result.result}")

        # Show reflection
        if agent_step.reflection:
            step_content.append(f"\n[bold]💭 Reflection:[/bold]\n{agent_step.reflection}")

        # Show error
        if agent_step.error:
            step_content.append(f"\n[red]❌ Error:[/red] {agent_step.error}")

        return Panel(
            "\n".join(step_content),
            title=f"Step {agent_step.step_number}",
            border_style=color,
            width=80,
        )

    def create_agent_steps_display(self) -> Group:
        panels: list[Panel] = []
        if self.agent_execution is None:
            previous_steps = (
                self.agent_step_history[:-1] if len(self.agent_step_history) >= 2 else []
            )
            current_step = self.agent_step_history[-1] if len(self.agent_step_history) > 0 else None
        else:
            previous_steps = self.agent_step_history
            current_step = None
        if len(previous_steps) > 0:
            for step in previous_steps:
                step_id = step.step_number
                if step_id not in self.console_steps:
                    panel = self._create_compact_step_display(step)
                    if self.lake_view is not None:
                        lake_view_panel_generator = asyncio.create_task(
                            self._create_lakeview_step_display(step)
                        )
                    else:
                        lake_view_panel_generator = None
                    self.console_steps[step_id] = ConsoleStep(panel, lake_view_panel_generator)
                    panels.append(panel)
                else:
                    console_step = self.console_steps[step_id]
                    if self.lake_view is None:
                        panels.append(console_step.panel)
                    else:
                        if console_step.lake_view_panel_generator is not None:
                            if console_step.lake_view_panel_generator.done():
                                lake_view_panel = (
                                    console_step.lake_view_panel_generator.result()
                                    or console_step.panel
                                )
                                panels.append(lake_view_panel)
                                self.console_steps[step_id] = ConsoleStep(
                                    lake_view_panel, None, True
                                )
                            else:
                                panels.append(console_step.panel)
                        else:
                            panels.append(console_step.panel)

        if current_step is not None:
            panels.append(self._create_step_display(current_step))
        # reorder panels
        panels = panels[::-1]
        return Group(*panels, fit=False)

    def print_task_progress(self) -> None:
        if self.agent_execution is not None:
            render_group: Group = Group(
                self.create_agent_steps_display(),
                self.create_execution_summary(self.agent_execution),
            )

        else:
            render_group = self.create_agent_steps_display()

        if self.live_display is None:
            self.live_display = Live(render_group, refresh_per_second=10)
            self.live_display.start()
        else:
            self.live_display.update(render_group)

    def create_execution_summary(self, execution: AgentExecution) -> Group:
        """Display a summary of the agent execution."""
        # Create summary table
        table = Table(title="Execution Summary", width=60)
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", style="green", width=40)

        table.add_row(
            "Task",
            execution.task[:50] + "..." if len(execution.task) > 50 else execution.task,
        )
        table.add_row("Success", "✅ Yes" if execution.success else "❌ No")
        table.add_row("Steps", str(len(execution.steps)))
        table.add_row("Execution Time", f"{execution.execution_time:.2f}s")

        if execution.total_tokens:
            total_tokens = (
                execution.total_tokens.input_tokens + execution.total_tokens.output_tokens
            )
            table.add_row("Total Tokens", str(total_tokens))
            table.add_row("Input Tokens", str(execution.total_tokens.input_tokens))
            table.add_row("Output Tokens", str(execution.total_tokens.output_tokens))

        # Display final result
        if execution.final_result:
            panel = Panel(
                execution.final_result,
                title="Final Result",
                border_style="green" if execution.success else "red",
            )
            return Group(panel, table)
        else:
            return Group(table)
