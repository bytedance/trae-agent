# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Trae Agent - LLM-based agent for general purpose software engineering tasks."""

__version__ = "0.1.0"

from trae_agent.agent.base_agent import BaseAgent
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.tools.base import Tool, ToolExecutor
from trae_agent.utils.llm_clients.llm_client import LLMClient

__all__ = ["BaseAgent", "TraeAgent", "LLMClient", "Tool", "ToolExecutor"]
