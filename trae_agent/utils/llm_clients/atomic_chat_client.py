# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Atomic Chat local provider (OpenAI-compatible API)."""

import openai

from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)

DEFAULT_ATOMIC_CHAT_BASE_URL = "http://127.0.0.1:1337/v1"
DEFAULT_ATOMIC_CHAT_API_KEY = "noop"


class AtomicChatProvider(ProviderConfig):
    """Atomic Chat — local OpenAI-compatible server (https://atomic.chat)."""

    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        return openai.OpenAI(api_key=api_key, base_url=base_url)

    def get_service_name(self) -> str:
        return "Atomic Chat"

    def get_provider_name(self) -> str:
        return "atomic_chat"

    def get_extra_headers(self) -> dict[str, str]:
        return {}

    def supports_tool_calling(self, model_name: str) -> bool:
        tool_capable_patterns = [
            "qwen",
            "llama",
            "mistral",
            "gemma",
            "deepseek",
            "gpt",
            "claude",
            "command",
            "phi",
            "coder",
        ]
        return any(pattern in model_name.lower() for pattern in tool_capable_patterns)


class AtomicChatClient(OpenAICompatibleClient):
    """Client for Atomic Chat's local OpenAI-compatible API."""

    def __init__(self, model_config: ModelConfig):
        if not model_config.model_provider.api_key:
            model_config.model_provider.api_key = DEFAULT_ATOMIC_CHAT_API_KEY
        if (
            model_config.model_provider.base_url is None
            or model_config.model_provider.base_url == ""
        ):
            model_config.model_provider.base_url = DEFAULT_ATOMIC_CHAT_BASE_URL
        super().__init__(model_config, AtomicChatProvider())

    def supports_tool_calling(self, model_config: ModelConfig) -> bool:
        if model_config.supports_tool_calling is False:
            return False
        return self.provider_config.supports_tool_calling(model_config.model)
