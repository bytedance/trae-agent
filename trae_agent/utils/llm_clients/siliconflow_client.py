# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""SiliconFlow provider configuration."""

import openai

from .openai_compatible_base import ProviderConfig
from ..config import ModelConfig
from .openai_compatible_base import OpenAICompatibleClient


class SiliconFlowProvider(ProviderConfig):
    """SiliconFlow provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with SiliconFlow base URL."""
        return openai.OpenAI(base_url=base_url, api_key=api_key)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "SiliconFlow"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "siliconflow"

    def get_extra_headers(self) -> dict[str, str]:
        """Get SiliconFlow-specific headers (none needed)."""
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling."""
        # Most SiliconFlow models support tool calling
        # We'll be conservative and check for known capable model patterns
        tool_capable_patterns = [
            "qwen",
            "deepseek",
            "yi",
            "baichuan",
            "chatglm",
            "internlm",
            "llama",
            "mistral",
            "gemma",
        ]
        return any(pattern in model_name.lower() for pattern in tool_capable_patterns)


class SiliconFlowClient(OpenAICompatibleClient):
    """SiliconFlow client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_parameters: ModelConfig):
        super().__init__(model_parameters, SiliconFlowProvider())
