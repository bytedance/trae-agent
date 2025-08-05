import asyncio
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
        trajectory_recorder: TrajectoryRecorder | str,
        cli_console: CLIConsole | None = None,
    ):
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type)
        self.agent_type: AgentType = agent_type
        self.trajectory_recorder: TrajectoryRecorder | str | None = trajectory_recorder
        match self.agent_type:
            case AgentType.TraeAgent:
                if config.trae_agent is None:
                    raise ValueError("trae_agent_config is required for TraeAgent")
                from .trae_agent import TraeAgent

                self.agent_config: AgentConfig = config.trae_agent

                self.agent: TraeAgent = TraeAgent(self.agent_config)
                self.agent.set_cli_console(cli_console)

        if isinstance(self.trajectory_recorder, str):
            self.trajectory_file: str = self.trajectory_recorder
            self.trajectory_recorder = TrajectoryRecorder(self.trajectory_recorder)
        else:
            self.trajectory_file = self.trajectory_recorder.trajectory_path.absolute().as_posix()

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
        task_details = {
            "Task": task,
            "Model Provider": self.agent_config.model.model_provider.provider,
            "Model": self.agent_config.model.model,
            "Max Steps": str(self.agent_config.max_steps),
            "Trajectory File": self.trajectory_file,
        }

        if extra_args:
            for key, value in extra_args.items():
                task_details[key.capitalize()] = value

        if self.agent.cli_console:
            self.agent.cli_console.print_task_details(task_details)

        self.agent.new_task(task, extra_args, tool_names)

        cli_console_task = (
            asyncio.create_task(self.agent.cli_console.start()) if self.agent.cli_console else None
        )

        execution = await self.agent.execute_task()

        if cli_console_task:
            await cli_console_task

        return execution
