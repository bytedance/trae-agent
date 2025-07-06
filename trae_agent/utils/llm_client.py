# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""LLM Client wrapper for OpenAI and Anthropic APIs."""

from enum import Enum

from ..tools.base import Tool
from .config import ModelParameters
from .trajectory_recorder import TrajectoryRecorder
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse

class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    GEMINI = "gemini"


class LLMClient:
    """Main LLM client that supports multiple providers."""

    def __init__(self, provider: str | LLMProvider, model_parameters: ModelParameters):
        if isinstance(provider, str):
            provider = LLMProvider(provider)

        self.provider: LLMProvider = provider

        if provider == LLMProvider.OPENAI:
            from .openai_client import OpenAIClient
            self.client: BaseLLMClient = OpenAIClient(model_parameters)
        elif provider == LLMProvider.ANTHROPIC:
            from .anthropic_client import AnthropicClient
            self.client = AnthropicClient(model_parameters)
        elif provider == LLMProvider.AZURE:
            from .azure_client import AzureClient
            self.client = AzureClient(model_parameters)
        elif provider == LLMProvider.GEMINI:
            from .gemini_client import GeminiClient
            self.client = GeminiClient(model_parameters)

    def set_trajectory_recorder(self, recorder: TrajectoryRecorder | None) -> None:
        """Set the trajectory recorder for the underlying client."""
        self.client.set_trajectory_recorder(recorder)

    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.client.set_chat_history(messages)

    def chat(self, messages: list[LLMMessage], model_parameters: ModelParameters, tools: list[Tool] | None = None, reuse_history: bool = True) -> LLMResponse:
        """Send chat messages to the LLM."""
        return self.client.chat(messages, model_parameters, tools, reuse_history)

    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current client supports tool calling."""
        return hasattr(self.client, 'supports_tool_calling') and self.client.supports_tool_calling(model_parameters)
