# Copyright (c) 2023 Anthropic
# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates.
# SPDX-License-Identifier: MIT
#
# This file has been modified by ByteDance Ltd. and/or its affiliates. on 13 June 2025
#
# Original file was released under MIT License, with the full license text
# available at https://github.com/anthropics/anthropic-quickstarts/blob/main/LICENSE
#
# This modified file is released under the same license.

import asyncio
import os
import re
import signal
from contextlib import suppress
from typing import override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter

# Regular expression patterns for detecting terminal interactive prompts.
# These match common patterns that cause commands to block waiting for user input.
INTERACTIVE_PROMPT_PATTERN_STRINGS: list[str] = [
    r"\[Y/n\]",
    r"\[y/N\]",
    r"\[Y/N\]",
    r"\(Y/n\)",
    r"\(y/N\)",
    r"\[yes/no\]",
    r"\[confirm\]",
    r"[Pp]assword\s*[:：]",
    r"[Pp]assphrase\s*[:：]",
    r"[Cc]ontinue\s*\?",
    r"[Pp]roceed\s*\?",
    r"[Pp]ress\s+any\s+key",
    r"[Ee]nter\s+to\s+continue",
    r"[Yy]es\s*/?\s*[Nn]o",
    r"[Aa]re\s+you\s+sure",
]

INTERACTIVE_PROMPT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in INTERACTIVE_PROMPT_PATTERN_STRINGS
]

# After this many consecutive empty polls (each at _output_delay), stall detection triggers.
# At 0.2s per poll, 5 polls ≈ 1 second of stall.
_STALL_POLL_LIMIT = 5


class _BashSession:
    """A session of a bash shell."""

    _started: bool

    command: str = "/bin/bash"
    _output_delay: float = 0.2  # seconds
    _timeout: float = 120.0  # seconds
    _sentinel: str = ",,,,bash-command-exit-__ERROR_CODE__-banner,,,,"  # `__ERROR_CODE__` will be replaced by `$?` or `!errorlevel!` later

    def __init__(self) -> None:
        self._started = False
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self._started:
            return

        if os.name != "nt":  # Unix-like systems
            self._process = await asyncio.create_subprocess_shell(
                self.command,
                shell=True,
                bufsize=0,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid,
            )
        else:
            self._process = await asyncio.create_subprocess_shell(
                "cmd.exe /v:on",  # enable delayed expansion to allow `echo !errorlevel!`
                shell=True,
                bufsize=0,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        self._started = True

    async def stop(self) -> None:
        """Terminate the bash shell."""
        if not self._started:
            raise ToolError("Session has not started.")
        if self._process is None:
            return
        if self._process.returncode is not None:
            return
        try:
            self._process.terminate()

            # Wait until the process has truly terminated.
            stdout, stderr = await asyncio.wait_for(self._process.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            self._process.kill()
            try:
                # Set a shorter timeout for the cleanup process
                stdout, stderr = await asyncio.wait_for(self._process.communicate(), timeout=2.0)
            except asyncio.TimeoutError:
                # If it still timeout, return None.
                return None
        except Exception:
            return None

    async def _read_stdout_available(self) -> bytearray:
        """Safely read all currently available data from stdout without blocking.

        Uses a short timeout to return immediately when no data is available,
        instead of blocking on the internal StreamReader buffer indefinitely.
        """
        data = bytearray()
        try:
            while self._process and self._process.stdout and not self._process.stdout.at_eof():
                chunk = await asyncio.wait_for(self._process.stdout.read(4096), timeout=0.005)
                if not chunk:
                    break
                data.extend(chunk)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        return data

    async def _read_stderr_available(self) -> bytearray:
        """Safely read all currently available data from stderr without blocking."""
        data = bytearray()
        try:
            while self._process and self._process.stderr and not self._process.stderr.at_eof():
                chunk = await asyncio.wait_for(self._process.stderr.read(4096), timeout=0.005)
                if not chunk:
                    break
                data.extend(chunk)
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
        return data

    async def _restart_session(self) -> None:
        """Forcefully kill the current session process and start a new one."""
        if self._process and self._process.pid is not None:
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                else:
                    self._process.kill()
            except (OSError, ProcessLookupError):
                pass
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._process.wait(), timeout=5.0)

        self._process = None
        self._started = False
        await self.start()

    def _check_interactive_prompt(self, output: str) -> str | None:
        """Check tail of output for interactive prompt patterns.

        Returns the matched pattern string, or None if no match.
        Only examines the last 200 characters for efficiency.
        """
        tail = output[-200:] if len(output) > 200 else output
        for pattern in INTERACTIVE_PROMPT_PATTERNS:
            match = pattern.search(tail)
            if match:
                return match.group()
        return None

    async def _restart_with_output(
        self, partial_stdout: str, partial_stderr: str, reason: str
    ) -> ToolExecResult:
        """Kill the stuck session and restart, returning partial output.

        This is used when a command blocks on an interactive prompt or times out.
        The session is transparently restarted so subsequent commands can proceed.
        """
        await self._restart_session()
        error_msg = f"Command blocked by interactive prompt ({reason}). Session restarted."
        if partial_stderr:
            error_msg += f"\nPartial stderr: {partial_stderr}"
        return ToolExecResult(
            output=partial_stdout,
            error=error_msg,
            error_code=-1,
            partial=True,
        )

    async def run(self, command: str) -> ToolExecResult:
        """Execute a command in the bash shell."""
        if not self._started or self._process is None:
            raise ToolError("Session has not started.")
        if self._process.returncode is not None:
            # Process has died — restart transparently and retry
            await self._restart_session()
            return await self.run(command)

        # we know these are not None because we created the process with PIPEs
        assert self._process.stdin
        assert self._process.stdout
        assert self._process.stderr

        error_code = 0

        sentinel_before, pivot, sentinel_after = self._sentinel.partition("__ERROR_CODE__")
        assert pivot == "__ERROR_CODE__"

        errcode_retriever = "!errorlevel!" if os.name == "nt" else "$?"
        command_sep = "&" if os.name == "nt" else ";"

        # send command to the process
        self._process.stdin.write(
            b"(\n"
            + command.encode()
            + f"\n){command_sep} echo {self._sentinel.replace('__ERROR_CODE__', errcode_retriever)}\n".encode()
        )
        await self._process.stdin.drain()

        # use bytearray accumulators instead of directly accessing internal _buffer
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        empty_polls = 0

        try:
            async with asyncio.timeout(self._timeout):
                while True:
                    await asyncio.sleep(self._output_delay)

                    # safely read available stdout data
                    new_stdout = await self._read_stdout_available()
                    if new_stdout:
                        stdout_buffer.extend(new_stdout)
                        empty_polls = 0
                    else:
                        empty_polls += 1

                    # also read stderr to avoid buffer blow-up
                    new_stderr = await self._read_stderr_available()
                    if new_stderr:
                        stderr_buffer.extend(new_stderr)

                    output = stdout_buffer.decode(errors="replace")

                    if sentinel_before in output:
                        # strip the sentinel from output
                        output, pivot, exit_banner = output.rpartition(sentinel_before)
                        assert pivot

                        # get error code inside banner
                        error_code_str, pivot, _ = exit_banner.partition(sentinel_after)
                        if not pivot or not error_code_str.isdecimal():
                            continue

                        error_code = int(error_code_str)
                        break

                    # Stall detection: if output hasn't grown for several polls,
                    # check whether the command is blocked on an interactive prompt.
                    if empty_polls >= _STALL_POLL_LIMIT:
                        matched = self._check_interactive_prompt(output)
                        if matched:
                            return await self._restart_with_output(
                                partial_stdout=output.rstrip("\n"),
                                partial_stderr=stderr_buffer.decode(errors="replace").rstrip("\n"),
                                reason=matched,
                            )
        except asyncio.TimeoutError:
            return await self._restart_with_output(
                partial_stdout=stdout_buffer.decode(errors="replace").rstrip("\n"),
                partial_stderr=stderr_buffer.decode(errors="replace").rstrip("\n"),
                reason=f"timeout after {self._timeout}s",
            )

        if output.endswith("\n"):
            output = output[:-1]

        stderr_output = stderr_buffer.decode(errors="replace")
        if stderr_output.endswith("\n"):
            stderr_output = stderr_output[:-1]

        return ToolExecResult(output=output, error=stderr_output, error_code=error_code)


class BashTool(Tool):
    """
    A tool that allows the agent to run bash commands.
    The tool parameters are defined by Anthropic and are not editable.
    """

    def __init__(self, model_provider: str | None = None):
        super().__init__(model_provider)
        self._session: _BashSession | None = None

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return "bash"

    @override
    def get_description(self) -> str:
        return """Run commands in a bash shell
* When invoking this tool, the contents of the "command" parameter does NOT need to be XML-escaped.
* You have access to a mirror of common linux and python packages via apt and pip.
* State is persistent across command calls and discussions with the user.
* To inspect a particular line range of a file, e.g. lines 10-25, try 'sed -n 10,25p /path/to/the/file'.
* Please avoid commands that may produce a very large amount of output.
* Please run long lived commands in the background, e.g. 'sleep 10 &' or start a server in the background.
"""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        # For OpenAI models, all parameters must be required=True
        # For other providers, optional parameters can have required=False
        restart_required = self.model_provider == "openai"

        return [
            ToolParameter(
                name="command",
                type="string",
                description="The bash command to run.",
                required=True,
            ),
            ToolParameter(
                name="restart",
                type="boolean",
                description="Set to true to restart the bash session.",
                required=restart_required,
            ),
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        if arguments.get("restart"):
            if self._session:
                await self._session.stop()
            self._session = _BashSession()
            await self._session.start()

            return ToolExecResult(output="tool has been restarted.")

        if self._session is None:
            try:
                self._session = _BashSession()
                await self._session.start()
            except Exception as e:
                return ToolExecResult(error=f"Error starting bash session: {e}", error_code=-1)

        command = str(arguments["command"]) if "command" in arguments else None
        if command is None:
            return ToolExecResult(
                error=f"No command provided for the {self.get_name()} tool",
                error_code=-1,
            )
        try:
            return await self._session.run(command)
        except Exception:
            # Implicit session restart and single retry
            try:
                self._session = _BashSession()
                await self._session.start()
                return await self._session.run(command)
            except Exception as e2:
                return ToolExecResult(error=f"Error running bash command: {e2}", error_code=-1)

    @override
    async def close(self):
        """Properly close self._process."""
        if self._session:
            ret = await self._session.stop()
            self._session = None
            return ret
