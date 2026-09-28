# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from abc import ABC, abstractmethod

from trae_agent.tools.base import Tool
from trae_agent.utils.config import ConfigError, ModelConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.utils.trajectory_recorder import TrajectoryRecorder


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    def __init__(self, model_config: ModelConfig):
        self.api_key: str = model_config.model_provider.api_key
        if not self.api_key:
            # An empty key is not a key the SDK can send: httpx rejects the `Authorization:
            # Bearer ` header it produces, so the request never leaves the process and the user
            # gets a `Connection error` after every retry. Fail here, naming the value to set.
            provider = str(model_config.model_provider.provider)
            raise ConfigError(
                f"No API key is configured for model provider `{provider}`. Set the "
                f"`{provider.upper()}_API_KEY` environment variable, pass `--api-key`, or fill "
                f"in `api_key` for that provider in the config file."
            )
        self.base_url: str | None = model_config.model_provider.base_url
        self.api_version: str | None = model_config.model_provider.api_version
        self.trajectory_recorder: TrajectoryRecorder | None = None  # TrajectoryRecorder instance

    def set_trajectory_recorder(self, recorder: TrajectoryRecorder | None) -> None:
        """Set the trajectory recorder for this client."""
        self.trajectory_recorder = recorder

    @abstractmethod
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to the LLM."""
        pass

    def supports_tool_calling(self, model_config: ModelConfig) -> bool:
        """Check if the current model supports tool calling."""
        return model_config.supports_tool_calling
