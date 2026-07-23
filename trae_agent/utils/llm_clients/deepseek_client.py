# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""DeepSeek client wrapper with tool integrations.

DeepSeek provides an OpenAI-compatible Chat Completions API at
https://api.deepseek.com/v1. This client uses the standard
chat.completions.create endpoint rather than the newer Responses API.
"""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class DeepSeekProvider(ProviderConfig):
    """DeepSeek provider configuration.

    DeepSeek's API is OpenAI-compatible. The base URL defaults to
    https://api.deepseek.com/v1 and can be overridden via config or
    the DEEPSEEK_BASE_URL environment variable.
    """

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create an OpenAI client pointed at DeepSeek's API endpoint."""
        return openai.OpenAI(base_url=base_url, api_key=api_key)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "DeepSeek"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "deepseek"

    def get_extra_headers(self) -> dict[str, str]:
        """DeepSeek does not require extra headers."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling.

        All DeepSeek chat models (deepseek-chat, deepseek-reasoner) support
        function calling via the OpenAI-compatible API.
        """
        return True


class DeepSeekClient(OpenAICompatibleClient):
    """DeepSeek client wrapper for the OpenAI-compatible Chat Completions API.

    Uses the standard chat.completions.create endpoint, which is compatible
    with DeepSeek's API as well as other OpenAI-compatible providers.

    Example YAML configuration::

        model_providers:
            deepseek:
                api_key: ""   # Reads DEEPSEEK_API_KEY from environment
                provider: deepseek
                base_url: https://api.deepseek.com/v1

        models:
            my_model:
                model_provider: deepseek
                model: deepseek-chat
                max_tokens: 4096
                temperature: 0.5
                top_p: 1
                top_k: 0
                max_retries: 3
                parallel_tool_calls: false
    """

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config, DeepSeekProvider())
