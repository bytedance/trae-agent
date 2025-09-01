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
from trae_agent.utils.command_queue import CommandQueue, QueuedCommand, get_command_queue

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
    "--queue",
    "-q",
    is_flag=True,
    help="Add command to queue for sequential execution",
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
    queue: bool = False,
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

    # Apply backward compatibility for config file
    config_file = resolve_config_file(config_file)

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

    # 处理队列模式
    if queue:
        return _handle_queue_mode(
            task=task,
            working_dir=working_dir or os.getcwd(),
            options={
                "provider": provider,
                "model": model,
                "model_base_url": model_base_url,
                "api_key": api_key,
                "max_steps": max_steps,
                "must_patch": must_patch,
                "config_file": config_file,
                "trajectory_file": trajectory_file,
                "console_type": console_type,
                "agent_type": agent_type,
                "patch_path": patch_path,
            }
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

    agent = Agent(agent_type, config, trajectory_file, cli_console)

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

        console.print(f"\n[green]Trajectory saved to: {agent.trajectory_file}[/green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Task execution interrupted by user[/yellow]")
        console.print(f"[blue]Partial trajectory saved to: {agent.trajectory_file}[/blue]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
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
        console_type=selected_console_type, lakeview_config=config.lakeview, mode=console_mode
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


@cli.command()
def queue_status():
    """显示命令队列状态"""
    command_queue = get_command_queue()
    status = command_queue.get_queue_status()
    
    # 创建状态表格
    status_table = Table(title="命令队列状态")
    status_table.add_column("状态", style="cyan")
    status_table.add_column("数量", style="green")
    
    status_table.add_row("总计", str(status['total']))
    status_table.add_row("待执行", str(status['pending']))
    status_table.add_row("执行中", str(status['running']))
    status_table.add_row("已完成", str(status['completed']))
    status_table.add_row("失败", str(status['failed']))
    status_table.add_row("处理器运行中", "是" if status['is_processing'] else "否")
    
    if status['current_command']:
        status_table.add_row("当前命令", status['current_command'])
    
    console.print(status_table)
    
    # 显示命令列表
    commands = command_queue.get_commands()
    if commands:
        commands_table = Table(title="命令列表")
        commands_table.add_column("ID", style="cyan")
        commands_table.add_column("状态", style="yellow")
        commands_table.add_column("任务", style="green")
        commands_table.add_column("工作目录", style="blue")
        commands_table.add_column("创建时间", style="magenta")
        
        for cmd in commands[-10:]:  # 只显示最近10个命令
            from datetime import datetime
            created_time = datetime.fromtimestamp(cmd.created_at).strftime("%Y-%m-%d %H:%M:%S")
            task_preview = cmd.task[:50] + "..." if len(cmd.task) > 50 else cmd.task
            commands_table.add_row(
                cmd.id,
                cmd.status.value,
                task_preview,
                cmd.working_dir,
                created_time
            )
        
        console.print(commands_table)


@cli.command()
@click.argument("command_id")
def cancel_command(command_id: str):
    """取消指定的队列命令"""
    command_queue = get_command_queue()
    
    if command_queue.cancel_command(command_id):
        console.print(f"[green]成功取消命令: {command_id}[/green]")
    else:
        console.print(f"[red]无法取消命令: {command_id} (命令不存在或已在执行中)[/red]")


@cli.command()
def clear_completed():
    """清除已完成的队列命令"""
    command_queue = get_command_queue()
    cleared_count = command_queue.clear_completed()
    
    if cleared_count > 0:
        console.print(f"[green]已清除 {cleared_count} 个已完成的命令[/green]")
    else:
        console.print("[yellow]没有需要清除的已完成命令[/yellow]")


@cli.command()
def process_queue():
    """手动启动队列处理器"""
    command_queue = get_command_queue()
    status = command_queue.get_queue_status()
    
    if status['is_processing']:
        console.print("[yellow]队列处理器已在运行中[/yellow]")
        return
    
    if status['pending'] == 0:
        console.print("[yellow]队列中没有待执行的命令[/yellow]")
        return
    
    console.print("[blue]启动队列处理器...[/blue]")
    asyncio.run(command_queue.process_queue(_execute_queued_command))


def _handle_queue_mode(task: str, working_dir: str, options: dict) -> None:
    """处理队列模式的命令
    
    Args:
        task: 任务描述
        working_dir: 工作目录
        options: 命令选项
    """
    command_queue = get_command_queue()
    
    # 添加命令到队列
    command_id = command_queue.add_command(task, working_dir, options)
    console.print(f"[green]命令已添加到队列: {command_id}[/green]")
    console.print(f"[blue]任务: {task}[/blue]")
    
    # 检查队列状态
    status = command_queue.get_queue_status()
    
    # 如果处理器没有运行且有待执行的命令，启动队列处理器
    if not status['is_processing'] and status['pending'] > 0:
        console.print("[yellow]启动队列处理器...[/yellow]")
        asyncio.run(command_queue.process_queue(_execute_queued_command))
    else:
        # 显示队列状态
        console.print(f"[cyan]队列状态: {status['pending']} 待执行, {status['running']} 执行中, {status['completed']} 已完成[/cyan]")


async def _execute_queued_command(queued_command: QueuedCommand) -> None:
    """执行队列中的命令
    
    Args:
        queued_command: 队列中的命令对象
    """
    # 从队列命令中提取参数
    task = queued_command.task
    working_dir = queued_command.working_dir
    options = queued_command.options
    
    # 切换到指定工作目录
    original_cwd = os.getcwd()
    try:
        os.chdir(working_dir)
        
        # 创建配置
        config = Config.create(
            config_file=options.get('config_file', 'trae_config.yaml'),
        ).resolve_config_values(
            provider=options.get('provider'),
            model=options.get('model'),
            model_base_url=options.get('model_base_url'),
            api_key=options.get('api_key'),
            max_steps=options.get('max_steps'),
        )
        
        # 创建控制台
        console_type = options.get('console_type', 'simple')
        selected_console_type = (
            ConsoleType.SIMPLE if console_type.lower() == "simple" else ConsoleType.RICH
        )
        cli_console = ConsoleFactory.create_console(
            console_type=selected_console_type, mode=ConsoleMode.RUN
        )
        
        # 设置初始任务（如果是rich控制台）
        if selected_console_type == ConsoleType.RICH and hasattr(cli_console, "set_initial_task"):
            cli_console.set_initial_task(task)
        
        # 创建代理
        agent = Agent(
            options.get('agent_type', 'trae_agent'),
            config,
            options.get('trajectory_file'),
            cli_console
        )
        
        # 准备任务参数
        task_args = {
            "project_path": working_dir,
            "issue": task,
            "must_patch": "true" if options.get('must_patch', False) else "false",
            "patch_path": options.get('patch_path', ''),
        }
        
        # 设置代理上下文（如果是rich控制台）
        if selected_console_type == ConsoleType.RICH and hasattr(cli_console, "set_agent_context"):
            cli_console.set_agent_context(
                agent, 
                config.trae_agent, 
                options.get('config_file', 'trae_config.yaml'), 
                options.get('trajectory_file')
            )
        
        # 执行任务
        await agent.run(task, task_args)
        
    finally:
        # 恢复原始工作目录
        os.chdir(original_cwd)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
