# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Base Agent class for LLM-based agents."""

from abc import ABC, abstractmethod

from ..tools.base import Tool, ToolCall, ToolExecutor, ToolResult
from ..utils.cli_console import CLIConsole
from ..utils.config import Config, ModelParameters
from ..utils.llm_basics import LLMMessage, LLMResponse
from ..utils.llm_client import LLMClient
from ..utils.trajectory_recorder import TrajectoryRecorder
from .agent_basics import AgentExecution, AgentState, AgentStep


class Agent(ABC):
    """Base class for LLM-based agents."""

    def __init__(self, config: Config):
        self.llm_client: LLMClient = LLMClient(
            config.default_provider, config.model_providers[config.default_provider]
        )
        self.max_steps: int = config.max_steps
        self.model_parameters: ModelParameters = config.model_providers[config.default_provider]
        self.initial_messages: list[LLMMessage] = []
        self.task: str = ""
        self.tools: list[Tool] = []
        self.tool_caller: ToolExecutor = ToolExecutor([])

        self.cli_console: CLIConsole | None = None

        # Trajectory recorder
        self.trajectory_recorder: TrajectoryRecorder | None = None

    def set_trajectory_recorder(self, recorder: TrajectoryRecorder | None) -> None:
        """Set the trajectory recorder for this agent."""
        self.trajectory_recorder = recorder
        # Also set it on the LLM client
        self.llm_client.set_trajectory_recorder(recorder)

    def set_cli_console(self, cli_console: CLIConsole | None) -> None:
        """Set the CLI console for this agent."""
        self.cli_console = cli_console

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

        execution = AgentExecution(task=self.task, steps=[])

        try:
            messages = self.initial_messages
            step_number = 1

            while step_number <= self.max_steps:
                step = AgentStep(step_number=step_number, state=AgentState.THINKING)

                try:
                    # Get LLM response
                    step.state = AgentState.THINKING

                    # Display thinking state
                    self._update_cli_console(step)

                    llm_response = self.llm_client.chat(messages, self.model_parameters, self.tools)
                    step.llm_response = llm_response

                    # Display step with LLM response
                    self._update_cli_console(step)

                    # Update token usage
                    self._update_llm_usage(llm_response, execution)

                    if self.llm_indicates_task_completed(llm_response):
                        if self._is_task_completed(llm_response):
                            self._llm_complete_response_task_handler(llm_response, step, execution , messages)
                            break
                        else:
                            step.state = AgentState.THINKING
                            messages = [
                                LLMMessage(role="user", content=self.task_incomplete_message())
                            ]
                    else:
                        # Check if the response contains a tool call
                        tool_calls = llm_response.tool_calls
                        messages = await self._tool_call_handler(tool_calls, step)

                    # Record agent step
                    self._record_handler(step, messages)
                    self._update_cli_console(step)

                    execution.steps.append(step)
                    step_number += 1

                except Exception as e:
                    step.state = AgentState.ERROR
                    step.error = str(e)

                    # Display error
                    self._update_cli_console(step)
                    # Record agent step
                    self._record_handler(step, messages)
                    self._update_cli_console(step)

                    execution.steps.append(step)
                    break

            if step_number > self.max_steps and not execution.success:
                execution.final_result = "Task execution exceeded maximum steps without completion."

        except Exception as e:
            execution.final_result = f"Agent execution failed: {str(e)}"

        execution.execution_time = time.time() - start_time

        # Display final summary
        self._update_cli_console(step)

        return execution

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
        if not llm_response:
            return None
        execution.total_tokens = (
            llm_response.usage
            if execution.total_tokens
            else llm_response.usage + execution.total_tokens
        )

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
        self, tool_calls: list[ToolCall]|None, step: AgentStep
    ) -> list[LLMMessage]:
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

        if self.model_parameters.parallel_tool_calls:
            tool_results = await self.tool_caller.parallel_tool_call(tool_calls)
        else:
            tool_results = await self.tool_caller.sequential_tool_call(tool_calls)
        step.tool_results = tool_results

        self._update_cli_console(step)
        messages = []
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

        return message
