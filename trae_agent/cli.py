# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Command Line Interface for Trae Agent."""

import asyncio
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from trae_agent.agent import Agent
from trae_agent.utils.cli import CLIConsole, ConsoleFactory, ConsoleMode, ConsoleType
from trae_agent.utils.config import Config, TraeAgentConfig

# Load environment variables
_ = load_dotenv()

console = Console()


def resolve_config_file(config_file: str) -> str:
    """
    Resolve config file with backward compatibility.
    First tries the specified file, then falls back to JSON if YAML doesn't exist.
    """
    if config_file.endswith(".yaml") or config_file.endswith(".yml"):
        yaml_path = Path(config_file)
        json_path = Path(config_file.replace(".yaml", ".json").replace(".yml", ".json"))
        if yaml_path.exists():
            return str(yaml_path)
        elif json_path.exists():
            console.print(f"[yellow]YAML config not found, using JSON config: {json_path}[/yellow]")
            return str(json_path)
        else:
            console.print(
                "[red]Error: Config file not found. Please specify a valid config file in the command line option --config-file[/red]"
            )
            sys.exit(1)
    else:
        return config_file


def _generate_session_id() -> str:
    """Generate a session ID based on the current timestamp."""
    from datetime import datetime

    return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def check_docker(timeout=3):
    # 1) Check whether the docker CLI is installed
    if shutil.which("docker") is None:
        return {
            "cli": False,
            "daemon": False,
            "version": None,
            "error": "docker CLI not found",
        }
    # 2) Check whether the Docker daemon is reachable (this makes a real request)
    try:
        cp = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if cp.returncode == 0 and cp.stdout.strip():
            return {
                "cli": True,
                "daemon": True,
                "version": cp.stdout.strip(),
                "error": None,
            }
        else:
            # The daemon may not be running or permissions may be insufficient
            return {
                "cli": True,
                "daemon": False,
                "version": None,
                "error": (cp.stderr or cp.stdout).strip(),
            }
    except Exception as e:
        return {"cli": True, "daemon": False, "version": None, "error": str(e)}


def build_with_pyinstaller():
    os.system("rm -rf trae_agent/dist")
    print("--- Building edit_tool ---")
    subprocess.run(
        [
            "pyinstaller",
            "--name",
            "edit_tool",
            "trae_agent/tools/edit_tool_cli.py",
        ],
        check=True,
    )
    print("\n--- Building json_edit_tool ---")
    subprocess.run(
        [
            "pyinstaller",
            "--name",
            "json_edit_tool",
            "--hidden-import=jsonpath_ng",
            "trae_agent/tools/json_edit_tool_cli.py",
        ],
        check=True,
    )
    os.system("mkdir trae_agent/dist")
    os.system("cp dist/edit_tool/edit_tool trae_agent/dist")
    os.system("cp -r dist/json_edit_tool/_internal trae_agent/dist")
    os.system("cp dist/json_edit_tool/json_edit_tool trae_agent/dist")
    os.system("rm -rf dist")


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
    default="trae_config.yaml",
    envvar="TRAE_CONFIG_FILE",
)
@click.option("--trajectory-file", "-t", help="Path to save trajectory file")
@click.option("--patch-path", "-pp", help="Path to patch file")
# --- Docker Mode Start ---
@click.option(
    "--docker-image",
    type=str,
    default=None,
    help="Specify a Docker image to run the task in a new container",
)
@click.option(
    "--docker-container-id",
    type=str,
    default=None,
    help="Attach to an existing Docker container by ID",
)
@click.option(
    "--dockerfile-path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    default=None,
    help="Absolute path to a Dockerfile to build an environment",
)
@click.option(
    "--docker-image-file",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    default=None,
    help="Path to a local Docker image file (tar archive) to load.",
)
@click.option(
    "--docker-keep",
    type=bool,
    default=True,
    help="Keep or remove the Docker container after finishing the task",
)
# --- Docker Mode End ---


@click.option(
    "--console-type",
    "-ct",
    default="simple",
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
@click.option(
    "--extract-memory",
    is_flag=True,
    default=False,
    help="Extract long-term memory after task execution",
)
@click.option(
    "--memory",
    "memory_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a .md memory file to preload into the session",
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
    config_file: str = "trae_config.yaml",
    trajectory_file: str | None = None,
    console_type: str | None = "simple",
    agent_type: str | None = "trae_agent",
    extract_memory: bool = False,
    memory_path: str | None = None,
    # --- Add Docker Mode ---
    docker_image: str | None = None,
    docker_container_id: str | None = None,
    dockerfile_path: str | None = None,
    docker_image_file: str | None = None,
    docker_keep: bool = True,
):
    """
    Run is the main function of trae. it runs a task using Trae Agent.
    Args:
        tasks: the task that you want your agent to solve. This is required to be in the input
        model: the model expected to be use
        working_dir: the working directory of the agent. This should be set either in cli or in the config file

    Return:
        None (it is expected to be ended after calling the run function)
    """

    docker_config: dict[str, str | None] | None = None
    if (
        sum(
            [
                bool(docker_image),
                bool(docker_container_id),
                bool(dockerfile_path),
                bool(docker_image_file),
            ]
        )
        > 1
    ):
        console.print(
            "[red]Error: --docker-image, --docker-container-id, --dockerfile-path, and --docker-image-file are mutually exclusive.[/red]"
        )
        sys.exit(1)

    if dockerfile_path:
        docker_config = {"dockerfile_path": dockerfile_path}
        console.print(
            f"[blue]Docker mode enabled. Building from Dockerfile: {dockerfile_path}[/blue]"
        )
    elif docker_image_file:
        docker_config = {"docker_image_file": docker_image_file}
        console.print(
            f"[blue]Docker mode enabled. Loading from image file: {docker_image_file}[/blue]"
        )
    elif docker_container_id:
        docker_config = {"container_id": docker_container_id}
        console.print(
            f"[blue]Docker mode enabled. Attaching to container: {docker_container_id}[/blue]"
        )
    elif docker_image:
        docker_config = {"image": docker_image}
        console.print(f"[blue]Docker mode enabled. Using image: {docker_image}[/blue]")
    # --- ADDED END ---

    # Apply backward compatibility for config file
    config_file = resolve_config_file(config_file)

    if docker_config:
        check_msg = check_docker()
        if check_msg["cli"] and check_msg["daemon"] and check_msg["version"]:
            print("Docker is configured correctly.")
        else:
            print(f"Docker is configured incorrectly. {check_msg['error']}")
            sys.exit(1)
        if not (os.path.exists("trae_agent/dist") and os.path.exists("trae_agent/dist/_internal")):
            print("Building tools of Docker mode for the first use, waiting for a few seconds...")
            build_with_pyinstaller()
            print("Building finished.")

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

    # agent = Agent(agent_type, config, trajectory_file, cli_console)

    if docker_config is not None:
        docker_config["workspace_dir"] = working_dir  # now type-safe

    # Change working directory if specified
    if working_dir:
        try:
            Path(working_dir).mkdir(parents=True, exist_ok=True)
            # os.chdir(working_dir)
            console.print(f"[blue]Changed working directory to: {working_dir}[/blue]")
            working_dir = os.path.abspath(working_dir)
        except Exception as e:
            error_text = Text(f"Error changing directory: {e}", style="red")
            console.print(error_text)
            sys.exit(1)
    else:
        working_dir = os.getcwd()
        console.print(f"[blue]Using current directory as working directory: {working_dir}[/blue]")

    # Ensure working directory is an absolute path
    if not Path(working_dir).is_absolute():
        console.print(
            f"[red]Working directory must be an absolute path: {working_dir}, it should start with `/`[/red]"
        )
        sys.exit(1)

    session_id = _generate_session_id()

    agent = Agent(
        agent_type,
        config,
        trajectory_file,
        cli_console,
        docker_config=docker_config,
        docker_keep=docker_keep,
        session_id=session_id,
        memory_path=memory_path,
    )

    if memory_path and agent.agent.long_term_memory:
        console.print(f"[cyan]Preloaded memory from: {memory_path}[/cyan]")

    if not docker_config:
        try:
            os.chdir(working_dir)
        except Exception as e:
            error_text = Text(f"Error changing directory: {e}", style="red")
            console.print(error_text)
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

        console.print(f"\n[green]Trajectory saved to: {agent.trajectory_file}[/green]")

        # Extract long-term memory if requested
        if extract_memory and agent.agent.long_term_memory:
            memory_path = asyncio.run(agent.agent.extract_memory_now())
            if memory_path:
                console.print(f"[cyan]Long-term memory saved to: {memory_path}[/cyan]")
            else:
                console.print("[yellow]No memory could be extracted from this execution.[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Task execution interrupted by user[/yellow]")
        console.print(f"[blue]Partial trajectory saved to: {agent.trajectory_file}[/blue]")
        sys.exit(1)
    except Exception as e:
        try:
            from docker.errors import DockerException

            if isinstance(e, DockerException):
                error_text = Text(f"Docker Error: {e}", style="red")
                console.print(f"\n{error_text}")
                console.print(
                    "[yellow]Please ensure the Docker daemon is running and you have the necessary permissions.[/yellow]"
                )
            else:
                raise e
        except ImportError:
            error_text = Text(f"Unexpected error: {e}", style="red")
            console.print(f"\n{error_text}")
            console.print(traceback.format_exc())
        except Exception:
            error_text = Text(f"Unexpected error: {e}", style="red")
            console.print(f"\n{error_text}")
            console.print(traceback.format_exc())
        console.print(f"[blue]Trajectory saved to: {agent.trajectory_file}[/blue]")
        sys.exit(1)


@cli.command()
@click.option("--provider", "-p", help="LLM provider to use")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--model-base-url", help="Base URL for the model API")
@click.option("--api-key", "-k", help="API key (or set via environment variable)")
@click.option(
    "--config-file",
    help="Path to configuration file",
    default="trae_config.yaml",
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
@click.option(
    "--memory",
    "memory_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a .md memory file to preload into the session",
)
def interactive(
    provider: str | None = None,
    model: str | None = None,
    model_base_url: str | None = None,
    api_key: str | None = None,
    config_file: str = "trae_config.yaml",
    max_steps: int | None = None,
    trajectory_file: str | None = None,
    console_type: str | None = "simple",
    agent_type: str | None = "trae_agent",
    memory_path: str | None = None,
):
    """
    This function starts an interactive session with Trae Agent.
    Args:
        console_type: Type of console to use for the interactive session
    """
    # Apply backward compatibility for config file
    config_file = resolve_config_file(config_file)

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
        console_type=selected_console_type,
        lakeview_config=config.lakeview,
        mode=console_mode,
    )

    if not agent_type:
        console.print("[red]Error: agent_type is required.[/red]")
        sys.exit(1)

    # Create agent
    session_id = _generate_session_id()
    agent = Agent(agent_type, config, trajectory_file, cli_console, session_id=session_id, memory_path=memory_path)

    if memory_path and agent.agent.long_term_memory:
        console.print(f"[cyan]Preloaded memory from: {memory_path}[/cyan]")

    # Get the actual trajectory file path (in case it was auto-generated)
    trajectory_file = agent.trajectory_file

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
            error_text = Text(f"Error: {e}", style="red")
            console.print(error_text)


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
    default="trae_config.yaml",
    envvar="TRAE_CONFIG_FILE",
)
@click.option("--provider", "-p", help="LLM provider to use")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--model-base-url", help="Base URL for the model API")
@click.option("--api-key", "-k", help="API key (or set via environment variable)")
@click.option("--max-steps", help="Maximum number of execution steps", type=int)
def show_config(
    config_file: str,
    provider: str | None,
    model: str | None,
    model_base_url: str | None,
    api_key: str | None,
    max_steps: int | None,
):
    """Show current configuration settings."""
    # Apply backward compatibility for config file
    config_file = resolve_config_file(config_file)

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
        "Default Provider",
        str(trae_agent_config.model.model_provider.provider or "Not set"),
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
        (
            f"Set ({provider_config.api_key[:4]}...{provider_config.api_key[-4:]})"
            if provider_config.api_key
            else "Not set"
        ),
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


@cli.command()
@click.option(
    "--trajectory-file",
    "-t",
    required=True,
    help="Path to a trajectory JSON file to extract memory from",
)
@click.option(
    "--output-dir",
    "-o",
    default="memory/",
    help="Output directory for the memory Markdown file",
)
@click.option(
    "--config-file",
    help="Path to configuration file (for model settings)",
    default="trae_config.yaml",
    envvar="TRAE_CONFIG_FILE",
)
def memory(
    trajectory_file: str,
    output_dir: str,
    config_file: str,
):
    """Extract long-term memory from a trajectory file."""
    import json

    from trae_agent.agent.agent_basics import AgentStep, AgentStepState
    from trae_agent.tools.base import ToolCall, ToolResult
    from trae_agent.utils.llm_clients.llm_basics import LLMResponse, LLMUsage
    from trae_agent.utils.long_term_memory import LongTermMemory

    # Load trajectory JSON
    traj_path = Path(trajectory_file)
    if not traj_path.exists():
        console.print(f"[red]Error: Trajectory file not found: {traj_path}[/red]")
        sys.exit(1)

    with open(traj_path, "r", encoding="utf-8") as f:
        traj_data = json.load(f)

    # Rebuild AgentStep objects from trajectory data
    steps: list[AgentStep] = []
    for step_data in traj_data.get("agent_steps", []):
        llm_response = None
        resp_data = step_data.get("llm_response")
        if resp_data:
            usage = None
            usage_data = resp_data.get("usage")
            if usage_data:
                usage = LLMUsage(
                    input_tokens=usage_data.get("input_tokens", 0),
                    output_tokens=usage_data.get("output_tokens", 0),
                )
            tool_calls = None
            tc_data = resp_data.get("tool_calls")
            if tc_data:
                tool_calls = [
                    ToolCall(
                        call_id=tc.get("call_id", ""),
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", {}),
                    )
                    for tc in tc_data
                ]
            llm_response = LLMResponse(
                content=resp_data.get("content", ""),
                model=resp_data.get("model", ""),
                finish_reason=resp_data.get("finish_reason"),
                usage=usage,
                tool_calls=tool_calls,
            )

        tool_results = None
        tr_data = step_data.get("tool_results")
        if tr_data:
            tool_results = [
                ToolResult(
                    call_id=tr.get("call_id", ""),
                    name=tr.get("name", ""),
                    success=tr.get("success", False),
                    result=tr.get("result"),
                    error=tr.get("error"),
                )
                for tr in tr_data
            ]

        step = AgentStep(
            step_number=step_data.get("step_number", 0),
            state=AgentStepState(step_data.get("state", "completed")),
            llm_response=llm_response,
            tool_results=tool_results,
            reflection=step_data.get("reflection"),
            error=step_data.get("error"),
        )
        steps.append(step)

    if not steps:
        console.print("[yellow]No agent steps found in the trajectory file.[/yellow]")
        sys.exit(1)

    # Load config for model settings
    config_file = resolve_config_file(config_file)
    try:
        config = Config.create(config_file=config_file)
        fallback_model = config.trae_agent.model if config.trae_agent else None
    except Exception:
        fallback_model = None

    if not fallback_model:
        console.print("[red]Error: No model configuration found. Check your config file.[/red]")
        sys.exit(1)

    # Create LongTermMemory and extract
    from trae_agent.utils.config import LongTermMemoryConfig

    ltm_config = LongTermMemoryConfig(
        enabled=True,
        output_dir=output_dir,
        model=fallback_model,
    )
    ltm = LongTermMemory(config=ltm_config, fallback_model=fallback_model)
    ltm.set_task(traj_data.get("task", "Unknown"))

    console.print(f"[blue]Extracting memory from {len(steps)} steps...[/blue]")

    memory_path = asyncio.run(ltm.extract_and_save(steps))
    if memory_path:
        console.print(f"[green]Long-term memory saved to: {memory_path}[/green]")
        # Print preview
        md_content = Path(memory_path).read_text(encoding="utf-8")
        from rich.markdown import Markdown as RichMarkdown

        console.print(Panel(RichMarkdown(md_content), title="Memory Preview", border_style="cyan"))
    else:
        console.print("[yellow]No memory could be extracted from this trajectory.[/yellow]")


@cli.command("memory-list")
@click.option(
    "--memory-dir",
    default="memory/",
    help="Directory containing memory files and index",
)
def memory_list(memory_dir: str):
    """List session-memory associations from the memory index."""
    from trae_agent.utils.long_term_memory import LongTermMemory

    index_path = os.path.join(memory_dir, "index.json")
    index = LongTermMemory.query_index(index_path)

    sessions = index.get("sessions", {})
    if not sessions:
        console.print("[yellow]No memory index found or no sessions recorded.[/yellow]")
        return

    table = Table(title="Memory Index — Session Associations")
    table.add_column("Session ID", style="cyan")
    table.add_column("Task Name", style="green")
    table.add_column("Memory Files", style="magenta")
    table.add_column("Trajectory File", style="blue")
    table.add_column("Created At", style="yellow")

    for session_id, entry in sessions.items():
        memory_files = "\n".join(entry.get("memory_files", []))
        table.add_row(
            session_id,
            entry.get("task_name", "Unknown"),
            memory_files,
            entry.get("trajectory_file", ""),
            entry.get("created_at", ""),
        )

    console.print(table)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
