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
from typing import override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter


class _BashSession:
    """A session of a bash shell."""

    _started: bool
    _timed_out: bool

    command: str = "/bin/bash"
    _output_delay: float = 0.2  # seconds
    _timeout: float = 120.0  # seconds
    _sentinel: str = ",,,,bash-command-exit-__ERROR_CODE__-banner,,,,"  # `__ERROR_CODE__` will be replaced by `$?` or `!errorlevel!` later
    _stderr_sentinel: str = ",,,,bash-command-stderr-end-banner,,,,"

    def __init__(self) -> None:
        self._started = False
        self._timed_out = False
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self._started:
            return

        # Windows compatibility: os.setsid not available

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

    async def run(self, command: str) -> ToolExecResult:
        """Execute a command in the bash shell."""
        if not self._started or self._process is None:
            raise ToolError("Session has not started.")
        if self._process.returncode is not None:
            return ToolExecResult(
                error=f"bash has exited with returncode {self._process.returncode}. tool must be restarted.",
                error_code=-1,
            )
        if self._timed_out:
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            )

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
            + f"\n){command_sep} echo {self._sentinel.replace('__ERROR_CODE__', errcode_retriever)}".encode()
            + f"{command_sep} echo {self._stderr_sentinel} ".encode()
            + (b"1>&2\n" if os.name == "nt" else b">&2\n")
        )
        await self._process.stdin.drain()

        # Consume both streams while the command runs. Merely inspecting the
        # StreamReader buffers allows pipe backpressure to block large outputs
        # before the shell can write the sentinel.
        try:
            async with asyncio.timeout(self._timeout):
                stdout, stderr = await asyncio.gather(
                    self._read_until_marker(
                        self._process.stdout,
                        sentinel_after.encode(),
                    ),
                    self._read_until_marker(
                        self._process.stderr,
                        self._stderr_sentinel.encode(),
                    ),
                )
        except asyncio.TimeoutError:
            self._timed_out = True
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            ) from None

        output, pivot, error_code_str = stdout.decode().rpartition(sentinel_before)
        if not pivot or not error_code_str.isdecimal():
            raise ToolError("bash returned an invalid exit status banner")
        error_code = int(error_code_str)

        if output.endswith("\n"):  # pyright: ignore[reportUnknownMemberType]
            output = output[:-1]  # pyright: ignore[reportUnknownVariableType]

        error = stderr.decode()
        if error.endswith("\n"):  # pyright: ignore[reportUnknownMemberType]
            error = error[:-1]  # pyright: ignore[reportUnknownVariableType]

        return ToolExecResult(output=output, error=error, error_code=error_code)  # pyright: ignore[reportUnknownArgumentType]

    @staticmethod
    async def _read_until_marker(reader: asyncio.StreamReader, marker: bytes) -> bytes:
        """Read and consume a stream until marker is encountered."""
        output = bytearray()
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                raise ToolError("bash exited before returning a command result")
            output.extend(chunk)
            marker_index = output.find(marker)
            if marker_index != -1:
                return bytes(output[:marker_index])


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
        except Exception as e:
            return ToolExecResult(error=f"Error running bash command: {e}", error_code=-1)

    @override
    async def close(self):
        """Properly close self._process."""
        if self._session:
            ret = await self._session.stop()
            self._session = None
            return ret
