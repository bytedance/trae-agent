# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Command Line Interface for Trae Agent."""

import asyncio
import os
import sys
import traceback
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from trae_agent.agent import Agent
from trae_agent.utils.cli import CLIConsole, ConsoleFactory, ConsoleMode, ConsoleType
from trae_agent.utils.config import Config, TraeAgentConfig
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder

# Load environment variables
_ = load_dotenv()

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Trae Agent - LLM-based agent for software engineering tasks."""
    pass


@cli.command()
@click.argument("task", required=False)
@click.option("--file", "-f", "file_path", help="Path to a file containing the task description.")
@click.option("--provider", "-p", help="LLM provider to use")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--model-base-url", help="Base URL for the model API")
@click.option("--api-key", "-k", help="API key (or set via environment variable)")
@click.option("--max-steps", help="Maximum number of execution steps", type=int)
@click.option("--working-dir", "-w", help="Working directory for the agent")
@click.option("--must-patch", "-mp", is_flag=True, help="Whether to patch the code")
@click.option(
    "--config-file",
    help="Path to configuration file",
    default="trae_config.json",
    envvar="TRAE_CONFIG_FILE",
)
@click.option("--trajectory-file", "-t", help="Path to save trajectory file")
@click.option("--patch-path", "-pp", help="Path to patch file")
@click.option(
    "--console-type",
    "-ct",
    type=click.Choice(["simple", "rich"], case_sensitive=False),
    help="Type of console to use (simple or rich)",
)
@click.option(
    "--agent-type",
    "-at",
    type=click.Choice(["trae_agent"], case_sensitive=False),
    help="Type of agent to use (trae_agent)",
    default="trae_agent",
)
def run(
    task: str | None,
    file_path: str | None,
    patch_path: str,
    provider: str | None = None,
    model: str | None = None,
    model_base_url: str | None = None,
    api_key: str | None = None,
    max_steps: int | None = None,
    working_dir: str | None = None,
    must_patch: bool = False,
    config_file: str = "trae_config.json",
    trajectory_file: str | None = None,
    console_type: str | None = "simple",
    agent_type: str | None = "trae_agent",
):
    """
    Run is the main function of tace. It runs a task using Trae Agent.
    Args:
        tasks: the task that you want your agent to solve. This is required to be in the input
        model: the model expected to be use
        working_dir: the working directory of the agent. This should be set either in cli or inf the config file (trae_config.json)

    Return:
        None (it is expected to be ended after calling the run function)
    """

    if file_path:
        if task:
            console.print(
                "[red]Error: Cannot use both a task string and the --file argument.[/red]"
            )
            sys.exit(1)
        try:
            task = Path(file_path).read_text()
        except FileNotFoundError:
            console.print(f"[red]Error: File not found: {file_path}[/red]")
            sys.exit(1)
    elif not task:
        console.print(
            "[red]Error: Must provide either a task string or use the --file argument.[/red]"
        )
        sys.exit(1)

    config = Config.create(
        config_file=config_file,
    ).resolve_config_values(
        provider=provider,
        model=model,
        model_base_url=model_base_url,
        api_key=api_key,
        max_steps=max_steps,
    )

    if not agent_type:
        console.print("[red]Error: agent_type is required.[/red]")
        sys.exit(1)

    if trajectory_file:
        trajectory_recorder = TrajectoryRecorder(trajectory_file)
    else:
        trajectory_recorder = TrajectoryRecorder()

    # Create CLI Console
    console_mode = ConsoleMode.RUN
    if console_type:
        selected_console_type = (
            ConsoleType.SIMPLE if console_type.lower() == "simple" else ConsoleType.RICH
        )
    else:
        selected_console_type = ConsoleFactory.get_recommended_console_type(console_mode)

    cli_console = ConsoleFactory.create_console(
        console_type=selected_console_type, mode=console_mode
    )

    # For rich console in RUN mode, set the initial task
    if selected_console_type == ConsoleType.RICH and hasattr(cli_console, "set_initial_task"):
        cli_console.set_initial_task(task)

    agent = Agent(agent_type, config, trajectory_recorder, cli_console)

    # Change working directory if specified
    if working_dir:
        try:
            os.chdir(working_dir)
            console.print(f"[blue]Changed working directory to: {working_dir}[/blue]")
        except Exception as e:
            console.print(f"[red]Error changing directory: {e}[/red]")
            sys.exit(1)
    else:
        working_dir = os.getcwd()

    # Ensure working directory is an absolute path
    if not Path(working_dir).is_absolute():
        console.print(
            f"[red]Working directory must be an absolute path: {working_dir}, it should start with `/`[/red]"
        )
        sys.exit(1)

    try:
        task_args = {
            "project_path": working_dir,
            "issue": task,
            "must_patch": "true" if must_patch else "false",
            "patch_path": patch_path,
        }

        # Set up agent context for rich console if applicable
        if selected_console_type == ConsoleType.RICH and hasattr(cli_console, "set_agent_context"):
            cli_console.set_agent_context(agent, config.trae_agent, config_file, trajectory_file)

        # Agent will handle starting the appropriate console
        _ = asyncio.run(agent.run(task, task_args))

        console.print(
            f"\n[green]Trajectory saved to: {trajectory_recorder.trajectory_path.absolute().as_posix()}[/green]"
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]Task execution interrupted by user[/yellow]")
        if trajectory_recorder:
            console.print(
                f"[blue]Partial trajectory saved to: {trajectory_recorder.trajectory_path.absolute().as_posix()}[/blue]"
            )
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        console.print(traceback.format_exc())
        if trajectory_recorder:
            console.print(
                f"[blue]Trajectory saved to: {trajectory_recorder.trajectory_path.absolute().as_posix()}[/blue]"
            )
        sys.exit(1)


@cli.command()
@click.option("--provider", "-p", help="LLM provider to use")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--model-base-url", help="Base URL for the model API")
@click.option("--api-key", "-k", help="API key (or set via environment variable)")
@click.option(
    "--config-file",
    help="Path to configuration file",
    default="trae_config.json",
    envvar="TRAE_CONFIG_FILE",
)
@click.option("--max-steps", help="Maximum number of execution steps", type=int, default=20)
@click.option("--trajectory-file", "-t", help="Path to save trajectory file")
@click.option(
    "--console-type",
    "-ct",
    type=click.Choice(["simple", "rich"], case_sensitive=False),
    help="Type of console to use (simple or rich)",
)
@click.option(
    "--agent-type",
    "-at",
    type=click.Choice(["trae_agent"], case_sensitive=False),
    help="Type of agent to use (trae_agent)",
    default="trae_agent",
)
def interactive(
    provider: str | None = None,
    model: str | None = None,
    model_base_url: str | None = None,
    api_key: str | None = None,
    config_file: str = "trae_config.json",
    max_steps: int | None = None,
    trajectory_file: str | None = None,
    console_type: str | None = "simple",
    agent_type: str | None = "trae_agent",
):
    """
    This function starts an interactive session with Trae Agent.
    Args:
        console_type: Type of console to use for the interactive session
    """
    config = Config.create(
        config_file=config_file,
    ).resolve_config_values(
        provider=provider,
        model=model,
        model_base_url=model_base_url,
        api_key=api_key,
        max_steps=max_steps,
    )

    if config.trae_agent:
        trae_agent_config = config.trae_agent
    else:
        console.print("[red]Error: trae_agent configuration is required in the config file.[/red]")
        sys.exit(1)

    # Create CLI Console for interactive mode
    console_mode = ConsoleMode.INTERACTIVE
    if console_type:
        selected_console_type = (
            ConsoleType.SIMPLE if console_type.lower() == "simple" else ConsoleType.RICH
        )
    else:
        selected_console_type = ConsoleFactory.get_recommended_console_type(console_mode)

    cli_console = ConsoleFactory.create_console(
        console_type=selected_console_type, lakeview_config=config.lakeview, mode=console_mode
    )

    if trajectory_file:
        trajectory_recorder = TrajectoryRecorder(trajectory_file)
    else:
        trajectory_recorder = TrajectoryRecorder()
        trajectory_file = trajectory_recorder.trajectory_path.absolute().as_posix()

    if not agent_type:
        console.print("[red]Error: agent_type is required.[/red]")
        sys.exit(1)

    # Create agent
    agent = Agent(agent_type, config, trajectory_recorder, cli_console)

    # For simple console, use traditional interactive loop
    if selected_console_type == ConsoleType.SIMPLE:
        asyncio.run(
            _run_simple_interactive_loop(
                agent, cli_console, trae_agent_config, config_file, trajectory_file
            )
        )
    else:
        # For rich console, start the textual app which handles interaction
        asyncio.run(
            _run_rich_interactive_loop(
                agent, cli_console, trae_agent_config, config_file, trajectory_file
            )
        )


async def _run_simple_interactive_loop(
    agent: Agent,
    cli_console: CLIConsole,
    trae_agent_config: TraeAgentConfig,
    config_file: str,
    trajectory_file: str | None,
):
    """Run the interactive loop for simple console."""
    while True:
        try:
            task = cli_console.get_task_input()
            if task is None:
                console.print("[green]Goodbye![/green]")
                break

            if task.lower() == "help":
                console.print(
                    Panel(
                        """[bold]Available Commands:[/bold]

• Type any task description to execute it
• 'status' - Show agent status
• 'clear' - Clear the screen
• 'exit' or 'quit' - End the session""",
                        title="Help",
                        border_style="yellow",
                    )
                )
                continue

            working_dir = cli_console.get_working_dir_input()

            if task.lower() == "status":
                console.print(
                    Panel(
                        f"""[bold]Provider:[/bold] {agent.agent_config.model.model_provider.provider}
    [bold]Model:[/bold] {agent.agent_config.model.model}
    [bold]Available Tools:[/bold] {len(agent.agent.tools)}
    [bold]Config File:[/bold] {config_file}
    [bold]Working Directory:[/bold] {os.getcwd()}""",
                        title="Agent Status",
                        border_style="blue",
                    )
                )
                continue

            if task.lower() == "clear":
                console.clear()
                continue

            # Set up trajectory recording for this task
            console.print(f"[blue]Trajectory will be saved to: {trajectory_file}[/blue]")

            task_args = {
                "project_path": working_dir,
                "issue": task,
                "must_patch": "false",
            }

            # Execute the task
            console.print(f"\n[blue]Executing task: {task}[/blue]")

            # Start console and execute task
            console_task = asyncio.create_task(cli_console.start())
            execution_task = asyncio.create_task(agent.run(task, task_args))

            # Wait for execution to complete
            _ = await execution_task
            _ = await console_task

            console.print(f"\n[green]Trajectory saved to: {trajectory_file}[/green]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'exit' or 'quit' to end the session[/yellow]")
        except EOFError:
            console.print("\n[green]Goodbye![/green]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


async def _run_rich_interactive_loop(
    agent: Agent,
    cli_console: CLIConsole,
    trae_agent_config: TraeAgentConfig,
    config_file: str,
    trajectory_file: str | None,
):
    """Run the interactive loop for rich console."""
    # Set up the agent in the rich console so it can handle task execution
    if hasattr(cli_console, "set_agent_context"):
        cli_console.set_agent_context(agent, trae_agent_config, config_file, trajectory_file)

    # Start the console UI - this will handle the entire interaction
    await cli_console.start()


@cli.command()
@click.option(
    "--config-file",
    help="Path to configuration file",
    default="trae_config.json",
    envvar="TRAE_CONFIG_FILE",
)
@click.option("--provider", "-p", help="LLM provider to use")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--model-base-url", help="Base URL for the model API")
@click.option("--api-key", "-k", help="API key (or set via environment variable)")
@click.option("--max-steps", help="Maximum number of execution steps", type=int)
def show_config(
    config_file: str,
    provider: str | None = None,
    model: str | None = None,
    model_base_url: str | None = None,
    api_key: str | None = None,
    max_steps: int | None = None,
):
    """Show current configuration settings."""
    config_path = Path(config_file)
    if not config_path.exists():
        console.print(
            Panel(
                f"""[yellow]No configuration file found at: {config_file}[/yellow]

Using default settings and environment variables.""",
                title="Configuration Status",
                border_style="yellow",
            )
        )

    config = Config.create(
        config_file=config_file,
    ).resolve_config_values(
        provider=provider,
        model=model,
        model_base_url=model_base_url,
        api_key=api_key,
        max_steps=max_steps,
    )

    if config.trae_agent:
        trae_agent_config = config.trae_agent
    else:
        console.print("[red]Error: trae_agent configuration is required in the config file.[/red]")
        sys.exit(1)

    # Display general settings
    general_table = Table(title="General Settings")
    general_table.add_column("Setting", style="cyan")
    general_table.add_column("Value", style="green")

    general_table.add_row(
        "Default Provider", str(trae_agent_config.model.model_provider.provider or "Not set")
    )
    general_table.add_row("Max Steps", str(trae_agent_config.max_steps or "Not set"))

    console.print(general_table)

    # Display provider settings
    provider_config = trae_agent_config.model.model_provider
    provider_table = Table(title=f"{provider_config.provider.title()} Configuration")
    provider_table.add_column("Setting", style="cyan")
    provider_table.add_column("Value", style="green")

    provider_table.add_row("Model", trae_agent_config.model.model or "Not set")
    provider_table.add_row("Base URL", provider_config.base_url or "Not set")
    provider_table.add_row("API Version", provider_config.api_version or "Not set")
    provider_table.add_row(
        "API Key",
        f"Set ({provider_config.api_key[:4]}...{provider_config.api_key[-4:]})"
        if provider_config.api_key
        else "Not set",
    )
    provider_table.add_row("Max Tokens", str(trae_agent_config.model.max_tokens))
    provider_table.add_row("Temperature", str(trae_agent_config.model.temperature))
    provider_table.add_row("Top P", str(trae_agent_config.model.top_p))

    if trae_agent_config.model.model_provider.provider == "anthropic":
        provider_table.add_row("Top K", str(trae_agent_config.model.top_k))

    console.print(provider_table)


@cli.command()
def tools():
    """Show available tools and their descriptions."""
    from .tools import tools_registry

    tools_table = Table(title="Available Tools")
    tools_table.add_column("Tool Name", style="cyan")
    tools_table.add_column("Description", style="green")

    for tool_name in tools_registry:
        try:
            tool = tools_registry[tool_name]()
            tools_table.add_row(tool.name, tool.description)
        except Exception as e:
            tools_table.add_row(tool_name, f"[red]Error loading: {e}[/red]")

    console.print(tools_table)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
