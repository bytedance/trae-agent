# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock, patch
import pytest

from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.tools import (
    CKGTool,
    SequentialThinkingTool,
    tools_registry,
)
from trae_agent.utils.config import ModelConfig, ModelProvider, TraeAgentConfig


def test_tools_registry_contains_all_builtin_tools():
    """Verify tools_registry contains ckg, sequentialthinking, and sequential_thinking alias."""
    assert "ckg" in tools_registry
    assert tools_registry["ckg"] is CKGTool

    assert "sequentialthinking" in tools_registry
    assert tools_registry["sequentialthinking"] is SequentialThinkingTool

    # Alias support
    assert "sequential_thinking" in tools_registry
    assert tools_registry["sequential_thinking"] is SequentialThinkingTool


@patch("trae_agent.agent.base_agent.LLMClient")
def test_base_agent_unknown_tool_raises_helpful_error(mock_llm):
    """Agent should raise a descriptive ValueError when an invalid tool name is provided."""
    mock_llm.return_value.client = MagicMock()
    model_provider = ModelProvider(provider="anthropic", api_key="dummy")
    model_cfg = ModelConfig(
        model="claude-sonnet-4-20250514",
        model_provider=model_provider,
        temperature=0.5,
        top_p=1.0,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=3,
    )
    agent_cfg = TraeAgentConfig(
        allow_mcp_servers=[],
        mcp_servers_config={},
        max_steps=20,
        model=model_cfg,
        tools=["non_existent_tool_xyz"],
    )

    with pytest.raises(ValueError, match="Unknown tool 'non_existent_tool_xyz' in agent configuration"):
        TraeAgent(agent_cfg)
