# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""LLM Client wrapper for OpenAI, Anthropic, Azure, and OpenRouter APIs."""

from enum import Enum

from ..tools.base import Tool
from .base_client import BaseLLMClient
from .config import ModelParameters
from .llm_basics import LLMMessage, LLMResponse
from .trajectory_recorder import TrajectoryRecorder


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"
    DOUBAO = "doubao"
    GOOGLE = "google"


class LLMClient:
    """Main LLM client that supports multiple providers."""

    def __init__(
        self, provider: str | LLMProvider, model_parameters: ModelParameters, max_steps: int
    ):
        if isinstance(provider, str):
            provider = LLMProvider(provider)

        self.provider: LLMProvider = provider
        self._model_parameters: ModelParameters = model_parameters
        self._max_steps: int = max_steps

        match provider:
            case LLMProvider.OPENAI:
                from .openai_client import OpenAIClient

                self.client: BaseLLMClient = OpenAIClient(model_parameters)
            case LLMProvider.ANTHROPIC:
                from .anthropic_client import AnthropicClient

                self.client = AnthropicClient(model_parameters)
            case LLMProvider.AZURE:
                from .azure_client import AzureClient

                self.client = AzureClient(model_parameters)
            case LLMProvider.OPENROUTER:
                from .openrouter_client import OpenRouterClient

                self.client = OpenRouterClient(model_parameters)
            case LLMProvider.DOUBAO:
                from .doubao_client import DoubaoClient

                self.client = DoubaoClient(model_parameters)
            case LLMProvider.OLLAMA:
                from .ollama_client import OllamaClient

                self.client = OllamaClient(model_parameters)
            case LLMProvider.GOOGLE:
                from .google_client import GoogleClient

                self.client = GoogleClient(model_parameters)

    @property
    def model_parameters(self) -> ModelParameters:
        """Get the model parameters used by this client."""
        return self._model_parameters

    @property
    def max_steps(self) -> int:
        """Get the max steps used by this client."""
        return self._max_steps

    def set_trajectory_recorder(self, recorder: TrajectoryRecorder | None) -> None:
        """Set the trajectory recorder for the underlying client."""
        self.client.set_trajectory_recorder(recorder)

    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.client.set_chat_history(messages)

    def chat(
        self,
        messages: list[LLMMessage],
        model_parameters: ModelParameters,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to the LLM."""
        return self.client.chat(messages, model_parameters, tools, reuse_history)

    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current client supports tool calling."""
        return hasattr(self.client, "supports_tool_calling") and self.client.supports_tool_calling(
            model_parameters
        )
