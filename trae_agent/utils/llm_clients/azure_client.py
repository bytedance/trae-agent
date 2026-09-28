# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Azure client wrapper with tool integrations"""

import os

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class AzureProvider(ProviderConfig):
    """Azure OpenAI provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create Azure OpenAI client."""
        if not base_url:
            raise ValueError("base_url is required for AzureClient")

        # Azure needs an api_version, but ModelProvider.api_version is optional and the SDK only
        # reads OPENAI_API_VERSION -- not AZURE_API_VERSION, the name used for every other
        # provider field in this project.
        resolved_api_version = (
            api_version or os.getenv("AZURE_API_VERSION") or os.getenv("OPENAI_API_VERSION")
        )
        if not resolved_api_version:
            raise ValueError(
                "api_version is required for AzureClient. Set `api_version` in the model provider "
                "configuration (for example `api_version: 2024-03-01-preview`), or export "
                "AZURE_API_VERSION."
            )

        return openai.AzureOpenAI(
            azure_endpoint=base_url,
            api_version=resolved_api_version,
            api_key=api_key,
        )

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "Azure OpenAI"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "azure"

    def get_extra_headers(self) -> dict[str, str]:
        """Get Azure-specific headers (none needed)."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling."""
        # Azure OpenAI models generally support tool calling
        return True


class AzureClient(OpenAICompatibleClient):
    """Azure client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config, AzureProvider())
