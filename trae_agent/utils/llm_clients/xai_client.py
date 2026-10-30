# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""xAI (Grok) provider configuration."""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class XAIProvider(ProviderConfig):
    """xAI (Grok) provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with xAI base URL."""
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "xAI"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "xai"

    def get_extra_headers(self) -> dict[str, str]:
        """Get xAI-specific headers (none needed)."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling."""
        tool_capable_patterns = [
            "grok",
        ]
        return any(pattern in model_name.lower() for pattern in tool_capable_patterns)


class XAIClient(OpenAICompatibleClient):
    """xAI client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_config: ModelConfig):
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = "https://api.x.ai/v1"
        super().__init__(model_config, XAIProvider())

    def supports_tool_calling(self, model_config: ModelConfig) -> bool:
        """Check if the configured xAI model supports tool calling."""
        return self.provider_config.supports_tool_calling(model_config.model)
