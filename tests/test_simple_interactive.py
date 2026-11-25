# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import re
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from trae_agent.cli import cli
from trae_agent.tools.base import ToolCall
from trae_agent.utils.llm_clients.llm_basics import LLMResponse


def test_simple_interactive_displays_each_task_once(tmp_path: Path) -> None:
    config = tmp_path / "trae.yaml"
    config.write_text(
        """
agents:
  trae_agent:
    model: test_model
    enable_lakeview: false
    max_steps: 1
    tools: [task_done]
models:
  test_model:
    model_provider: test_provider
    model: test
    temperature: 0.5
    top_p: 1.0
    top_k: 1
    parallel_tool_calls: false
    max_retries: 1
model_providers:
  test_provider:
    provider: anthropic
    api_key: test
""",
        encoding="utf-8",
    )
    with (
        patch("trae_agent.agent.base_agent.LLMClient") as client,
        patch("trae_agent.tools.ckg.ckg_database.CKG_DATABASE_PATH", tmp_path / "ckg"),
    ):
        client.return_value.provider.value = "anthropic"
        client.return_value.chat.side_effect = [
            LLMResponse(
                content="Task completed: result one", tool_calls=[ToolCall("task_done", "one")]
            ),
            LLMResponse(
                content="Task completed: result two", tool_calls=[ToolCall("task_done", "two")]
            ),
        ]
        result = CliRunner().invoke(
            cli,
            [
                "interactive",
                "--console-type",
                "simple",
                "--config-file",
                str(config),
                "-t",
                str(tmp_path / "trace.json"),
            ],
            input=f"first task\n{tmp_path}\nsecond task\n{tmp_path}\nexit\n",
            catch_exceptions=False,
        )
        assert client.return_value.chat.call_count == 2, result.output
    assert result.exit_code == 0, result.output
    assert result.output.count("Execution Summary") == 2, result.output
    assert len(re.findall(r"Step 1: Completed", result.output)) == 2, result.output
    assert result.output.count("result one") == 2, result.output
    assert result.output.count("result two") == 2, result.output
