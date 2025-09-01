# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Base class for OpenAI-compatible clients with shared logic."""

import json
from abc import ABC, abstractmethod
from typing import override

import openai
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionFunctionMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import Function
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
)
from openai.types.shared_params.function_definition import FunctionDefinition

from trae_agent.tools.base import Tool, ToolCall
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class ProviderConfig(ABC):
    """Abstract base class for provider-specific configurations."""

    @abstractmethod
    def create_client(
        self, api_key: str, base_url: str | None, api_version: str | None
    ) -> openai.OpenAI:
        """Create the OpenAI client instance."""
        pass

    @abstractmethod
    def get_service_name(self) -> str:
        """Get the service name for retry logging."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider name for trajectory recording."""
        pass

    @abstractmethod
    def get_extra_headers(self) -> dict[str, str]:
        """Get any extra headers needed for the API call."""
        pass

    @abstractmethod
    def supports_tool_calling(self, model_name: str) -> bool:
        """Check if the model supports tool calling."""
        pass


class OpenAICompatibleClient(BaseLLMClient):
    """Base class for OpenAI-compatible clients with shared logic."""

    def __init__(self, model_config: ModelConfig, provider_config: ProviderConfig):
        super().__init__(model_config)
        self.provider_config = provider_config
        self.client = provider_config.create_client(self.api_key, self.base_url, self.api_version)
        self.message_history: list[ChatCompletionMessageParam] = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    def _create_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[ChatCompletionToolParam] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> ChatCompletion:
        """Create a response using the provider's API. This method will be decorated with retry logic."""
        """Select the correct token parameter based on model configuration.
        If max_completion_tokens is set, use it. Otherwise, use max_tokens."""
        token_params = {}
        if model_config.should_use_max_completion_tokens():
            token_params["max_completion_tokens"] = model_config.get_max_tokens_param()
        else:
            token_params["max_tokens"] = model_config.get_max_tokens_param()

        return self.client.chat.completions.create(
            model=model_config.model,
            messages=self.message_history,
            tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
            temperature=model_config.temperature
            if "o3" not in model_config.model
            and "o4-mini" not in model_config.model
            and "gpt-5" not in model_config.model
            else openai.NOT_GIVEN,
            top_p=model_config.top_p,
            extra_headers=extra_headers if extra_headers else None,
            n=1,
            **token_params,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages with optional tool support."""
        parsed_messages = self.parse_messages(messages)
        if reuse_history:
            self.message_history = self.message_history + parsed_messages
        else:
            self.message_history = parsed_messages

        tool_schemas = None
        if tools:
            tool_schemas = [
                ChatCompletionToolParam(
                    function=FunctionDefinition(
                        name=tool.get_name(),
                        description=tool.get_description(),
                        parameters=tool.get_input_schema(),
                    ),
                    type="function",
                )
                for tool in tools
            ]

        # Get provider-specific extra headers
        extra_headers = self.provider_config.get_extra_headers()

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_response,
            provider_name=self.provider_config.get_service_name(),
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(model_config, tool_schemas, extra_headers)

        choice = response.choices[0]

        tool_calls: list[ToolCall] | None = None
        if choice.message.tool_calls:
            tool_calls = []
            for tool_call in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        name=tool_call.function.name,
                        call_id=tool_call.id,
                        arguments=(
                            json.loads(tool_call.function.arguments)
                            if tool_call.function.arguments
                            else {}
                        ),
                    )
                )

        llm_response = LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            model=response.model,
            usage=(
                LLMUsage(
                    input_tokens=response.usage.prompt_tokens or 0,
                    output_tokens=response.usage.completion_tokens or 0,
                )
                if response.usage
                else None
            ),
        )

        # Update message history
        if llm_response.tool_calls:
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=llm_response.content,
                    tool_calls=[
                        ChatCompletionMessageToolCallParam(
                            id=tool_call.call_id,
                            function=Function(
                                name=tool_call.name,
                                arguments=json.dumps(tool_call.arguments),
                            ),
                            type="function",
                        )
                        for tool_call in llm_response.tool_calls
                    ],
                )
            )
        elif llm_response.content:
            self.message_history.append(
                ChatCompletionAssistantMessageParam(content=llm_response.content, role="assistant")
            )

        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider=self.provider_config.get_provider_name(),
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
        """Parse LLM messages to OpenAI format."""
        openai_messages: list[ChatCompletionMessageParam] = []
        for msg in messages:
            match msg:
                case msg if msg.tool_call is not None:
                    _msg_tool_call_handler(openai_messages, msg)
                case msg if msg.tool_result is not None:
                    _msg_tool_result_handler(openai_messages, msg)
                case _:
                    _msg_role_handler(openai_messages, msg)

        return openai_messages


def _msg_tool_call_handler(messages: list[ChatCompletionMessageParam], msg: LLMMessage) -> None:
    if msg.tool_call:
        messages.append(
            ChatCompletionFunctionMessageParam(
                content=json.dumps(
                    {
                        "name": msg.tool_call.name,
                        "arguments": msg.tool_call.arguments,
                    }
                ),
                role="function",
                name=msg.tool_call.name,
            )
        )


def _msg_tool_result_handler(messages: list[ChatCompletionMessageParam], msg: LLMMessage) -> None:
    if msg.tool_result:
        result: str = ""
        if msg.tool_result.result:
            result = result + msg.tool_result.result + "\n"
        if msg.tool_result.error:
            result += "Tool call failed with error:\n"
            result += msg.tool_result.error
        result = result.strip()
        messages.append(
            ChatCompletionToolMessageParam(
                content=result,
                role="tool",
                tool_call_id=msg.tool_result.call_id,
            )
        )


def _msg_role_handler(messages: list[ChatCompletionMessageParam], msg: LLMMessage) -> None:
    if msg.role:
        match msg.role:
            case "system":
                if not msg.content:
                    raise ValueError("System message content is required")
                messages.append(
                    ChatCompletionSystemMessageParam(content=msg.content, role="system")
                )
            case "user":
                if not msg.content:
                    raise ValueError("User message content is required")
                messages.append(ChatCompletionUserMessageParam(content=msg.content, role="user"))
            case "assistant":
                if not msg.content:
                    raise ValueError("Assistant message content is required")
                messages.append(
                    ChatCompletionAssistantMessageParam(content=msg.content, role="assistant")
                )
            case _:
                raise ValueError(f"Invalid message role: {msg.role}")
