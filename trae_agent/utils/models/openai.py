# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import os
from typing import Optional, override

import openai
from openai.types.responses import (
    ResponseInputParam,
)

from ...tools.base import Tool
from ..base_client import BaseLLMClient
from ..config import ModelParameters
from ..llm_basics import LLMMessage, LLMResponse

"""
    This file provides an base class for open ai competitible clients
"""


class OpenAIClientBase(BaseLLMClient):
    def __init__(self, model_parameters: ModelParameters, provider: Optional[str]):
        """
        The init function should separate different clients to specific
        chat , support tool calling and all kinds of parsing
        """

        # default setting as openai
        if not provider:
            provider = "openai"

        super().__init__(model_parameters)

        # save provider
        self.provider = provider

        if self.api_key == "":
            # all open ai competitible models will be using OPENAI_API_KEY
            self.api_key: str = os.getenv("OPENAI_API_KEY", "")
            if provider == "ollama":
                self.api_key = "ollama"

        if self.api_key == "":
            raise ValueError(
                "API key not provided. Set OPENAI_API_KEY in environment variables or config file."
            )

        self.client: openai.OpenAI = openai.OpenAI(api_key=self.api_key)

        base_url = model_parameters.base_url
        if base_url:
            self.client.base_url = base_url

        self.message_history: ResponseInputParam = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """
        set chat history provides a method to set the messages list
        to the one we provided.
        """
        self.message_history = self.parse_messages(messages)

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_parameters: ModelParameters,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        match self.provider:
            case _:
                from .openai_client import chat as openai_chat

                llm_response, message_history = openai_chat(
                    messages,
                    model_parameters,
                    self.client,
                    tools,
                    reuse_history,
                    self.message_history,
                    self.trajectory_recorder,
                )
                self.message_history = message_history
                return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        match self.provider:
            case _:
                from .openai_client import (
                    supports_tool_calling as openai_support_tool_calling,
                )

                return openai_support_tool_calling(model_parameters)

    def parse_messages(self, messages: list[LLMMessage]) -> ResponseInputParam:
        match self.provider:
            case _:
                from .openai_client import parse_messages as openai_parse_messages

                return openai_parse_messages(messages)
