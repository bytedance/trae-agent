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

from .base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter


class _BashSession:
    """A session of a bash shell."""

    _started: bool
    _timed_out: bool

    command: str = "/bin/bash"
    _output_delay: float = 0.2  # seconds
    _timeout: float = 120.0  # seconds
    _sentinel: str = "<<exit>>"

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
                "cmd.exe",
                shell=True,
                bufsize=0,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        self._started = True

    def stop(self) -> None:
        """Terminate the bash shell."""
        if not self._started:
            raise ToolError("Session has not started.")
        if self._process is None:
            return
        if self._process.returncode is not None:
            return
        self._process.terminate()

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

        # send command to the process
        self._process.stdin.write(command.encode() + f"; echo '{self._sentinel}'\n".encode())
        await self._process.stdin.drain()

        # read output from the process, until the sentinel is found
        try:
            async with asyncio.timeout(self._timeout):
                while True:
                    await asyncio.sleep(self._output_delay)
                    # if we read directly from stdout/stderr, it will wait forever for
                    # EOF. use the StreamReader buffer directly instead.
                    output: str = self._process.stdout._buffer.decode()  # type: ignore[attr-defined] # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
                    if self._sentinel in output:
                        # strip the sentinel and break
                        output = output[: output.index(self._sentinel)]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                        break
        except asyncio.TimeoutError:
            self._timed_out = True
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            ) from None

        if output.endswith("\n"):  # pyright: ignore[reportUnknownMemberType]
            output = output[:-1]  # pyright: ignore[reportUnknownVariableType]

        error: str = self._process.stderr._buffer.decode()  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportAttributeAccessIssue]
        if error.endswith("\n"):  # pyright: ignore[reportUnknownMemberType]
            error = error[:-1]  # pyright: ignore[reportUnknownVariableType]

        error_code = self._process.returncode if self._process.returncode is not None else 0

        # clear the buffers so that the next output can be read correctly
        self._process.stdout._buffer.clear()  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        self._process.stderr._buffer.clear()  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]

        return ToolExecResult(output=output, error=error, error_code=error_code)  # pyright: ignore[reportUnknownArgumentType]


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
                self._session.stop()
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
