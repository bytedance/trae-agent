import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from trae_agent.tools.base import Tool, ToolExecutor


def closing_tool(close):
    tool = MagicMock(spec=Tool)
    tool.close = close
    return tool


@pytest.mark.asyncio
async def test_close_waits_for_other_resources_before_propagating_an_error():
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    failure = RuntimeError("first resource failed to close")

    async def fail():
        await started.wait()
        raise failure

    async def close_slowly():
        started.set()
        await release.wait()
        finished.set()

    executor = ToolExecutor([closing_tool(fail), closing_tool(close_slowly)])
    task = asyncio.create_task(executor.close_tools())
    await started.wait()
    try:
        done, _ = await asyncio.wait({task}, timeout=0.02)
        assert not done, "cleanup returned while another resource was still open"
    finally:
        release.set()
        results = await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)
    assert finished.is_set()
    assert results == [failure]


@pytest.mark.asyncio
async def test_successful_cleanup_preserves_result_order():
    first = AsyncMock(return_value="first")
    second = AsyncMock(return_value="second")
    result = await ToolExecutor([closing_tool(first), closing_tool(second)]).close_tools()
    assert result == ["first", "second"]
    first.assert_awaited_once()
    second.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_executor_has_no_cleanup_results():
    assert await ToolExecutor([]).close_tools() == []


@pytest.mark.asyncio
async def test_cancelling_cleanup_still_cancels_inflight_closers():
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def close_until_cancelled():
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    task = asyncio.create_task(ToolExecutor([closing_tool(close_until_cancelled)]).close_tools())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
