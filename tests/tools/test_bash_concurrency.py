# SPDX-License-Identifier: MIT

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from trae_agent.tools.base import ToolCall, ToolExecResult, ToolExecutor
from trae_agent.tools.bash_tool import BashTool, _BashSession


class TestBashSessionConcurrency(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.pending = []
        self.session = MagicMock(spec=_BashSession)
        self.session.start = AsyncMock()
        self.session.stop = AsyncMock()

        async def run(command):
            self.entered.set()
            await self.release.wait()
            return ToolExecResult(output=command)

        self.session.run = AsyncMock(side_effect=run)
        self.tool = BashTool()
        self.tool._session = self.session

    async def asyncTearDown(self):
        self.release.set()
        await asyncio.gather(*self.pending, return_exceptions=True)
        await self.tool.close()

    async def test_parallel_first_use_waits_for_session_start(self):
        self.tool._session = None

        async def start():
            self.entered.set()
            await self.release.wait()

        self.session.start.side_effect = start
        with patch("trae_agent.tools.bash_tool._BashSession", return_value=self.session):
            task = asyncio.create_task(
                ToolExecutor([self.tool]).parallel_tool_call(
                    [
                        ToolCall("bash", "one", {"command": "one"}),
                        ToolCall("bash", "two", {"command": "two"}),
                    ]
                )
            )
            self.pending.append(task)
            await asyncio.wait_for(self.entered.wait(), timeout=1)
            self.session.run.assert_not_awaited()
            self.release.set()
            results = await task
        self.session.start.assert_awaited_once()
        self.assertEqual([result.result for result in results], ["one", "two"])

    async def test_close_waits_for_running_command(self):
        command = asyncio.create_task(self.tool.execute({"command": "one"}))
        self.pending.append(command)
        await asyncio.wait_for(self.entered.wait(), timeout=1)
        closing = asyncio.create_task(self.tool.close())
        self.pending.append(closing)
        await asyncio.sleep(0)
        self.session.stop.assert_not_awaited()
        self.release.set()
        self.assertEqual((await command).output, "one")
        await closing
        self.session.stop.assert_awaited_once()
        self.assertIsNone(self.tool._session)

    async def test_restart_waits_for_running_command(self):
        command = asyncio.create_task(self.tool.execute({"command": "one"}))
        self.pending.append(command)
        await asyncio.wait_for(self.entered.wait(), timeout=1)
        replacement = MagicMock(spec=_BashSession)
        replacement.start = AsyncMock()
        replacement.stop = AsyncMock()
        with patch("trae_agent.tools.bash_tool._BashSession", return_value=replacement):
            restarting = asyncio.create_task(self.tool.execute({"restart": True}))
            self.pending.append(restarting)
            await asyncio.sleep(0)
            self.session.stop.assert_not_awaited()
            self.release.set()
            self.assertEqual((await command).output, "one")
            self.assertIn("restarted", (await restarting).output)
        self.session.stop.assert_awaited_once()
        replacement.start.assert_awaited_once()
        self.assertIs(self.tool._session, replacement)

    async def test_cancelled_waiter_does_not_touch_active_session(self):
        command = asyncio.create_task(self.tool.execute({"command": "one"}))
        self.pending.append(command)
        await asyncio.wait_for(self.entered.wait(), timeout=1)
        waiting = asyncio.create_task(self.tool.execute({"command": "two"}))
        self.pending.append(waiting)
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertEqual(self.session.run.await_count, 1)
        self.session.stop.assert_not_awaited()
        self.release.set()
        self.assertEqual((await command).output, "one")
        self.assertEqual((await self.tool.execute({"command": "three"})).output, "three")

    async def test_failed_command_does_not_block_next_call(self):
        self.session.run.side_effect = [RuntimeError("failed command"), ToolExecResult(output="ok")]
        first = await self.tool.execute({"command": "one"})
        self.assertEqual(first.error_code, -1)
        second = await asyncio.wait_for(self.tool.execute({"command": "two"}), timeout=1)
        self.assertEqual(second.output, "ok")

    async def test_independent_tools_can_run_concurrently(self):
        other_entered = asyncio.Event()

        async def other_run(command):
            other_entered.set()
            await self.release.wait()
            return ToolExecResult(output=command)

        other_session = MagicMock(spec=_BashSession)
        other_session.run = AsyncMock(side_effect=other_run)
        other_session.stop = AsyncMock()
        other = BashTool()
        other._session = other_session
        self.pending.extend(
            [
                asyncio.create_task(self.tool.execute({"command": "one"})),
                asyncio.create_task(other.execute({"command": "two"})),
            ]
        )
        await asyncio.wait_for(asyncio.gather(self.entered.wait(), other_entered.wait()), timeout=1)
        self.release.set()
        results = await asyncio.gather(*self.pending)
        self.assertEqual([result.output for result in results], ["one", "two"])
        await other.close()


class TestParallelBashCommands(unittest.IsolatedAsyncioTestCase):
    async def test_real_parallel_calls_keep_outputs_and_ids_separate(self):
        tool = BashTool()
        try:
            with patch.object(_BashSession, "_timeout", 3):
                warmup = await tool.execute({"command": "echo WARMUP"})
                self.assertEqual(warmup.error_code, 0)
                results = await ToolExecutor([tool]).parallel_tool_call(
                    [
                        ToolCall("bash", "one", {"command": "echo FIRST_RESULT"}),
                        ToolCall("bash", "two", {"command": "echo SECOND_RESULT"}),
                    ]
                )
            self.assertEqual([result.call_id for result in results], ["one", "two"])
            self.assertTrue(all(result.success for result in results), results)
            self.assertIn("FIRST_RESULT", results[0].result)
            self.assertNotIn("SECOND_RESULT", results[0].result)
            self.assertIn("SECOND_RESULT", results[1].result)
            self.assertNotIn("FIRST_RESULT", results[1].result)
        finally:
            await tool.close()
