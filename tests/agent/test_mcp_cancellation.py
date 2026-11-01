# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Cancellation must revoke admission to execution during MCP discovery."""

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from trae_agent.agent.agent import Agent
from trae_agent.utils.config import (
    Config,
    MCPServerConfig,
    ModelConfig,
    ModelProvider,
    TraeAgentConfig,
)


@pytest.fixture
def agent(tmp_path):
    model = ModelConfig(
        model="fake-model",
        model_provider=ModelProvider(api_key="test-only", provider="openai"),
        temperature=0,
        top_p=1,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=0,
    )
    config = Config(
        trae_agent=TraeAgentConfig(
            model=model,
            max_steps=1,
            tools=[],
            enable_lakeview=False,
            allow_mcp_servers=["ready", "blocked", "later"],
            mcp_servers_config={
                name: MCPServerConfig(command="unused", args=[])
                for name in ["ready", "blocked", "later"]
            },
        )
    )
    with (
        patch("trae_agent.agent.base_agent.LLMClient") as model_client,
        patch("trae_agent.agent.base_agent.clear_older_ckg"),
    ):
        model_client.return_value.provider.value = "openai"
        runner = Agent("trae_agent", config, trajectory_file=str(tmp_path / "trace.json"))
    runner.agent.execute_task = AsyncMock(return_value="execution-result")
    return runner


def discovery_client(started, events, *, failure=False, cleanup_failure=False):
    class Client:
        async def connect_and_discover(self, name, config, tools, provider):
            self.name = name
            events.append(("connect", name))
            if name == "blocked":
                started.set()
                if failure:
                    raise RuntimeError("server unavailable")
                await asyncio.Event().wait()
            tools.append(SimpleNamespace(name=name))

        async def cleanup(self, name):
            events.append(("close", self.name))
            if cleanup_failure and self.name == "blocked":
                raise RuntimeError("close failed")

    return Client


@pytest.mark.parametrize("cancellation", ["parent", "deadline"])
@pytest.mark.parametrize("cleanup_failure", [False, True])
async def test_cancelled_discovery_never_enters_execution(agent, cancellation, cleanup_failure):
    started, events = asyncio.Event(), []
    deadline = asyncio.timeout(None)

    async def run():
        async with deadline:
            return await agent.run("test", {"project_path": "."}, tool_names=[])

    with patch(
        "trae_agent.agent.trae_agent.MCPClient",
        discovery_client(started, events, cleanup_failure=cleanup_failure),
    ):
        task = asyncio.create_task(run())
        await asyncio.wait_for(started.wait(), timeout=2)
        if cancellation == "parent":
            task.cancel("caller stopped")
        else:
            deadline.reschedule(asyncio.get_running_loop().time())
        # Await directly: gather(return_exceptions=True) constructs a new
        # CancelledError and can discard the original cancellation message.
        try:
            result = await task
        except (asyncio.CancelledError, TimeoutError) as error:
            result = error

    expected = asyncio.CancelledError if cancellation == "parent" else TimeoutError
    assert isinstance(result, expected), (result, events)
    if cancellation == "parent":
        assert result.args == ("caller stopped",)
    assert events == [
        ("connect", "ready"),
        ("connect", "blocked"),
        ("close", "blocked"),
        ("close", "ready"),
    ]
    agent.agent.execute_task.assert_not_awaited()
    assert agent.agent.mcp_clients == []
    assert agent.agent.tools == []


async def test_unavailable_server_is_still_skipped(agent):
    events = []
    with patch(
        "trae_agent.agent.trae_agent.MCPClient",
        discovery_client(asyncio.Event(), events, failure=True),
    ):
        assert await agent.run("test", {"project_path": "."}, tool_names=[]) == "execution-result"

    assert [name for event, name in events if event == "connect"] == ["ready", "blocked", "later"]
    assert sorted(name for event, name in events if event == "close") == [
        "blocked",
        "later",
        "ready",
    ]
    agent.agent.execute_task.assert_awaited_once()
    assert agent.agent.mcp_clients == []


async def test_initialization_error_releases_previously_connected_clients(agent):
    events = []

    async def fail_after_connecting():
        client = SimpleNamespace(cleanup=AsyncMock(side_effect=lambda name: events.append(name)))
        agent.agent.mcp_clients.append(client)
        raise RuntimeError("initialization failed")

    with (
        patch.object(agent.agent, "initialise_mcp", side_effect=fail_after_connecting),
        pytest.raises(RuntimeError, match="initialization failed"),
    ):
        await agent.run("test", {"project_path": "."}, tool_names=[])

    assert events == ["cleanup"]
    assert agent.agent.mcp_clients == []
    agent.agent.execute_task.assert_not_awaited()


async def test_run_without_mcp_still_executes(agent):
    agent.agent.allow_mcp_servers = []
    with patch.object(agent.agent, "initialise_mcp", new_callable=AsyncMock) as initialize:
        assert await agent.run("test", {"project_path": "."}, tool_names=[]) == "execution-result"
    initialize.assert_not_awaited()
    agent.agent.execute_task.assert_awaited_once()


async def test_execution_error_still_releases_clients(agent):
    client = SimpleNamespace(cleanup=AsyncMock())

    async def connect():
        agent.agent.mcp_clients.append(client)

    agent.agent.execute_task.side_effect = RuntimeError("execution failed")
    with (
        patch.object(agent.agent, "initialise_mcp", side_effect=connect),
        pytest.raises(RuntimeError, match="execution failed"),
    ):
        await agent.run("test", {"project_path": "."}, tool_names=[])
    client.cleanup.assert_awaited_once_with("cleanup")
    assert agent.agent.mcp_clients == []


@pytest.mark.parametrize("cancellation", ["parent", "deadline"])
async def test_real_stdio_clients_close_when_discovery_is_cancelled(agent, tmp_path, cancellation):
    """Exercise MCP's actual ClientSession/AnyIO exit stacks and child processes."""
    server = tmp_path / "server.py"
    server.write_text(
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "name, directory = sys.argv[1:]\n"
        "root = Path(directory)\n"
        "(root / (name + '.pid')).write_text(str(os.getpid()))\n"
        "for line in sys.stdin:\n"
        "    message = json.loads(line)\n"
        "    method = message.get('method')\n"
        "    if method == 'initialize':\n"
        "        result = {'protocolVersion': message['params']['protocolVersion'],\n"
        "                  'capabilities': {'tools': {}},\n"
        "                  'serverInfo': {'name': name, 'version': '1'}}\n"
        "    elif method == 'tools/list':\n"
        "        (root / (name + '.listing')).touch()\n"
        "        if name == 'blocked':\n"
        "            time.sleep(60)\n"
        "        result = {'tools': []}\n"
        "    else:\n"
        "        continue\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)\n"
    )
    agent.agent.mcp_servers_config = {
        name: MCPServerConfig(command=sys.executable, args=[str(server), name, str(tmp_path)])
        for name in ["ready", "blocked", "later"]
    }
    deadline = asyncio.timeout(None)

    async def run():
        async with deadline:
            return await agent.run("test", {"project_path": "."}, tool_names=[])

    async def wait_for_discovery():
        while not (tmp_path / "blocked.listing").exists():
            await asyncio.sleep(0.01)

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(wait_for_discovery(), timeout=10)
        if cancellation == "parent":
            task.cancel()
        else:
            deadline.reschedule(asyncio.get_running_loop().time())
        result = (await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=10))[
            0
        ]
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    expected = asyncio.CancelledError if cancellation == "parent" else TimeoutError
    assert isinstance(result, expected), result
    assert not (tmp_path / "later.pid").exists()
    agent.agent.execute_task.assert_not_awaited()
    assert agent.agent.mcp_clients == []
    for name in ["ready", "blocked"]:
        pid = int((tmp_path / f"{name}.pid").read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
