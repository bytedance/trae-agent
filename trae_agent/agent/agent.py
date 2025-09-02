import asyncio
import contextlib
from enum import Enum

from trae_agent.utils.cli.cli_console import CLIConsole
from trae_agent.utils.config import AgentConfig, Config
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


class AgentType(Enum):
    TraeAgent = "trae_agent"


class Agent:
    def __init__(
        self,
        agent_type: AgentType | str,
        config: Config,
        trajectory_file: str | None = None,
        cli_console: CLIConsole | None = None,
        docker_config: dict | None = None,
        docker_keep: bool = True,
    ):
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type)
        self.agent_type: AgentType = agent_type

        # Set up trajectory recording
        if trajectory_file is not None:
            self.trajectory_file: str = trajectory_file
            self.trajectory_recorder: TrajectoryRecorder = TrajectoryRecorder(trajectory_file)
        else:
            # Auto-generate trajectory file path
            self.trajectory_recorder = TrajectoryRecorder()
            self.trajectory_file = self.trajectory_recorder.get_trajectory_path()

        match self.agent_type:
            case AgentType.TraeAgent:
                if config.trae_agent is None:
                    raise ValueError("trae_agent_config is required for TraeAgent")
                from .trae_agent import TraeAgent

                self.agent_config: AgentConfig = config.trae_agent

                self.agent: TraeAgent = TraeAgent(
                    self.agent_config, docker_config=docker_config, docker_keep=docker_keep
                )

                self.agent.set_cli_console(cli_console)

        if cli_console:
            if config.trae_agent.enable_lakeview:
                cli_console.set_lakeview(config.lakeview)
            else:
                cli_console.set_lakeview(None)

        self.agent.set_trajectory_recorder(self.trajectory_recorder)

    async def run(
        self,
        task: str,
        extra_args: dict[str, str] | None = None,
        tool_names: list[str] | None = None,
    ):
        self.agent.new_task(task, extra_args, tool_names)

        if self.agent.allow_mcp_servers:
            if self.agent.cli_console:
                self.agent.cli_console.print("Initialising MCP tools...")
            await self.agent.initialise_mcp()

        if self.agent.cli_console:
            task_details = {
                "Task": task,
                "Model Provider": self.agent_config.model.model_provider.provider,
                "Model": self.agent_config.model.model,
                "Max Steps": str(self.agent_config.max_steps),
                "Trajectory File": self.trajectory_file,
                "Tools": ", ".join([tool.name for tool in self.agent.tools]),
            }
            if extra_args:
                for key, value in extra_args.items():
                    task_details[key.capitalize()] = value
            self.agent.cli_console.print_task_details(task_details)

        cli_console_task = (
            asyncio.create_task(self.agent.cli_console.start()) if self.agent.cli_console else None
        )

        try:
            execution = await self.agent.execute_task()
        finally:
            # Ensure MCP cleanup happens even if execution fails
            with contextlib.suppress(Exception):
                await self.agent.cleanup_mcp_clients()

        if cli_console_task:
            await cli_console_task

        return execution
