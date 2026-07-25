# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""NVIDIA NIM client wrapper with tool integrations.

NVIDIA NIM (build.nvidia.com) 提供与 OpenAI 兼容的 Chat Completions API。
- base_url: https://integrate.api.nvidia.com/v1
- API Key 格式: nvapi-xxxxx
- 模型: moonshotai/kimi-k2.6, meta/llama-3.1-405b-instruct,
  nvidia/llama-3.1-nemotron-70b-instruct, deepseek-ai/deepseek-r1 等

注意: 并非所有 NVIDIA 目录中的模型都支持工具调用 (function calling)，
使用 Agent 功能前请先在 build.nvidia.com 检查模型卡片。
"""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class NvidiaProvider(ProviderConfig):
    """NVIDIA NIM provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with NVIDIA NIM base URL."""
        return openai.OpenAI(base_url=base_url, api_key=api_key)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "NVIDIA"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "nvidia"

    def get_extra_headers(self) -> dict[str, str]:
        """Get NVIDIA-specific headers (none needed)."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling.

        NVIDIA NIM 上已知支持 function calling 的模型包括:
        - moonshotai/kimi-k2.6
        - meta/llama-3.1-* 系列
        - nvidia/llama-3.1-nemotron-*
        - deepseek-ai/deepseek-r1
        对于其他模型请查阅 build.nvidia.com 上的模型卡片确认。
        """
        tool_capable_patterns = [
            "kimi-k2",
            "llama-3.1",
            "llama-3.3",
            "nemotron",
            "deepseek-r1",
            "qwen2.5",
        ]
        return any(pattern in model_name.lower() for pattern in tool_capable_patterns)


class NvidiaClient(OpenAICompatibleClient):
    """NVIDIA NIM client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_config: ModelConfig):
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = "https://integrate.api.nvidia.com/v1"
        super().__init__(model_config, NvidiaProvider())
