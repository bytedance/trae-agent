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

"""Utility to run shell commands asynchronously with a timeout."""

import asyncio
import contextlib

from daytona import Sandbox, SessionExecuteRequest

TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>"
MAX_RESPONSE_LEN: int = 16000


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN):
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


async def run(
    cmd: str,
    timeout: float | None = 120.0,  # seconds
    truncate_after: int | None = MAX_RESPONSE_LEN,
):
    """Run a shell command asynchronously with a timeout."""
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return (
            process.returncode or 0,
            maybe_truncate(stdout.decode(), truncate_after=truncate_after),
            maybe_truncate(stderr.decode(), truncate_after=truncate_after),
        )
    except asyncio.TimeoutError as exc:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        raise TimeoutError(f"Command '{cmd}' timed out after {timeout} seconds") from exc


async def run_in_sandbox(
    sandbox: Sandbox,
    cmd: str,
    timeout: float | None = 120.0,  # seconds
    truncate_after: int | None = MAX_RESPONSE_LEN,
):
    """Run a shell command asynchronously with a timeout in sandbox."""
    if not sandbox:
        raise ValueError("Sandbox must be provided to run command in sandbox")

    session_id = "sd-run-session"
    try:
        sandbox.process.create_session(session_id)
        ret = sandbox.process.execute_session_command(
            session_id, SessionExecuteRequest(command=cmd)
        )
        if ret.exit_code == 0:
            return (
                ret.exit_code,
                maybe_truncate(ret.output, truncate_after=truncate_after),
                "",
            )
        else:
            return (
                ret.exit_code,
                "",
                f"Command failed with exit code {ret.exit_code}: {ret.error}",
            )
    except Exception as e:
        raise RuntimeError(f"Error running command in sandbox: {e}") from e
    finally:
        sandbox.process.delete_session(session_id)
