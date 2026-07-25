# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""MiniMax client wrapper with tool integrations.

MiniMax 提供与 OpenAI 兼容的 Chat Completions API。
- 国际版 base_url: https://api.minimax.io/v1
- 国内版 base_url: https://api.minimax.chat/v1
- 模型: MiniMax-M3, MiniMax-Text-01, abab6.5s-chat 等
"""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class MiniMaxProvider(ProviderConfig):
    """MiniMax provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with MiniMax base URL."""
        return openai.OpenAI(base_url=base_url, api_key=api_key)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "MiniMax"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "minimax"

    def get_extra_headers(self) -> dict[str, str]:
        """Get MiniMax-specific headers (none needed)."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling.

        MiniMax-M3 / MiniMax-Text-01 / abab6.5 系列均支持 function calling。
        """
        return True


class MiniMaxClient(OpenAICompatibleClient):
    """MiniMax client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_config: ModelConfig):
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = "https://api.minimax.io/v1"
        super().__init__(model_config, MiniMaxProvider())
