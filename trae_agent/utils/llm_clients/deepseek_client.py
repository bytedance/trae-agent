# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""DeepSeek provider configuration.

Endpoints:
  - https://api.deepseek.com          (OpenAI-compatible, this client)
  - https://api.deepseek.com/anthropic (Anthropic-compatible, use anthropic provider)
"""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class DeepSeekProvider(ProviderConfig):
    """DeepSeek provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with DeepSeek base URL."""
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "DeepSeek"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "deepseek"

    def get_extra_headers(self) -> dict[str, str]:
        """Get any extra headers needed for the API call."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling."""
        return "deepseek" in model_name.lower()


class DeepSeekClient(OpenAICompatibleClient):
    """DeepSeek client wrapper via OpenAI-compatible Chat Completions API.

    Default endpoint: https://api.deepseek.com
    Models: deepseek-v4-pro, deepseek-v4-flash
    """

    def __init__(self, model_config: ModelConfig):
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = "https://api.deepseek.com"
        super().__init__(model_config, DeepSeekProvider())
