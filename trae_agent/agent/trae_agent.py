# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""TraeAgent for software engineering tasks."""

import asyncio
import os
import subprocess
from typing import override

from .base import Agent
from .agent_basics import AgentError, AgentExecution
from ..utils.config import Config
from ..utils.llm_basics import LLMMessage, LLMResponse
from ..tools.base import Tool, ToolExecutor, ToolResult
from ..tools import tools_registry

TraeAgentToolNames = [
    "str_replace_based_edit_tool",
    "sequentialthinking",
    "task_done",
    "bash"
]


class TraeAgent(Agent):
    """Trae Agent specialized for software engineering tasks."""

    def __init__(self, config: Config):
        self.project_path: str = ""
        self.base_commit: str | None = None
        self.must_patch: str = "false"
        self.patch_path: str | None = None
        super().__init__(config)

    def setup_trajectory_recording(self, trajectory_path: str | None = None) -> str:
        """Set up trajectory recording for this agent.

        Args:
            trajectory_path: Path to save trajectory file. If None, generates default path.

        Returns:
            The path where trajectory will be saved.
        """
        from ..utils.trajectory_recorder import TrajectoryRecorder

        recorder = TrajectoryRecorder(trajectory_path)
        self.set_trajectory_recorder(recorder)

        # Start recording with task info
        if hasattr(self, 'task') and self.task:
            recorder.start_recording(
                task=self.task,
                provider=self.llm_client.provider.value,
                model=self.model_parameters.model,
                max_steps=self.max_steps
            )

        return recorder.get_trajectory_path()

    @override
    def new_task(self, task: str, extra_args: dict[str, str] | None = None, tool_names: list[str] | None = None):
        """Create a new task."""
        self.task: str = task

        if tool_names is None:
            tool_names = TraeAgentToolNames
        self.tools: list[Tool] = [tools_registry[tool_name]() for tool_name in tool_names]
        self.tool_caller: ToolExecutor = ToolExecutor(self.tools)

        self.initial_messages: list[LLMMessage] = []
        self.initial_messages.append(LLMMessage(role="system", content=self.get_system_prompt()))

        user_message = ""
        if extra_args:
            if "project_path" in extra_args:
                user_message += f"[Project root path]:\n{extra_args['project_path']}\n\n"
                self.project_path = extra_args['project_path']
            else:
                raise AgentError("Project path is required")
            if "issue" in extra_args:
                user_message += f"[Problem statement]: We're currently solving the following issue within our repository. Here's the issue text:\n{extra_args['issue']}\n"
            if "base_commit" in extra_args:
                self.base_commit = extra_args['base_commit']
            if "must_patch" in extra_args:
                self.must_patch = extra_args['must_patch']
            if "patch_path" in extra_args:
                self.patch_path = extra_args['patch_path']
        else:
            raise AgentError("Project path and issue information are required.")

        self.initial_messages.append(
            LLMMessage(
                role="user",
                content=user_message
                )
            )

        # If trajectory recorder is set, start recording
        if self.trajectory_recorder:
            self.trajectory_recorder.start_recording(
                task=task,
                provider=self.llm_client.provider.value,
                model=self.model_parameters.model,
                max_steps=self.max_steps
            )

    @override
    async def execute_task(self) -> AgentExecution:
        """Execute the task and finalize trajectory recording."""
        if self.cli_console:
            console_task = asyncio.create_task(self.cli_console.start())
        else:
            console_task = None
        execution = await super().execute_task()
        if self.cli_console and console_task and not console_task.done():
            await console_task

        # Finalize trajectory recording if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.finalize_recording(
                success=execution.success,
                final_result=execution.final_result
            )

        if self.patch_path is not None:
            with open(self.patch_path, 'w') as patch_f:
                patch_f.write(self.get_git_diff())

        return execution

    def get_system_prompt(self) -> str:
        """Get the system prompt for TraeAgent."""
        return """You are an expert AI software engineering agent.
Your primary goal is to resolve a given GitHub issue by navigating the provided codebase, identifying the root cause of the bug, implementing a robust fix, and ensuring your changes are safe and well-tested.

Follow these steps methodically:

1.  Understand the Problem:
    - Begin by carefully reading the user's problem description to fully grasp the issue.
    - Identify the core components and expected behavior.

2.  Explore and Locate:
    - Use the available tools to explore the codebase.
    - Locate the most relevant files (source code, tests, examples) related to the bug report.

3.  Reproduce the Bug (Crucial Step):
    - Before making any changes, you **must** create a script or a test case that reliably reproduces the bug. This will be your baseline for verification.
    - Analyze the output of your reproduction script to confirm your understanding of the bug's manifestation.

4.  Debug and Diagnose:
    - Inspect the relevant code sections you identified.
    - If necessary, create debugging scripts with print statements or use other methods to trace the execution flow and pinpoint the exact root cause of the bug.

5.  Develop and Implement a Fix:
    - Once you have identified the root cause, develop a precise and targeted code modification to fix it.
    - Use the provided file editing tools to apply your patch. Aim for minimal, clean changes.

6.  Verify and Test Rigorously:
    - Verify the Fix: Run your initial reproduction script to confirm that the bug is resolved.
    - Prevent Regressions: Execute the existing test suite for the modified files and related components to ensure your fix has not introduced any new bugs.
    - Write New Tests: Create new, specific test cases (e.g., using `pytest`) that cover the original bug scenario. This is essential to prevent the bug from recurring in the future. Add these tests to the codebase.
    - Consider Edge Cases: Think about and test potential edge cases related to your changes.

7.  Summarize Your Work:
    - Conclude your trajectory with a clear and concise summary. Explain the nature of the bug, the logic of your fix, and the steps you took to verify its correctness and safety.

**Guiding Principle:** Act like a senior software engineer. Prioritize correctness, safety, and high-quality, test-driven development.

# GUIDE FOR HOW TO USE "sequential_thinking" TOOL:
- Your thinking should be thorough and so it's fine if it's very long. Set totalThoughts to at least 5, but setting it up to 25 is fine as well. You'll need more total thoughts when you are considering multiple possible solutions or root causes for an issue.
- Use this tool as much as you find necessary to improve the quality of your answers.
- You can run bash commands (like tests, a reproduction script, or 'grep'/'find' to find relevant context) in between thoughts.
- The sequential_thinking tool can help you break down complex problems, analyze issues step-by-step, and ensure a thorough approach to problem-solving.
- Don't hesitate to use it multiple times throughout your thought process to enhance the depth and accuracy of your solutions.

If you are sure the issue has been solved, you should call the `task_done` to finish the task."""

    @override
    def reflect_on_result(self, tool_results: list[ToolResult]) -> str | None:
        return None

    def get_git_diff(self) -> str:
        """Get the git diff of the project."""
        pwd = os.getcwd()
        os.chdir(self.project_path)
        try:
            if not self.base_commit:
                stdout = subprocess.check_output(['git', '--no-pager', 'diff']).decode()
            else:
                stdout = subprocess.check_output(['git', '--no-pager', 'diff', self.base_commit, 'HEAD']).decode()
        except:
            stdout = ""
        finally:
            os.chdir(pwd)
        return stdout

    def remove_patches_to_tests(self, model_patch: str) -> str:
        """
        Remove any changes to the tests directory from the provided patch.
        This is to ensure that the model_patch does not disturb the repo's
        tests when doing acceptance testing with the `test_patch`.
        """
        lines = model_patch.splitlines(keepends=True)
        filtered_lines: list[str] = []
        is_tests = False

        for line in lines:
            if line.startswith("diff --git a/"):
                pieces = line.split()
                to = pieces[-1]
                if to.startswith("b/") and (
                    "/test/" in to
                    or "/tests/" in to
                    or "/testing/" in to
                    or "/test_" in to
                    or "/tox.ini" in to
                ):
                    is_tests = True
                else:
                    is_tests = False

            if not is_tests:
                filtered_lines.append(line)

        return "".join(filtered_lines)

    @override
    def llm_indicates_task_completed(self, llm_response: LLMResponse) -> bool:
        """Check if the LLM indicates that the task is completed."""
        if llm_response.tool_calls is None:
            return False
        for tool_call in llm_response.tool_calls:
            if tool_call.name == "task_done":
                return True
        return False

    @override
    def is_task_completed(self, llm_response: LLMResponse) -> bool:
        """Enhanced task completion detection."""
        if self.must_patch == "true":
            model_patch = self.get_git_diff()
            patch = self.remove_patches_to_tests(model_patch)
            if patch.strip() == "":
                return False

        return True

    @override
    def task_incomplete_message(self) -> str:
        """Return a message indicating that the task is incomplete."""
        return "ERROR! Your Patch is empty. Please provide a patch that fixes the problem."

    def cleanup(self):
        """Clean up resources used by the agent."""
        try:
            # Clean up tools that might have subprocess resources
            for tool in self.tools:
                if hasattr(tool, 'stop'):
                    try:
                        tool.stop()
                    except Exception:
                        pass
                if hasattr(tool, '_process') and tool._process is not None:
                    try:
                        if tool._process.returncode is None:
                            tool._process.terminate()
                    except Exception:
                        pass
        except Exception:
            # Ignore cleanup errors
            pass