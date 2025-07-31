# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Base Agent class for LLM-based agents."""

from abc import ABC, abstractmethod

from trae_agent.agent.agent_basics import AgentExecution, AgentState, AgentStep
from trae_agent.tools import tools_registry
from trae_agent.tools.base import Tool, ToolCall, ToolExecutor, ToolResult
from trae_agent.tools.ckg.ckg_database import clear_older_ckg
from trae_agent.utils.cli_console import CLIConsole
from trae_agent.utils.config import AgentConfig, ModelConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.utils.llm_clients.llm_client import LLMClient
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


class Agent(ABC):
    """Base class for LLM-based agents."""

    def __init__(self, agent_config: AgentConfig):
        """Initialize the agent.

        Args:
            agent_config: Configuration object containing model parameters and other settings.
        """
        self._llm_client = LLMClient(agent_config.model)
        self._model_config = agent_config.model
        self._max_steps = agent_config.max_steps

        self._initial_messages: list[LLMMessage] = []
        self._task: str = ""
        self._tools: list[Tool] = [
            tools_registry[tool_name](model_provider=self._model_config.model_provider.provider)
            for tool_name in agent_config.tools
        ]
        self._tool_caller: ToolExecutor = ToolExecutor([])
        self._cli_console: CLIConsole | None = None

        # Trajectory recorder
        self._trajectory_recorder: TrajectoryRecorder | None = None

        # CKG tool-specific: clear the older CKG databases
        clear_older_ckg()

    @property
    def llm_client(self) -> LLMClient:
        return self._llm_client

    @property
    def trajectory_recorder(self) -> TrajectoryRecorder | None:
        """Get the trajectory recorder for this agent."""
        return self._trajectory_recorder

    def _set_trajectory_recorder(self, recorder: TrajectoryRecorder | None) -> None:
        """Set the trajectory recorder for this agent."""
        self._trajectory_recorder = recorder
        # Also set it on the LLM client
        self._llm_client.set_trajectory_recorder(recorder)

    @property
    def cli_console(self) -> CLIConsole | None:
        """Get the CLI console for this agent."""
        return self._cli_console

    def set_cli_console(self, cli_console: CLIConsole | None) -> None:
        """Set the CLI console for this agent."""
        self._cli_console = cli_console

    @property
    def tools(self) -> list[Tool]:
        """Get the tools available to this agent."""
        return self._tools

    @property
    def task(self) -> str:
        """Get the current task of the agent."""
        return self._task

    @task.setter
    def task(self, value: str):
        """Set the current task of the agent."""
        self._task = value

    @property
    def initial_messages(self) -> list[LLMMessage]:
        """Get the initial messages for the agent."""
        return self._initial_messages

    @property
    def model_config(self) -> ModelConfig:
        """Get the model config for the agent."""
        return self._model_config

    @property
    def max_steps(self) -> int:
        """Get the maximum number of steps for the agent."""
        return self._max_steps

    @abstractmethod
    def new_task(
        self,
        task: str,
        extra_args: dict[str, str] | None = None,
        tool_names: list[str] | None = None,
    ):
        """Create a new task."""
        pass

    async def execute_task(self) -> AgentExecution:
        """Execute a task using the agent."""
        import time

        start_time = time.time()
        execution = AgentExecution(task=self._task, steps=[])
        step: AgentStep | None = None

        try:
            messages = self._initial_messages
            step_number = 1

            while step_number <= self._max_steps:
                step = self._create_new_step(step_number)
                try:
                    messages = await self._run_llm_step(step, messages, execution)
                    self._finalize_step(step, messages, execution)
                    if step.state == AgentState.COMPLETED:
                        break
                    step_number += 1
                except Exception as e:
                    self._handle_step_error(step, e, messages, execution)
                    break

            if step_number > self._max_steps and not execution.success:
                execution.final_result = "Task execution exceeded maximum steps without completion."

        except Exception as e:
            execution.final_result = f"Agent execution failed: {str(e)}"

        execution.execution_time = time.time() - start_time
        if step:
            self._update_cli_console(step)
        return execution

    def _create_new_step(self, step_number: int) -> AgentStep:
        return AgentStep(step_number=step_number, state=AgentState.THINKING)

    async def _run_llm_step(
        self, step: "AgentStep", messages: list["LLMMessage"], execution: "AgentExecution"
    ) -> list["LLMMessage"]:
        step.state = AgentState.THINKING
        self._update_cli_console(step)
        llm_response = self._llm_client.chat(messages, self._model_config, self._tools)
        step.llm_response = llm_response
        self._update_cli_console(step)
        self._update_llm_usage(llm_response, execution)

        if self.llm_indicates_task_completed(llm_response):
            if self._is_task_completed(llm_response):
                self._llm_complete_response_task_handler(llm_response, step, execution, messages)
                return messages
            else:
                step.state = AgentState.THINKING
                return [LLMMessage(role="user", content=self.task_incomplete_message())]
        else:
            tool_calls = llm_response.tool_calls
            return await self._tool_call_handler(tool_calls, step)

    def _finalize_step(
        self, step: "AgentStep", messages: list["LLMMessage"], execution: "AgentExecution"
    ) -> None:
        self._record_handler(step, messages)
        self._update_cli_console(step)
        execution.steps.append(step)

    def _handle_step_error(
        self,
        step: "AgentStep",
        error: Exception,
        messages: list["LLMMessage"],
        execution: "AgentExecution",
    ) -> None:
        step.state = AgentState.ERROR
        step.error = str(error)
        self._update_cli_console(step)
        self._record_handler(step, messages)
        self._update_cli_console(step)
        execution.steps.append(step)

    def reflect_on_result(self, tool_results: list[ToolResult]) -> str | None:
        """Reflect on tool execution result. Override for custom reflection logic."""
        if len(tool_results) == 0:
            return None

        reflection = "\n".join(
            f"The tool execution failed with error: {tool_result.error}. Consider trying a different approach or fixing the parameters."
            for tool_result in tool_results
            if not tool_result.success
        )

        return reflection

    def llm_indicates_task_completed(self, llm_response: LLMResponse) -> bool:
        """Check if the LLM indicates that the task is completed. Override for custom logic."""
        completion_indicators = [
            "task completed",
            "task finished",
            "done",
            "completed successfully",
            "finished successfully",
        ]

        response_lower = llm_response.content.lower()
        return any(indicator in response_lower for indicator in completion_indicators)

    def _is_task_completed(self, llm_response: LLMResponse) -> bool:  # pyright: ignore[reportUnusedParameter]
        """Check if the task is completed based on the response. Override for custom logic."""
        return True

    def task_incomplete_message(self) -> str:
        """Return a message indicating that the task is incomplete. Override for custom logic."""
        return "The task is incomplete. Please try again."

    def _update_cli_console(self, step: AgentStep) -> None:
        if self.cli_console:
            self.cli_console.update_status(step)

    def _update_llm_usage(self, llm_response: LLMResponse, execution: AgentExecution) -> None:
        if not llm_response.usage:
            return None
        # if execution.total_tokens is None then set it to be llm_response.usage else sum it up
        # execution.total_tokens is not None
        if not execution.total_tokens:
            execution.total_tokens = llm_response.usage
        else:
            execution.total_tokens += llm_response.usage
        return None

    def _llm_complete_response_task_handler(
        self,
        llm_response: LLMResponse,
        step: AgentStep,
        execution: AgentExecution,
        messages: list[LLMMessage],
    ) -> None:
        """
        update states
        """
        step.state = AgentState.COMPLETED
        execution.final_result = llm_response.content
        execution.success = True

        self._record_handler(step, messages)
        self._update_cli_console(step)
        execution.steps.append(step)

    def _record_handler(self, step: AgentStep, messages: list[LLMMessage]) -> None:
        if self.trajectory_recorder:
            self.trajectory_recorder.record_agent_step(
                step_number=step.step_number,
                state=step.state.value,
                llm_messages=messages,
                llm_response=step.llm_response,
                tool_calls=step.tool_calls,
                tool_results=step.tool_results,
                reflection=step.reflection,
                error=step.error,
            )

    async def _tool_call_handler(
        self, tool_calls: list[ToolCall] | None, step: AgentStep
    ) -> list[LLMMessage]:
        messages: list[LLMMessage] = []
        if not tool_calls or len(tool_calls) <= 0:
            messages = [
                LLMMessage(
                    role="user",
                    content="It seems that you have not completed the task.",
                )
            ]
            return messages

        step.state = AgentState.CALLING_TOOL
        step.tool_calls = tool_calls
        self._update_cli_console(step)

        if self._model_config.parallel_tool_calls:
            tool_results = await self._tool_caller.parallel_tool_call(tool_calls)
        else:
            tool_results = await self._tool_caller.sequential_tool_call(tool_calls)
        step.tool_results = tool_results
        self._update_cli_console(step)
        for tool_result in tool_results:
            # Add tool result to conversation
            message = LLMMessage(role="user", tool_result=tool_result)
            messages.append(message)

        reflection = self.reflect_on_result(tool_results)
        if reflection:
            step.state = AgentState.REFLECTING
            step.reflection = reflection

            # Display reflection
            self._update_cli_console(step)

            messages.append(LLMMessage(role="assistant", content=reflection))

        return messages
