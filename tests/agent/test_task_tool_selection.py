# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest
from unittest.mock import AsyncMock, patch

from trae_agent.agent.trae_agent import TraeAgent, TraeAgentToolNames
from trae_agent.tools.base import ToolCall, ToolExecResult, ToolResult
from trae_agent.tools.bash_tool import BashTool
from trae_agent.utils.config import ModelConfig, ModelProvider, TraeAgentConfig
from trae_agent.utils.llm_clients.llm_basics import LLMResponse


class TestTaskToolSelection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = TraeAgentConfig(
            allow_mcp_servers=[],
            mcp_servers_config={},
            max_steps=2,
            model=ModelConfig(
                model="test-model",
                model_provider=ModelProvider(api_key="test-key", provider="anthropic"),
                temperature=0,
                top_p=1,
                top_k=0,
                parallel_tool_calls=False,
                max_retries=1,
            ),
        )
        for target in (
            "trae_agent.agent.base_agent.LLMClient",
            "trae_agent.agent.base_agent.clear_older_ckg",
            "trae_agent.agent.base_agent.DockerManager",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bash_call = ToolCall(name="bash", call_id="bash-call", arguments={})

    async def run_bash_task(self, agent):
        advertised = []

        def chat(messages, model, tools):
            advertised.append([tool.name for tool in tools])
            calls = (
                [self.bash_call]
                if len(advertised) == 1
                else [ToolCall(name="task_done", call_id="done", arguments={})]
            )
            return LLMResponse(content="", tool_calls=calls)

        agent.llm_client.chat.side_effect = chat
        execution = await agent.execute_task()
        self.assertTrue(execution.success)
        self.assertEqual(len(advertised), 2)
        return execution.steps[0].tool_results[0], advertised[0]

    async def test_selection_changes_advertised_and_executable_tools_between_tasks(self):
        agent = TraeAgent(self.config)
        with patch.object(BashTool, "execute", new_callable=AsyncMock) as execute:
            execute.return_value = ToolExecResult(output="mocked bash")
            for names, expected, allowed in (
                (None, self.config.tools, True),
                (["task_done"], ["task_done"], False),
                ([], [], False),
                (None, self.config.tools, True),
            ):
                with self.subTest(tool_names=names):
                    execute.reset_mock()
                    agent.new_task("test", {"project_path": "/project"}, names)
                    result, advertised = await self.run_bash_task(agent)
                    self.assertEqual(advertised, expected)
                    self.assertEqual(result.success, allowed)
                    self.assertEqual(execute.await_count, int(allowed))
                    if not allowed:
                        self.assertIn("not found", result.error)

    async def test_empty_configuration_fallback_is_executable(self):
        self.config.tools = []
        agent = TraeAgent(self.config)
        agent.new_task("test", {"project_path": "/project"})
        with patch.object(BashTool, "execute", new_callable=AsyncMock) as execute:
            execute.return_value = ToolExecResult(output="mocked bash")
            result, advertised = await self.run_bash_task(agent)
            self.assertEqual(advertised, TraeAgentToolNames)
            self.assertTrue(result.success)
            execute.assert_awaited_once()

    async def test_additional_registered_tool_and_invalid_selection(self):
        agent = TraeAgent(self.config)
        agent.new_task("test", {"project_path": "/project"}, ["json_edit_tool"])
        self.assertEqual([tool.name for tool in agent.tools], ["json_edit_tool"])
        selected_tool = agent.tools[0]
        with self.assertRaisesRegex(ValueError, "unknown_tool"):
            agent.new_task("test", {"project_path": "/project"}, ["bash", "unknown_tool"])
        self.assertEqual([tool.name for tool in agent.tools], ["json_edit_tool"])
        with patch.object(selected_tool, "execute", new_callable=AsyncMock) as execute:
            execute.return_value = ToolExecResult(output="mocked edit")
            results = await agent._tool_caller.sequential_tool_call(
                [ToolCall(name="json_edit_tool", call_id="edit-call", arguments={})]
            )
            self.assertTrue(results[0].success)
            execute.assert_awaited_once()

    async def test_docker_selection_can_remove_and_restore_tools(self):
        agent = TraeAgent(self.config, docker_config={"workspace_dir": "/project"})
        docker_result = ToolResult(name="bash", call_id="bash-call", success=True, result="mocked")
        with (
            patch.object(
                agent._tool_caller, "_execute_in_docker", return_value=docker_result
            ) as docker,
            patch.object(BashTool, "execute", new_callable=AsyncMock) as host,
        ):
            for names, expected in (
                (None, True),
                (["task_done"], False),
                ([], False),
                (None, True),
            ):
                with self.subTest(tool_names=names):
                    docker.reset_mock()
                    agent.new_task("test", {"project_path": "/project"}, names)
                    result, _ = await self.run_bash_task(agent)
                    self.assertEqual(result.success, expected)
                    self.assertEqual(docker.call_count, int(expected))
                    host.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
