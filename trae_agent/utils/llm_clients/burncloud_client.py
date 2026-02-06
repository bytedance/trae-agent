# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""BurnCloud provider configuration."""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)


class BurnCloudProvider(ProviderConfig):
    """BurnCloud provider configuration."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create OpenAI client with BurnCloud base URL."""
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        return "BurnCloud"

    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        return "burncloud"

    def get_extra_headers(self) -> dict[str, str]:
        """Get BurnCloud-specific headers."""
        # BurnCloud uses standard OpenAI-compatible API, no extra headers needed
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling."""
        # Most modern models on BurnCloud support tool calling
        # Check for known capable models with more precise patterns
        tool_capable_patterns = [
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-20250514", 
            "claude-opus-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "gpt-5-chat-latest",
            "gpt-5",
            "gpt-4.1",
            "gpt-4.1-mini",
            "chatgpt-4o-latest",
            "gpt-4o-2024-11-20",
            "gpt-4o",
            "gpt-4o-mini",
            "o3",
            "o3-mini", 
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-nothink",
            "gemini-2.5-pro-search",
            "gemini-2.5-pro-preview-06-05",
            "gemini-2.5-pro-preview-05-06",  
            "deepseek-v3",
        ]
        model_lower = model_name.lower()
        return any(pattern.lower() == model_lower for pattern in tool_capable_patterns)


class BurnCloudClient(OpenAICompatibleClient):
    """BurnCloud client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_config: ModelConfig):
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = "https://ai.burncloud.com/v1"
        super().__init__(model_config, BurnCloudProvider())

    def supports_tool_calling(self, model_config: ModelConfig) -> bool:
        """Check if the model supports tool calling."""
        # Most modern models on BurnCloud support tool calling
        # Check for known capable models with more precise patterns
        tool_capable_patterns = [
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-20250514", 
            "claude-opus-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "gpt-5-chat-latest",
            "gpt-5",
            "gpt-4.1",
            "gpt-4.1-mini",
            "chatgpt-4o-latest",
            "gpt-4o-2024-11-20",
            "gpt-4o",
            "gpt-4o-mini",
            "o3",
            "o3-mini", 
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-nothink",
            "gemini-2.5-pro-search",
            "gemini-2.5-pro-preview-06-05",
            "gemini-2.5-pro-preview-05-06",  
            "deepseek-v3",
        ]
        model_lower = model_config.model.lower()
        return any(pattern.lower() == model_lower for pattern in tool_capable_patterns)