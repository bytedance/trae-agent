# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""TraeAgent for software engineering tasks."""

import asyncio
import contextlib
import os
import subprocess
from typing_extensions import override

from trae_agent.agent.agent_basics import AgentError, AgentExecution
from trae_agent.agent.base_agent import BaseAgent
from trae_agent.prompt.agent_prompt import TRAE_AGENT_SYSTEM_PROMPT
from trae_agent.tools import tools_registry
from trae_agent.tools.base import Tool, ToolResult
from trae_agent.utils.config import MCPServerConfig, TraeAgentConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.utils.mcp_client import MCPClient

TraeAgentToolNames = [
    "str_replace_based_edit_tool",
    "sequentialthinking",
    "json_edit_tool",
    "task_done",
    "bash",
]

# Plan mode: read-only tool set. file mutation tools are excluded.
TraeAgentPlanToolNames = [
    "bash",
    "sequentialthinking",
    "task_done",
]

# Plan mode system prompt — appended after the main prompt.
TRAE_AGENT_PLAN_PROMPT = """

# Plan Mode

You are currently running in **PLAN MODE** — a read-only exploration mode,
analogous to Claude Code's plan mode.

## Hard rules
- **Do NOT modify any files.** Do not use any file-edit / write tools.
- **Do NOT run mutation commands** (no `git commit`, `rm`, `mv`, install,
  curl-write, npm/pip install, etc.). bash is restricted to read-only
  inspection (cat, ls, grep, find, sed -n, head, tail, wc, file, tree).
- **Do NOT start long-running processes** (`python server.py`, `npm run dev`).

## What you SHOULD do
- Read the user's request carefully.
- Explore the repository: list files, grep for symbols, read key modules.
- Build a concrete plan: which files to change, what to change, why.
- Present the plan as a numbered list of steps.

## Output format

```
## Summary
<one-sentence goal>

## Steps
1. <step> — touches <file:line> — <reason>
2. ...

## Risks
- <risk + mitigation>

## Out of scope
- <explicitly NOT doing these things>
```
"""


class TraeAgent(BaseAgent):
    """Trae Agent specialized for software engineering tasks."""

    def __init__(
        self,
        trae_agent_config: TraeAgentConfig,
        docker_config: dict | None = None,
        docker_keep: bool = True,
    ):
        """Initialize TraeAgent.

        Args:
            config: Configuration object containing model parameters and other settings.
                   Required if llm_client is not provided.
            llm_client: Optional pre-configured LLMClient instance.
                       If provided, it will be used instead of creating a new one from config.
            docker_config: Optional configuration for running in a Docker environment.
        """
        self.project_path: str = ""
        self.base_commit: str | None = None
        self.must_patch: str = "false"
        self.patch_path: str | None = None
        self.mcp_servers_config: dict[str, MCPServerConfig] | None = (
            trae_agent_config.mcp_servers_config if trae_agent_config.mcp_servers_config else None
        )
        self.allow_mcp_servers: list[str] | None = (
            trae_agent_config.allow_mcp_servers if trae_agent_config.allow_mcp_servers else []
        )
        self.mcp_tools: list[Tool] = []
        self.mcp_clients: list[MCPClient] = []  # Keep track of MCP clients for cleanup
        self.docker_config = docker_config
        # Plan mode flag — restricts available tools and appends PLAN prompt.
        # Set externally before calling new_task().
        self.plan_mode: bool = False
        super().__init__(
            agent_config=trae_agent_config, docker_config=docker_config, docker_keep=docker_keep
        )

    async def initialise_mcp(self):
        """Async factory to create and initialize TraeAgent."""
        # Plan mode: skip MCP tool discovery — plan mode only allows read-only tools.
        if self.plan_mode:
            return
        await self.discover_mcp_tools()

        if self.mcp_tools:
            self._tools.extend(self.mcp_tools)

    async def discover_mcp_tools(self):
        if self.mcp_servers_config:
            for mcp_server_name, mcp_server_config in self.mcp_servers_config.items():
                # P1-6 修复:之前的逻辑是 `allow_mcp_servers is None → return`，
                # 这把"None = 不限制"误读成"None = 全部跳过",结果用户配
                # 了 MCP server 但不写 allow_mcp_servers 时,所有 server 都
                # 不会被发现。正确语义:
                #   - None  : 不限制 → 允许所有 server
                #   - []    : 显式空列表 → 拒绝所有 server
                #   - [a,b] : 仅允许列表中的 server
                if self.allow_mcp_servers is not None and (
                    not self.allow_mcp_servers
                    or mcp_server_name not in self.allow_mcp_servers
                ):
                    continue
                mcp_client = MCPClient()
                try:
                    await mcp_client.connect_and_discover(
                        mcp_server_name,
                        mcp_server_config,
                        self.mcp_tools,
                        self._llm_client.provider.value,
                    )
                    # Store client for later cleanup
                    self.mcp_clients.append(mcp_client)
                except Exception:
                    # Clean up failed client
                    with contextlib.suppress(Exception):
                        await mcp_client.cleanup(mcp_server_name)
                    continue
                except asyncio.CancelledError:
                    # If the task is cancelled, clean up and skip this server
                    with contextlib.suppress(Exception):
                        await mcp_client.cleanup(mcp_server_name)
                    continue
        else:
            return

    @override
    def new_task(
        self,
        task: str,
        extra_args: dict[str, str] | None = None,
        tool_names: list[str] | None = None,
    ):
        """Create a new task."""
        self._task: str = task

        # Decide which tools to instantiate for THIS task.
        #
        # P1-1 修复:之前条件是 `tool_names is None and len(self._tools) == 0`,
        # 但 BaseAgent.__init__ 已经把 agent_config.tools 实例化过了,所以
        # `len == 0` 几乎永不成立,plan_mode 永远走不到 TraeAgentPlanToolNames,
        # plan mode 实际失效。
        #
        # 新规则:
        #   1. 显式传 tool_names: 用它(完整覆盖)
        #   2. plan_mode 启用: 强制用 plan 工具集(覆盖既有)
        #   3. 否则: 保持 BaseAgent.__init__ 已建好的工具
        if tool_names is not None:
            chosen = tool_names
        elif self.plan_mode:
            chosen = TraeAgentPlanToolNames
        else:
            chosen = None

        if chosen is not None:
            provider = self._model_config.model_provider.provider
            self._tools: list[Tool] = []
            for t in chosen:
                # Plan mode: replace `bash` with the read-only variant.
                if t == "bash" and self.plan_mode:
                    from trae_agent.tools.bash_tool import ReadOnlyBashTool

                    self._tools.append(ReadOnlyBashTool(model_provider=provider))
                else:
                    # 传入 working_dir 让 edit 工具做越权防护(只允许落在 project 内)。
                    # 仅 edit 工具接受该参数,其余工具(BashTool 等)不接受,需区分。
                    wd = extra_args.get("project_path") if extra_args else None
                    if t == "str_replace_based_edit_tool":
                        tool = tools_registry[t](model_provider=provider, working_dir=wd)
                    else:
                        tool = tools_registry[t](model_provider=provider)
                    self._tools.append(tool)
            # 重新构造 tool_caller 以匹配新工具集
            from trae_agent.tools.base import ToolExecutor

            self._tool_caller = ToolExecutor(self._tools)

        # --- Validation (always needed) ---
        if not extra_args:
            raise AgentError("Project path and issue information are required.")
        if "project_path" not in extra_args:
            raise AgentError("Project path is required")
        self.project_path = extra_args.get("project_path", "")
        optional_attrs_to_set = ["base_commit", "must_patch", "patch_path"]
        for attr in optional_attrs_to_set:
            if attr in extra_args:
                setattr(self, attr, extra_args[attr])

        # --- Skills load + render prompt (always, for tool filtering below) ---
        skills: list = []
        skills_block: str = ""
        try:
            from trae_agent.skills.loader import (
                load_all_skills,
                skills_to_system_message,
            )

            skills = load_all_skills(
                project_dir=self.project_path if self.project_path else None
            )
            skills_block = skills_to_system_message(skills)
        except Exception:
            # Skills are optional; never fail the agent on a skill error.
            pass

        # --- Build initial messages (normal only) ---
        if self._resume_start_step <= 1:
            self._initial_messages: list[LLMMessage] = []
            self._initial_messages.append(
                LLMMessage(role="system", content=self.get_system_prompt())
            )
            if skills_block:
                self._initial_messages.append(
                    LLMMessage(role="system", content=skills_block)
                )

            user_message = ""
            if self.docker_config:
                user_message += r"[Project root path]:\workspace\n\n"
            else:
                user_message += f"[Project root path]:\n{self.project_path}\n\n"
            if "issue" in extra_args:
                user_message += (
                    "[Problem statement]: We're currently solving the following "
                    "issue within our repository. Here's the issue text:\n"
                    f"{extra_args['issue']}\n"
                )
            self._initial_messages.append(LLMMessage(role="user", content=user_message))
        # else: resume mode — _initial_messages already populated by
        # resume_from_messages(). Do NOT clobber them.

        # --- Skills tool filtering (P0) ---
        if skills:
            allowed = self._compute_skills_allowed_tools(skills)
            if allowed is not None and self._tools:
                filtered = [t for t in self._tools if t.name in allowed]
                if len(filtered) != len(self._tools):
                    self._tools = filtered
                    from trae_agent.tools.base import ToolExecutor

                    self._tool_caller = ToolExecutor(self._tools)

        # If trajectory recorder is set, start recording
        if self._trajectory_recorder:
            self._trajectory_recorder.start_recording(
                task=task,
                provider=self._llm_client.provider.value,
                model=self._model_config.model,
                max_steps=self._max_steps,
            )

    @staticmethod
    def _compute_skills_allowed_tools(skills: list) -> set[str] | None:
        """P0 修复:计算所有 skill 中 allowed_tools 交集,作为实际可用工具约束。

        若没有任何 skill 设定了 allowed_tools(或所有都为 None),返回 None
        表示不限制。若有 skill 设定了列表,则取**交集**。

        空交集意味着**没有任何工具可用**——调用方应 allowlist 为空,
        agent 将很快因无可用工具自然失败。
        """
        sets: list[set[str]] = []
        for s in skills:
            if hasattr(s, "allowed_tools") and s.allowed_tools is not None:
                sets.append(set(s.allowed_tools))
        if not sets:
            return None
        result = set.intersection(*sets)
        return result

    @override
    async def execute_task(self) -> AgentExecution:
        """Execute the task and finalize trajectory recording."""
        execution = await super().execute_task()

        # Finalize trajectory recording if recorder is available
        if self._trajectory_recorder:
            self._trajectory_recorder.finalize_recording(
                success=execution.success, final_result=execution.final_result
            )

        if self.patch_path is not None:
            with open(self.patch_path, "w") as patch_f:
                _ = patch_f.write(self.get_git_diff())

        return execution

    def get_system_prompt(self) -> str:
        """Get the system prompt for TraeAgent."""
        if self.plan_mode:
            return TRAE_AGENT_SYSTEM_PROMPT + TRAE_AGENT_PLAN_PROMPT
        return TRAE_AGENT_SYSTEM_PROMPT

    @override
    def reflect_on_result(self, tool_results: list[ToolResult]) -> str | None:
        return None

    def get_git_diff(self) -> str:
        """Get the git diff of the project.

        P1-6 修复:不再用 os.chdir 改全局 cwd(异步并发任务 A/B 互相串),
        改用 subprocess.run(..., cwd=self.project_path)。
        """
        if not os.path.isdir(self.project_path):
            return ""
        cmd = ["git", "--no-pager", "diff"]
        if self.base_commit:
            cmd += [self.base_commit, "HEAD"]
        try:
            return subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                check=False,
            ).stdout.decode()
        except FileNotFoundError:
            return ""

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

    @override
    async def cleanup_mcp_clients(self) -> None:
        """Clean up all MCP clients to prevent async context leaks."""
        for client in self.mcp_clients:
            with contextlib.suppress(Exception):
                # Use a generic server name for cleanup since we don't track which server each client is for
                await client.cleanup("cleanup")
        self.mcp_clients.clear()
