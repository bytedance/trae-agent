# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from abc import ABC, abstractmethod

from ..tools.base import Tool
from ..utils.config import ModelParameters
from ..utils.llm_basics import LLMMessage, LLMResponse
from ..utils.trajectory_recorder import TrajectoryRecorder


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    def __init__(self, model_parameters: ModelParameters):
        self.api_key: str = model_parameters.api_key
        self.base_url: str | None = model_parameters.base_url
        self.api_version: str | None = model_parameters.api_version
        self.trajectory_recorder: TrajectoryRecorder | None = (
            None  # TrajectoryRecorder instance
        )

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
        model_parameters: ModelParameters,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to the LLM."""
        pass

    @abstractmethod
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        pass
