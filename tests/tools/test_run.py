# Copyright (c) 2026 ByteDance Ltd. and/or its affiliates.
# SPDX-License-Identifier: MIT

import os
import shlex
import subprocess
import sys

import pytest

from trae_agent.tools.run import run


def python_command(code: str) -> str:
    args = [sys.executable, "-c", code]
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
async def test_non_utf8_output_keeps_command_result(stream: str) -> None:
    command = python_command(
        f"import sys; sys.{stream}.buffer.write(bytes([111, 107, 255, 10])); sys.exit(7)"
    )
    code, stdout, stderr = await run(command)
    assert code == 7
    assert (stdout if stream == "stdout" else stderr) == "ok\ufffd\n"
    assert (stderr if stream == "stdout" else stdout) == ""


@pytest.mark.asyncio
async def test_valid_utf8_output_is_unchanged() -> None:
    command = python_command(
        "import sys; sys.stdout.buffer.write(bytes([228, 184, 173, 230, 150, 135]))"
    )
    assert await run(command) == (0, "中文", "")
