# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the bash tool (safe IO, stall detection, session restart)."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from trae_agent.tools.base import ToolCallArguments, ToolExecResult
from trae_agent.tools.bash_tool import (
    INTERACTIVE_PROMPT_PATTERN_STRINGS,
    BashTool,
    _BashSession,
)


class TestInteractivePromptPatterns(unittest.TestCase):
    """Verify regex patterns match expected prompts and reject non-prompts."""

    def setUp(self):
        import re

        self.patterns = [re.compile(p, re.IGNORECASE) for p in INTERACTIVE_PROMPT_PATTERN_STRINGS]

    def _match_any(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)

    # --- Positive cases ---

    def test_yes_no_brackets(self):
        self.assertTrue(self._match_any("Proceed? [Y/n]"))
        self.assertTrue(self._match_any("[y/N]"))
        self.assertTrue(self._match_any("[Y/N]"))

    def test_yes_no_parentheses(self):
        self.assertTrue(self._match_any("(Y/n)"))
        self.assertTrue(self._match_any("(y/N)"))

    def test_yes_no_long(self):
        self.assertTrue(self._match_any("[yes/no]"))
        self.assertTrue(self._match_any("Yes/No"))
        self.assertTrue(self._match_any("yes / no"))

    def test_password_prompt(self):
        self.assertTrue(self._match_any("password:"))
        self.assertTrue(self._match_any("Password: "))
        self.assertTrue(self._match_any("passphrase:"))
        self.assertTrue(self._match_any("Passphrase: "))

    def test_confirm_prompt(self):
        self.assertTrue(self._match_any("[confirm]"))
        self.assertTrue(self._match_any("Continue?"))
        self.assertTrue(self._match_any("continue?"))
        self.assertTrue(self._match_any("Proceed?"))
        self.assertTrue(self._match_any("proceed?"))

    def test_are_you_sure(self):
        self.assertTrue(self._match_any("Are you sure you want to continue?"))
        self.assertTrue(self._match_any("are you sure?"))

    def test_press_any_key(self):
        self.assertTrue(self._match_any("Press any key to continue"))
        self.assertTrue(self._match_any("press any key"))

    def test_enter_to_continue(self):
        self.assertTrue(self._match_any("Enter to continue"))
        self.assertTrue(self._match_any("enter to continue"))

    # --- Negative cases (should NOT match) ---

    def test_regular_output_no_match(self):
        self.assertFalse(self._match_any("hello world"))
        self.assertFalse(self._match_any("ls -la"))
        self.assertFalse(self._match_any(""))

    def test_error_messages_no_match(self):
        self.assertFalse(self._match_any("Error: command not found"))
        self.assertFalse(self._match_any("Permission denied"))
        self.assertFalse(self._match_any("connection refused"))

    def test_code_output_no_match(self):
        self.assertFalse(self._match_any("int main() {"))
        self.assertFalse(self._match_any("if (x > 0) {"))
        self.assertFalse(self._match_any("const password = 'secret'"))

    def test_log_output_no_match(self):
        self.assertFalse(self._match_any("[INFO] Starting build"))
        self.assertFalse(self._match_any("[WARN] Continue without validation"))


def _make_mock_process() -> MagicMock:
    """Create a minimal mock process for _BashSession testing."""
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.returncode = None
    proc.pid = 99999
    return proc


def _make_sentinel_output(session: _BashSession, error_code: int, body: str = "") -> bytes:
    """Format mock process output with the correct sentinel banner."""
    sentinel = session._sentinel.replace("__ERROR_CODE__", str(error_code))
    return f"{body}\n{sentinel}\n".encode()


class TestBashSessionStallDetection(unittest.IsolatedAsyncioTestCase):
    """Test stall detection and interactive prompt handling in _BashSession.run()."""

    def setUp(self):
        self.session = _BashSession()
        self.session._started = True
        self.session._process = _make_mock_process()
        self.session._output_delay = 0.01  # speed up tests
        self.session._restart_session = AsyncMock()  # prevent real process killing

    async def test_normal_command_completion(self):
        """Normal command with sentinel should complete normally."""
        data = _make_sentinel_output(self.session, 0, "hello world")

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(data)
            return bytearray()

        async def mock_stderr():
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        result = await self.session.run("echo hello")
        self.assertEqual(result.output, "hello world")
        self.assertEqual(result.error_code, 0)
        self.assertFalse(result.partial)

    async def test_interactive_prompt_detection(self):
        """Command blocked on [Y/n] should detect and return partial."""

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(b"Some output\nProceed? [Y/n] ")
            return bytearray()

        async def mock_stderr():
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        result = await self.session.run("apt-get install something")
        self.assertTrue(result.partial)
        self.assertIn("Proceed? [Y/n]", result.output)
        self.assertIn("interactive prompt", result.error.lower())
        self.assertEqual(result.error_code, -1)

    async def test_password_prompt_detection(self):
        """Password prompt should be detected."""

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(b"Enter password: ")
            return bytearray()

        async def mock_stderr():
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        result = await self.session.run("some command")
        self.assertTrue(result.partial)
        self.assertIn("password", result.error.lower())

    async def test_non_interactive_stall_times_out_with_restart(self):
        """A command that stalls without an interactive prompt should restart on timeout."""

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(b"Starting long operation...\n")
            return bytearray()

        async def mock_stderr():
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        with patch.object(self.session, "_timeout", 0.05):
            result = await self.session.run("long command")

        self.assertTrue(result.partial)
        self.assertIn("timeout", result.error.lower())

    async def test_sentinel_with_stderr(self):
        """Command producing stderr should capture it correctly."""
        data = _make_sentinel_output(self.session, 1, "output")

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(data)
            return bytearray()

        async def mock_stderr():
            if not getattr(mock_stderr, "called", False):
                mock_stderr.called = True
                return bytearray(b"warning: something\n")
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        result = await self.session.run("invalid command")
        self.assertEqual(result.error_code, 1)
        self.assertIn("warning", result.error)
        self.assertFalse(result.partial)


class TestBashSessionAutoRestart(unittest.IsolatedAsyncioTestCase):
    """Test that _BashSession restarts correctly after process death."""

    def setUp(self):
        self.session = _BashSession()
        self.session._started = True
        self.session._process = _make_mock_process()
        self.session._process.returncode = 1  # Process has exited
        self.session._process.pid = 88888

    async def test_restart_on_dead_process(self):
        """If process is dead, _restart_session should be called and run retried."""

        # Mock _restart_session to create a working mock process
        async def _fake_restart():
            self.session._process = _make_mock_process()
            self.session._process.returncode = None
            self.session._started = True

        self.session._restart_session = _fake_restart

        data = _make_sentinel_output(self.session, 0, "output")

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(data)
            return bytearray()

        async def mock_stderr():
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        result = await self.session.run("echo hello")
        self.assertEqual(result.error_code, 0)
        self.assertIn("output", result.output)


class TestBashToolExecuteRetry(unittest.IsolatedAsyncioTestCase):
    """Test that BashTool.execute() retries on session errors."""

    def setUp(self):
        self.tool = BashTool()

    async def asyncTearDown(self):
        if self.tool._session:
            await self.tool._session.stop()

    async def test_retry_on_run_exception(self):
        """If session.run() raises, execute() should restart and retry once."""
        initial_session = AsyncMock()
        initial_session.run = AsyncMock(side_effect=RuntimeError("session died"))
        self.tool._session = initial_session

        retry_session = AsyncMock()
        retry_session.run = AsyncMock(return_value=ToolExecResult(output="retry ok", error_code=0))

        with patch("trae_agent.tools.bash_tool._BashSession", return_value=retry_session):
            result = await self.tool.execute(ToolCallArguments({"command": "echo hello"}))

        self.assertEqual(result.output, "retry ok")
        self.assertEqual(result.error_code, 0)

    async def test_retry_fails_gracefully(self):
        """If both original and retry fail, return error gracefully."""
        initial_session = AsyncMock()
        initial_session.run = AsyncMock(side_effect=RuntimeError("session died"))
        self.tool._session = initial_session

        retry_session = AsyncMock()
        retry_session.run = AsyncMock(side_effect=RuntimeError("retry also failed"))

        with patch("trae_agent.tools.bash_tool._BashSession", return_value=retry_session):
            result = await self.tool.execute(ToolCallArguments({"command": "echo hello"}))

        self.assertIn("error", result.error.lower())
        self.assertEqual(result.error_code, -1)

    async def test_successful_execution(self):
        """Normal execution should work."""
        result = await self.tool.execute(ToolCallArguments({"command": "echo hello world"}))
        self.assertEqual(result.error_code, 0)
        self.assertIn("hello world", result.output)
        self.assertEqual(result.error, "")

    async def test_session_restart(self):
        """Explicit restart should work."""
        await self.tool.execute(ToolCallArguments({"command": "echo first"}))
        self.assertIsNotNone(self.tool._session)

        result = await self.tool.execute(ToolCallArguments({"restart": True}))
        self.assertIn("restarted", result.output.lower())

        result = await self.tool.execute(ToolCallArguments({"command": "echo new session"}))
        self.assertIn("new session", result.output)

    async def test_missing_command(self):
        """No command should return error."""
        result = await self.tool.execute(ToolCallArguments({}))
        self.assertIn("no command provided", result.error.lower())
        self.assertEqual(result.error_code, -1)

    async def test_command_error(self):
        """Invalid command should report error."""
        result = await self.tool.execute(ToolCallArguments({"command": "invalid_command_123"}))
        self.assertTrue(any(s in result.error.lower() for s in ["not found", "not recognized"]))
        self.assertNotEqual(result.error_code, 0)


class TestBashToolPartialPropagation(unittest.IsolatedAsyncioTestCase):
    """Test that ToolExecResult.partial is correctly propagated."""

    def setUp(self):
        self.tool = BashTool()

    async def asyncTearDown(self):
        if self.tool._session:
            await self.tool._session.stop()

    async def test_normal_result_not_partial(self):
        """A normal command completion should not be marked partial."""
        result = await self.tool.execute(ToolCallArguments({"command": "echo hello"}))
        self.assertFalse(result.partial)

    async def test_session_restart_not_partial(self):
        """Restart result should not be marked partial."""
        result = await self.tool.execute(ToolCallArguments({"restart": True}))
        self.assertFalse(result.partial)


class TestDockerInteractiveDetection(unittest.TestCase):
    """Verify that the interactive prompt patterns are importable by docker_manager."""

    def test_interactive_prompt_import_exists(self):
        """INTERACTIVE_PROMPT_PATTERN_STRINGS should be importable and contain key patterns."""
        from trae_agent.tools.bash_tool import INTERACTIVE_PROMPT_PATTERN_STRINGS as patterns

        self.assertIsInstance(patterns, list)
        self.assertGreater(len(patterns), 0)
        # Check that password-related pattern exists (the raw pattern is [Pp]assword\s*[:：])
        combined = " ".join(patterns)
        self.assertIn(r"assword", combined)  # partial match of [Pp]assword
        self.assertIn(r"ontinue", combined)  # partial match of [Cc]ontinue


class TestCheckInteractivePrompt(unittest.IsolatedAsyncioTestCase):
    """Test the _check_interactive_prompt method directly."""

    def setUp(self):
        self.session = _BashSession()

    def test_matches_prompt_in_tail(self):
        """Prompt at the end of output should be detected."""
        result = self.session._check_interactive_prompt("Downloading packages...\nProceed? [Y/n] ")
        self.assertIsNotNone(result)
        self.assertIn("[Y/n]", result)

    def test_no_match_for_normal_output(self):
        """Normal command output should not match."""
        result = self.session._check_interactive_prompt(
            "total 42\n-rw-r--r--  1 user  staff  1024 May 10 12:00 file.txt"
        )
        self.assertIsNone(result)

    def test_match_in_long_output(self):
        """Prompt in last 200 chars of long output should be detected."""
        long_output = "A" * 500 + "\nContinue? (Y/n) "
        result = self.session._check_interactive_prompt(long_output)
        self.assertIsNotNone(result)
        # result is the match group (Y/n), verify it matched something meaningful
        self.assertIn("Y/n", result)

    def test_match_in_short_output(self):
        """Prompt in short output should be detected."""
        result = self.session._check_interactive_prompt("Password: ")
        self.assertIsNotNone(result)


class TestStallDetectionEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Test stall detection edge cases."""

    def setUp(self):
        self.session = _BashSession()
        self.session._started = True
        self.session._process = _make_mock_process()
        self.session._output_delay = 0.01
        self.session._restart_session = AsyncMock()

    async def test_stall_without_prompt_times_out(self):
        """Stall without interactive prompt should timeout (not trigger partial return early)."""

        async def mock_stdout():
            if not getattr(mock_stdout, "called", False):
                mock_stdout.called = True
                return bytearray(b"computing...\n")
            return bytearray()

        async def mock_stderr():
            return bytearray()

        self.session._read_stdout_available = mock_stdout
        self.session._read_stderr_available = mock_stderr

        with patch.object(self.session, "_timeout", 0.1):
            result = await self.session.run("long command")

        self.assertTrue(result.partial)
        self.assertIn("timeout", result.error.lower())

    async def test_check_interactive_prompt_directly(self):
        """Direct _check_interactive_prompt test for non-prompt stall."""
        result = self.session._check_interactive_prompt("computing...\nstill computing...\n")
        self.assertIsNone(result)


class TestPartialFieldInBase(unittest.TestCase):
    """Verify ToolExecResult carries the partial field."""

    def test_partial_default_is_false(self):
        r = ToolExecResult(output="hello")
        self.assertFalse(r.partial)

    def test_partial_can_be_true(self):
        r = ToolExecResult(output="partial", error="blocked", error_code=-1, partial=True)
        self.assertTrue(r.partial)


if __name__ == "__main__":
    unittest.main()
