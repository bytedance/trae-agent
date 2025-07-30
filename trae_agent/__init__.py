# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Trae Agent - LLM-based agent for general purpose software engineering tasks."""

__version__ = "0.1.0"

from .agent.base import Agent
from .agent.trae_agent import TraeAgent
from .tools.base import Tool, ToolExecutor
from .utils.llm_clients.llm_client import LLMClient

__all__ = ["Agent", "TraeAgent", "LLMClient", "Tool", "ToolExecutor"]
