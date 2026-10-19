# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import ntpath
import posixpath
import shlex
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import trae_agent.tools.docker_tool_executor as docker_executor
from trae_agent.tools.base import ToolCall


@pytest.mark.parametrize(
    ("path_module", "workspace", "host_path", "expected"),
    [
        (ntpath, r"C:\repo", r"C:\repo\src\main.py", "/workspace/src/main.py"),
        (ntpath, r"C:\repo", r"C:\repo", "/workspace"),
        (ntpath, r"C:\Repo", r"c:\repo\src\main.py", "/workspace/src/main.py"),
        (ntpath, r"C:\repo", r"D:\outside\file.py", r"D:\outside\file.py"),
        (ntpath, r"C:\repo", r"C:\repo-other\file.py", r"C:\repo-other\file.py"),
        (posixpath, "/home/user/repo", "/home/user/repo/src/main.py", "/workspace/src/main.py"),
    ],
)
def test_host_paths_translate_to_posix_container_paths(
    monkeypatch, path_module, workspace, host_path, expected
):
    monkeypatch.setattr(
        docker_executor, "os", SimpleNamespace(path=path_module, sep=path_module.sep)
    )
    executor = docker_executor.DockerToolExecutor(
        MagicMock(), MagicMock(), [], workspace, "/workspace"
    )

    assert executor._translate_path(host_path) == expected


@pytest.mark.parametrize(
    ("tool_name", "arguments", "path_flag"),
    [
        (
            "str_replace_based_edit_tool",
            {"command": "view", "path": r"C:\repo\src\main.py"},
            "--path",
        ),
        (
            "json_edit_tool",
            {"operation": "view", "file_path": r"C:\repo\src\config.json"},
            "--file_path",
        ),
    ],
)
def test_both_edit_tools_receive_translated_paths(monkeypatch, tool_name, arguments, path_flag):
    monkeypatch.setattr(docker_executor, "os", SimpleNamespace(path=ntpath, sep=ntpath.sep))
    manager = MagicMock()
    manager.CONTAINER_TOOLS_PATH = "/tools"
    manager.execute.return_value = (0, "ok")
    executor = docker_executor.DockerToolExecutor(
        MagicMock(), manager, [tool_name], r"C:\repo", "/workspace"
    )

    result = executor._execute_in_docker(
        ToolCall(call_id="call-1", name=tool_name, arguments=arguments)
    )

    assert result.success, result.error
    argv = shlex.split(manager.execute.call_args.args[0])
    expected = "/workspace/src/main.py" if path_flag == "--path" else "/workspace/src/config.json"
    assert argv[argv.index(path_flag) + 1] == expected
