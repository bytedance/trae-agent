# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""LLM Client wrapper for OpenAI, Anthropic, Azure, and OpenRouter APIs."""

from enum import Enum

from trae_agent.tools.base import Tool
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    DOUBAO = "doubao"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"


class LLMClient:
    """Main LLM client that supports multiple providers."""

    def __init__(self, model_config: ModelConfig):
        self.provider: LLMProvider = LLMProvider(model_config.model_provider.provider)
        self.model_config: ModelConfig = model_config

        match self.provider:
            case LLMProvider.OPENAI:
                from .openai_client import OpenAIClient

                self.client: BaseLLMClient = OpenAIClient(model_config)
            case LLMProvider.ANTHROPIC:
                from .anthropic_client import AnthropicClient

                self.client = AnthropicClient(model_config)
            case LLMProvider.AZURE:
                from .azure_client import AzureClient

                self.client = AzureClient(model_config)
            case LLMProvider.OPENROUTER:
                from .openrouter_client import OpenRouterClient

                self.client = OpenRouterClient(model_config)
            case LLMProvider.DOUBAO:
                from .doubao_client import DoubaoClient

                self.client = DoubaoClient(model_config)
            case LLMProvider.OLLAMA:
                from .ollama_client import OllamaClient

                self.client = OllamaClient(model_config)
            case LLMProvider.GOOGLE:
                from .google_client import GoogleClient

                self.client = GoogleClient(model_config)
            case LLMProvider.DEEPSEEK:
                from .deepseek_client import DeepSeekClient

                self.client = DeepSeekClient(model_config)

    def set_trajectory_recorder(self, recorder: TrajectoryRecorder | None) -> None:
        """Set the trajectory recorder for the underlying client."""
        self.client.set_trajectory_recorder(recorder)

    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.client.set_chat_history(messages)

    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to the LLM."""
        return self.client.chat(messages, model_config, tools, reuse_history)

    def supports_tool_calling(self, model_config: ModelConfig) -> bool:
        """Check if the current client supports tool calling."""
        return hasattr(self.client, "supports_tool_calling") and self.client.supports_tool_calling(
            model_config
        )
