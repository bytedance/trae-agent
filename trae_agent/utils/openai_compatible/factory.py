# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Factory for creating OpenAI-compatible clients."""

from enum import Enum

from ..config import ModelParameters
from .base import OpenAICompatibleClient
from .providers import AzureProvider, DoubaoProvider, OpenRouterProvider


class OpenAICompatibleProvider(Enum):
    """Supported OpenAI-compatible providers."""

    OPENROUTER = "openrouter"
    AZURE = "azure"
    DOUBAO = "doubao"


def create_openai_compatible_client(
    provider: str | OpenAICompatibleProvider, model_parameters: ModelParameters
) -> OpenAICompatibleClient:
    """Factory function to create OpenAI-compatible clients.

    Args:
        provider: The provider type (openrouter, azure, or doubao)
        model_parameters: Model configuration parameters

    Returns:
        OpenAICompatibleClient instance configured for the provider

    Raises:
        ValueError: If the provider is not supported
    """
    if isinstance(provider, str):
        try:
            provider = OpenAICompatibleProvider(provider)
        except ValueError as err:
            raise ValueError(f"Unsupported provider: {provider}") from err

    provider_configs = {
        OpenAICompatibleProvider.OPENROUTER: OpenRouterProvider(),
        OpenAICompatibleProvider.AZURE: AzureProvider(),
        OpenAICompatibleProvider.DOUBAO: DoubaoProvider(),
    }

    provider_config = provider_configs.get(provider)
    if not provider_config:
        raise ValueError(f"Unsupported provider: {provider}")

    return OpenAICompatibleClient(model_parameters, provider_config)
