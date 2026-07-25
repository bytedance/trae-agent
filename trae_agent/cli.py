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
from trae_agent.utils.multimodal import load_images

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
    import shutil

    # P1 修复:原实现用 os.system("rm -rf ...") / mkdir / cp,在 Windows 上
    # 直接不可用,且跨平台行为不一致。改用 shutil,且用 Path 处理目录。
    dist_dir = Path("trae_agent/dist")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
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
    dist_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy("dist/edit_tool/edit_tool", dist_dir / "edit_tool")
    internal_src = Path("dist/json_edit_tool/_internal")
    if internal_src.exists():
        shutil.copytree(internal_src, dist_dir / "_internal", dirs_exist_ok=True)
    shutil.copy("dist/json_edit_tool/json_edit_tool", dist_dir / "json_edit_tool")
    if Path("dist").exists():
        shutil.rmtree("dist")


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
    "--image",
    "-i",
    "images",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Attach an image to the task (multimodal). Repeatable. "
    "Only sent when the selected model supports multimodal input.",
)
@click.option(
    "--output-dir",
    "-od",
    default=None,
    type=click.Path(resolve_path=True),
    help="Custom output directory for generated files. If set, files go directly here (no project subfolders).",
)
@click.option(
    "--project",
    default=None,
    help="Project name for organizing outputs. Files saved to ~/Desktop/trae-agent-outputs/<project>/",
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
    images: tuple[str, ...] = (),
    agent_type: str | None = "trae_agent",
    output_dir: str | None = None,
    project: str | None = None,
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

    # --- Output directory setup ---
    from trae_agent.utils.output_manager import set_output_dir_override, set_current_project, new_conversation
    if output_dir:
        set_output_dir_override(output_dir)
        console.print(f"[blue]Output directory: {output_dir}[/blue]")
    elif project:
        set_current_project(project)
        conv_id = new_conversation(project)
        console.print(f"[blue]Project: {project} | Conversation: {conv_id}[/blue]")

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

    # working_dir 已被 os.path.abspath() 或 os.getcwd() 确保为绝对路径,
    # 不再需要 is_absolute 校验(死代码)。

    agent = Agent(
        agent_type,
        config,
        trajectory_file,
        cli_console,
        docker_config=docker_config,
        docker_keep=docker_keep,
    )

    if not docker_config:
        try:
            os.chdir(working_dir)
        except Exception as e:
            error_text = Text(f"Error changing directory: {e}", style="red")
            console.print(error_text)
            sys.exit(1)

    # Render a startup banner — Claude Code style.
    try:
        from rich.box import DOUBLE_EDGE

        banner = (
            f"[bold cyan]trae-agent[/bold cyan]  [dim]·[/dim]  "
            f"[green]{provider or config.trae_agent.model.model_provider.provider}[/green]"
            f"[dim]/[/dim]"
            f"[yellow]{model or config.trae_agent.model.model}[/yellow]"
        )
        console.print(Panel(banner, box=DOUBLE_EDGE, border_style="cyan"))
    except Exception:
        pass

    try:
        task_args = {
            "project_path": working_dir,
            "issue": task,
            "must_patch": "true" if must_patch else "false",
            "patch_path": patch_path,
        }

        # --- Multimodal: load attached images ---
        images_list = None
        if images:
            try:
                images_list = load_images(list(images))
            except (FileNotFoundError, ValueError) as e:
                console.print(f"[red]Error loading image: {e}[/red]")
                sys.exit(1)
            if config.trae_agent and not config.trae_agent.model.supports_multimodal:
                console.print(
                    "[yellow]Warning: the selected model does not support "
                    "multimodal input; attached images will be ignored.[/yellow]"
                )
                images_list = None

        # Set up agent context for rich console if applicable
        if selected_console_type == ConsoleType.RICH and hasattr(cli_console, "set_agent_context"):
            cli_console.set_agent_context(agent, config.trae_agent, config_file, trajectory_file)

        # Agent will handle starting the appropriate console
        _ = asyncio.run(agent.run(task, task_args, images=images_list))

        console.print(f"\n[green]Trajectory saved to: {agent.trajectory_file}[/green]")

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
@click.argument("task", required=False)
@click.option("--file", "-f", "file_path", help="Path to a file containing the task description.")
@click.option("--provider", "-p", help="LLM provider to use")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--max-steps", help="Maximum number of execution steps", type=int)
@click.option("--working-dir", "-w", help="Working directory for the agent")
@click.option(
    "--config-file",
    help="Path to configuration file",
    default="trae_config.yaml",
    envvar="TRAE_CONFIG_FILE",
)
def plan(
    task: str | None,
    file_path: str | None,
    provider: str | None = None,
    model: str | None = None,
    max_steps: int | None = None,
    working_dir: str | None = None,
    config_file: str = "trae_config.yaml",
):
    """
    Plan mode — read-only exploration. Same syntax as `trae run`, but the
    agent is restricted to non-mutation tools and emits a structured plan.

    Mirrors Claude Code's `plan` / `build` split.
    """
    if file_path:
        if task:
            console.print("[red]Cannot use both a task string and the --file argument.[/red]")
            sys.exit(1)
        try:
            task = Path(file_path).read_text()
        except FileNotFoundError:
            console.print(f"[red]File not found: {file_path}[/red]")
            sys.exit(1)
    elif not task:
        console.print("[red]Must provide either a task string or --file argument.[/red]")
        sys.exit(1)

    config_file = resolve_config_file(config_file)

    config = Config.create(
        config_file=config_file,
    ).resolve_config_values(
        provider=provider,
        model=model,
        max_steps=max_steps,
    )

    working_dir = working_dir or os.getcwd()
    if not Path(working_dir).is_absolute():
        working_dir = os.path.abspath(working_dir)

    # Force plan mode.
    if config.trae_agent:
        if max_steps is not None:
            config.trae_agent.max_steps = max_steps
        else:
            config.trae_agent.max_steps = config.trae_agent.max_steps or 30
            # Heuristic: plan 模式默认上限 30,避免无限制狂奔。
            # 仅当用户未显式指定时才施加上限,否则用户的 --max-steps 会被强制压回 30。
            if config.trae_agent.max_steps > 30:
                console.print(
                    f"[yellow]Warning: plan mode caps max_steps at 30. "
                    f"Config value {config.trae_agent.max_steps} overridden. "
                    f"Use --max-steps to explicitly set a higher value.[/yellow]"
                )
                config.trae_agent.max_steps = 30

    cli_console = ConsoleFactory.create_console(
        console_type=ConsoleType.SIMPLE, mode=ConsoleMode.RUN
    )

    agent = Agent(
        "trae_agent",
        config,
        None,
        cli_console,
    )
    # Flip the plan-mode flag BEFORE the task starts.
    if hasattr(agent.agent, "plan_mode"):
        agent.agent.plan_mode = True

    console.print(
        Panel(
            "[bold cyan]PLAN MODE[/bold cyan]\n"
            "Read-only exploration — the agent will inspect files and emit a "
            "structured plan, but will not modify anything.\n"
            f"Project: {working_dir}",
            border_style="cyan",
        )
    )

    try:
        task_args = {
            "project_path": working_dir,
            "issue": task,
            "must_patch": "false",
        }
        _ = asyncio.run(agent.run(task, task_args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Plan interrupted.[/yellow]")
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
    agent = Agent(agent_type, config, trajectory_file, cli_console)

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

            # 重置 console 状态，为新一轮任务做准备
            # （上一轮的 agent_execution 还是 COMPLETED 状态，会导致 start() 的 while 循环立即退出）
            cli_console.agent_execution = None
            cli_console.console_step_history.clear()

            # agent.run() 内部会创建 cli_console.start() 协程来显示进度
            # 不需要在这里重复创建，否则两个 console 协程会互相干扰
            await agent.run(task, task_args)

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
def version():
    """Show trae-agent version and exit."""
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        v = _v("trae-agent")
    except PackageNotFoundError:
        v = "0.1.0+local"
    console.print(
        Panel(
            f"[bold cyan]trae-agent[/bold cyan] [green]{v}[/green]\n"
            f"[dim]Python · Local LLM Coding Agent[/dim]",
            border_style="cyan",
        )
    )


@cli.command()
@click.argument("trajectory_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--config-file",
    default="trae_config.yaml",
    help="Path to trae_config.yaml. Provider/model are taken from the saved "
    "trajectory if the loaded values are missing, but the running agent "
    "still uses the providers defined in this file.",
)
@click.option(
    "--agent-type",
    default="trae_agent",
    show_default=True,
    help="Agent implementation (currently only `trae_agent` is supported).",
)
@click.option(
    "--provider",
    default=None,
    help="Override the LLM provider from the trajectory (e.g. doubao, ollama).",
)
@click.option(
    "--model",
    default=None,
    help="Override the model id from the trajectory (e.g. qwen2.5-coder:7b).",
)
@click.option(
    "--max-steps",
    type=int,
    default=None,
    help="Override the max-step budget. The resumed run counts steps from "
    "where the saved trajectory left off, so this is the *additional* "
    "steps, not the total.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Load and summarize the trajectory without actually running the agent.",
)
@click.option(
    "--trajectory-file-output",
    type=click.Path(dir_okay=False),
    default=None,
    help="Where to write the new trajectory (default: <name>_resumed_<ts>.json "
    "next to the original).",
)
def resume(
    trajectory_file: str,
    config_file: str,
    agent_type: str,
    provider: str | None,
    model: str | None,
    max_steps: int | None,
    dry_run: bool,
    trajectory_file_output: str | None,
):
    """Resume an interrupted run from a saved trajectory file.

    TRAJECTORY_FILE is the JSON file written by a previous `trae run` /
    `trae interactive` (look under `trajectories/`). The agent picks up
    exactly where it stopped — same task, same message history, same step
    counter — and continues from the next step.
    """
    import asyncio
    from datetime import datetime
    from pathlib import Path

    from trae_agent.utils.trajectory_loader import (
        TrajectoryLoadError,
        load_trajectory,
        summarize,
    )

    # ----- Load + sanity check -----
    try:
        traj = load_trajectory(trajectory_file)
    except TrajectoryLoadError as e:
        error_text = Text(f"Cannot resume: {e}", style="red")
        console.print(error_text)
        sys.exit(1)

    console.print(
        Panel(
            f"[bold]Resuming trajectory[/bold]\n\n{summarize(traj)}",
            title="[cyan]trajectory loaded[/cyan]",
            border_style="cyan",
        )
    )

    if dry_run:
        console.print("[yellow]--dry-run set; not invoking agent.[/yellow]")
        return

    # ----- Resolve config + effective provider/model -----
    config_file = resolve_config_file(config_file)
    config: Config = (
        Config.create(config_file=config_file)
        .resolve_config_values(
            provider=provider or traj.provider or None,
            model=model or traj.model or None,
            max_steps=max_steps,
        )
    )

    eff_provider = config.trae_agent.model.model_provider.provider
    eff_model = config.trae_agent.model.model

    # ----- Pick a console (mirrors `run`) -----
    console_mode = ConsoleMode.RUN
    selected_console_type = ConsoleFactory.get_recommended_console_type(console_mode)
    cli_console = ConsoleFactory.create_console(
        console_type=selected_console_type, mode=console_mode
    )

    agent = Agent(
        agent_type,
        config,
        None,  # new trajectory path, set below
        cli_console,
    )

    # ----- Restore message history + step counter -----
    agent.resume_from_messages(
        messages=traj.last_input_messages,
        completed_steps=traj.completed_steps,
    )

    # ----- New trajectory path -----
    if trajectory_file_output:
        out_path = Path(trajectory_file_output).expanduser().resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = traj.trajectory_path.with_name(
            f"{traj.trajectory_path.stem}_resumed_{ts}.json"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    agent.set_trajectory_file(str(out_path))

    console.print(
        f"[blue]Resuming from step {traj.completed_step_count + 1}[/blue]\n"
        f"[blue]Provider: {eff_provider} | Model: {eff_model}[/blue]\n"
        f"[blue]New trajectory: {out_path}[/blue]\n"
    )

    # ----- Run -----
    task_args = {
        "project_path": os.getcwd(),
        "issue": traj.task,
        "must_patch": "false",
    }
    try:
        execution = asyncio.run(agent.run(traj.task, task_args))
    except Exception as e:
        console.print(f"[red]Resume failed: {e}[/red]")
        sys.exit(1)

    if execution.success:
        console.print(
            Panel(
                f"[green]Resume complete[/green]\n\n{execution.final_result or ''}",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[yellow]Resume finished with state {execution.agent_state}[/yellow]\n\n"
                f"{execution.final_result or ''}",
                border_style="yellow",
            )
        )
        sys.exit(2)


@cli.group()
def skills():
    """Manage skills (extensible system-prompt fragments)."""
    pass


@skills.command(name="list")
@click.option("--project-dir", default=".", help="Project root for project-local skills.")
def skills_list(project_dir: str):
    """List all discoverable skills (user-wide + project-local)."""
    from .skills.loader import load_all_skills

    loaded = load_all_skills(project_dir=project_dir)

    if not loaded:
        console.print(
            Panel(
                "[yellow]No skills found.[/yellow]\n\n"
                "User skills: [cyan]~/.trae-agent/skills/*.md[/cyan]\n"
                "Project skills: [cyan]./.trae-agent/skills/*.md[/cyan]",
                title="Skills",
                border_style="yellow",
            )
        )
        return

    table = Table(title=f"Skills ({len(loaded)} loaded)")
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Description", style="green")
    table.add_column("Source", style="dim")

    for s in loaded:
        table.add_row(s.name, s.description, s.relative_source)

    console.print(table)


@skills.command(name="show")
@click.argument("name")
@click.option("--project-dir", default=".", help="Project root for project-local skills.")
def skills_show(name: str, project_dir: str):
    """Show the full content of a skill."""
    from .skills.loader import load_all_skills

    loaded = load_all_skills(project_dir=project_dir)
    match = next((s for s in loaded if s.name == name), None)
    if not match:
        console.print(f"[red]Skill '{name}' not found.[/red]")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]Description:[/bold cyan] {match.description}\n"
            f"[bold cyan]Source:[/bold cyan] {match.relative_source}\n"
            + (
                f"[bold cyan]Allowed tools:[/bold cyan] {', '.join(match.allowed_tools)}\n"
                if match.allowed_tools
                else "[bold cyan]Allowed tools:[/bold cyan] (all)\n"
            ),
            title=f"Skill: {match.name}",
            border_style="cyan",
        )
    )
    console.print(match.content)


@skills.command(name="open-dir")
def skills_open_dir():
    """Open the user skills directory in Finder (creates it if missing)."""
    from pathlib import Path

    p = Path.home() / ".trae-agent" / "skills"
    p.mkdir(parents=True, exist_ok=True)
    console.print(f"Skills directory: [cyan]{p}[/cyan]")
    if sys.platform == "darwin":
        _ = subprocess.Popen(["open", str(p)])
    elif sys.platform.startswith("linux"):
        _ = subprocess.Popen(["xdg-open", str(p)])
    elif os.name == "nt":
        _ = subprocess.Popen(["explorer", str(p)])


@cli.group()
def trajectory():
    """Inspect and export saved trajectories."""
    pass


@trajectory.command(name="export")
@click.argument("trajectory_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "html"], case_sensitive=False),
    default="md",
    help="Output format (default: md; auto-detected from --output extension).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Destination path. Default: <trajectory>.md next to the source.",
)
def trajectory_export(trajectory_file: str, fmt: str, output: str | None):
    """Export a trajectory JSON to Markdown or HTML for sharing/review."""
    from trae_agent.utils.trajectory_exporter import export as _export

    src = Path(trajectory_file).expanduser().resolve()
    if output is None:
        out = src.with_suffix("." + fmt.lower())
    else:
        out = Path(output).expanduser().resolve()

    try:
        written = _export(src, out, fmt=fmt.lower())
    except FileNotFoundError:
        console.print(f"[red]Trajectory not found: {src}[/red]")
        sys.exit(1)
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Cannot parse trajectory: {e}[/red]")
        sys.exit(1)

    console.print(f"[green]✓ Exported trajectory[/green]")
    console.print(f"  source: {src}")
    console.print(f"  output: {written}  ({fmt.upper()})")


# ========== Project Management ==========

@cli.group()
def project():
    """Manage projects (organize outputs by project)."""
    pass


@project.command(name="new")
@click.argument("name")
@click.option("--output-dir", "-o", default=None, help="Custom output directory (no subfolders created).")
def project_new(name: str, output_dir: str | None):
    """Create a new project."""
    from trae_agent.utils.output_manager import new_project
    path = new_project(name, output_dir)
    console.print(f"[green]✓ Project '{name}' created[/green]")
    console.print(f"  Path: {path}")


@project.command(name="list")
def project_list():
    """List all projects."""
    from trae_agent.utils.output_manager import list_projects
    projects = list_projects()
    if not projects:
        console.print("[yellow]No projects yet.[/yellow]")
        console.print("Create one with: trae-cli project new <name>")
        return

    table = Table(title=f"Projects ({len(projects)})")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Conversations", style="dim")
    table.add_column("Created", style="dim")

    for name, info in projects.items():
        conv_count = len(info.get("conversations", []))
        table.add_row(name, info.get("dir", "?"), str(conv_count), info.get("created", "?")[:10])

    console.print(table)


@project.command(name="use")
@click.argument("name")
def project_use(name: str):
    """Switch to an existing project."""
    from trae_agent.utils.output_manager import set_current_project, get_project_dir
    project_dir = get_project_dir(name)
    if project_dir is None:
        console.print(f"[red]Project '{name}' not found. Create it with: trae-cli project new {name}[/red]")
        sys.exit(1)
    set_current_project(name)
    console.print(f"[green]✓ Switched to project '{name}'[/green]")
    console.print(f"  Path: {project_dir}")


@project.command(name="open")
@click.argument("name", required=False)
def project_open(name: str | None):
    """Open project folder in Finder."""
    from trae_agent.utils.output_manager import get_project_dir, _current_project
    target = name or _current_project
    if not target:
        console.print("[red]No project specified. Use: trae-cli project open <name>[/red]")
        sys.exit(1)
    project_dir = get_project_dir(target)
    if project_dir is None:
        console.print(f"[red]Project '{target}' not found.[/red]")
        sys.exit(1)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(project_dir)])
    elif sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(project_dir)])
    elif os.name == "nt":
        subprocess.Popen(["explorer", str(project_dir)])
    console.print(f"Opened: {project_dir}")


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
