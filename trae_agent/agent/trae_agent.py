# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""TraeAgent for software engineering tasks."""

import asyncio
import os
import subprocess
from typing import override

from ..prompt.agent_prompt import TRAE_AGENT_SYSTEM_PROMPT
from ..tools import tools_registry
from ..tools.base import Tool, ToolExecutor, ToolResult
from ..utils.config import Config
from ..utils.llm_basics import LLMMessage, LLMResponse
from ..utils.llm_client import LLMClient
from .agent_basics import AgentError, AgentExecution
from .base import Agent

TraeAgentToolNames = [
    "str_replace_based_edit_tool",
    "sequentialthinking",
    "json_edit_tool",
    "task_done",
    "bash",
]


class TraeAgent(Agent):
    """Trae Agent specialized for software engineering tasks."""

    def __init__(self, config: Config | None = None, llm_client: LLMClient | None = None):
        """Initialize TraeAgent.

        Args:
            config: Configuration object containing model parameters and other settings.
                   Required if llm_client is not provided.
            llm_client: Optional pre-configured LLMClient instance.
                       If provided, it will be used instead of creating a new one from config.
        """
        self.project_path: str = ""
        self.base_commit: str | None = None
        self.must_patch: str = "false"
        self.patch_path: str | None = None
        super().__init__(config=config, llm_client=llm_client)

    @classmethod
    @override
    def from_config(cls, config: Config) -> "TraeAgent":
        """Create a TraeAgent instance from a configuration object.

        This factory method provides the traditional config-based initialization
        while allowing for future customization of the instantiation process.

        Args:
            config: Configuration object containing model parameters and other settings.

        Returns:
            An instance of TraeAgent.
        """
        return cls(config=config)

    def setup_trajectory_recording(self, trajectory_path: str | None = None) -> str:
        """Set up trajectory recording for this agent.

        Args:
            trajectory_path: Path to save trajectory file. If None, generates default path.

        Returns:
            The path where trajectory will be saved.
        """
        from ..utils.trajectory_recorder import TrajectoryRecorder

        recorder = TrajectoryRecorder(trajectory_path)
        self._set_trajectory_recorder(recorder)

        return recorder.get_trajectory_path()

    @override
    def new_task(
        self,
        task: str,
        extra_args: dict[str, str] | None = None,
        tool_names: list[str] | None = None,
    ):
        """Create a new task."""
        self._task: str = task

        if tool_names is None:
            tool_names = TraeAgentToolNames

        # Get the model provider from the LLM client
        provider = self._llm_client.provider.value
        self._tools: list[Tool] = [
            tools_registry[tool_name](model_provider=provider) for tool_name in tool_names
        ]
        self._tool_caller: ToolExecutor = ToolExecutor(self._tools)

        self._initial_messages: list[LLMMessage] = []
        self._initial_messages.append(LLMMessage(role="system", content=self.get_system_prompt()))

        user_message = ""
        if not extra_args:
            raise AgentError("Project path and issue information are required.")
        if "project_path" not in extra_args:
            raise AgentError("Project path is required")

        self.project_path = extra_args.get("project_path", "")
        user_message += f"[Project root path]:\n{self.project_path}\n\n"

        if "issue" in extra_args:
            user_message += f"[Problem statement]: We're currently solving the following issue within our repository. Here's the issue text:\n{extra_args['issue']}\n"
        optional_attrs_to_set = ["base_commit", "must_patch", "patch_path"]
        for attr in optional_attrs_to_set:
            if attr in extra_args:
                setattr(self, attr, extra_args[attr])

        self._initial_messages.append(LLMMessage(role="user", content=user_message))

        # If trajectory recorder is set, start recording
        if self._trajectory_recorder:
            self._trajectory_recorder.start_recording(
                task=task,
                provider=self._llm_client.provider.value,
                model=self._model_parameters.model,
                max_steps=self._max_steps,
            )

    @override
    async def execute_task(self) -> AgentExecution:
        """Execute the task and finalize trajectory recording."""
        console_task = asyncio.create_task(self._cli_console.start()) if self._cli_console else None
        execution = await super().execute_task()
        if self._cli_console and console_task and not console_task.done():
            await console_task

        # Finalize trajectory recording if recorder is available
        if self._trajectory_recorder:
            self._trajectory_recorder.finalize_recording(
                success=execution.success, final_result=execution.final_result
            )

        if self.patch_path is not None:
            with open(self.patch_path, "w") as patch_f:
                patch_f.write(self.get_git_diff())

        return execution

    def get_system_prompt(self) -> str:
        """Get the system prompt for TraeAgent."""
        return TRAE_AGENT_SYSTEM_PROMPT

    @override
    def reflect_on_result(self, tool_results: list[ToolResult]) -> str | None:
        return None

    def get_git_diff(self) -> str:
        """Get the git diff of the project."""
        pwd = os.getcwd()
        if not os.path.isdir(self.project_path):
            return ""
        os.chdir(self.project_path)
        try:
            if not self.base_commit:
                stdout = subprocess.check_output(["git", "--no-pager", "diff"]).decode()
            else:
                stdout = subprocess.check_output(
                    ["git", "--no-pager", "diff", self.base_commit, "HEAD"]
                ).decode()
        except (subprocess.CalledProcessError, FileNotFoundError):
            stdout = ""
        finally:
            os.chdir(pwd)
        return stdout

    # Copyright (c) 2024 paul-gauthier
    # SPDX-License-Identifier: Apache-2.0
    # Original remove_patches_to_tests function was released under Apache-2.0 License, with the full license text
    # available at https://github.com/Aider-AI/aider-swe-bench/blob/6e98cd6c3b2cbcba12976d6ae1b07f847480cb74/LICENSE.txt
    # Original function is at https://github.com/Aider-AI/aider-swe-bench/blob/6e98cd6c3b2cbcba12976d6ae1b07f847480cb74/tests.py#L45

    def remove_patches_to_tests(self, model_patch: str) -> str:
        """
        Remove any changes to the tests directory from the provided patch.
        This is to ensure that the model_patch does not disturb the repo's
        tests when doing acceptance testing with the `test_patch`.
        """
        lines = model_patch.splitlines(keepends=True)
        filtered_lines: list[str] = []
        test_patterns = ["/test/", "/tests/", "/testing/", "test_", "tox.ini"]
        is_tests = False

        for line in lines:
            if line.startswith("diff --git a/"):
                target_path = line.split()[-1]
                is_tests = target_path.startswith("b/") and any(
                    p in target_path for p in test_patterns
                )

            if not is_tests:
                filtered_lines.append(line)

        return "".join(filtered_lines)

    @override
    def llm_indicates_task_completed(self, llm_response: LLMResponse) -> bool:
        """Check if the LLM indicates that the task is completed."""
        if llm_response.tool_calls is None:
            return False
        return any(tool_call.name == "task_done" for tool_call in llm_response.tool_calls)

    @override
    def _is_task_completed(self, llm_response: LLMResponse) -> bool:
        """Enhanced task completion detection."""
        if self.must_patch == "true":
            model_patch = self.get_git_diff()
            patch = self.remove_patches_to_tests(model_patch)
            if not patch.strip():
                return False

        return True

    @override
    def task_incomplete_message(self) -> str:
        """Return a message indicating that the task is incomplete."""
        return "ERROR! Your Patch is empty. Please provide a patch that fixes the problem."
