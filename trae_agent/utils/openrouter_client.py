# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenRouter API client wrapper with tool integration."""

import json
import os
import random
import time
from typing import override

import openai
from openai.types.chat import (
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

from ..tools.base import Tool, ToolCall
from ..utils.config import ModelParameters
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse, LLMUsage


class OpenRouterClient(BaseLLMClient):
    """OpenRouter client wrapper with tool schema generation."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)

        # Use OpenAI SDK with OpenRouter's base URL
        self.client: openai.OpenAI = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.message_history: list[ChatCompletionMessageParam] = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_parameters: ModelParameters,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to OpenRouter with optional tool support."""
        openrouter_messages = self.parse_messages(messages)
        if reuse_history:
            self.message_history = self.message_history + openrouter_messages
        else:
            self.message_history = openrouter_messages

        tool_schemas = None
        # Add tools if provided
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

        # Set up extra headers for OpenRouter
        extra_headers = {}
        if os.getenv("OPENROUTER_SITE_URL"):
            extra_headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL")
        if os.getenv("OPENROUTER_SITE_NAME"):
            extra_headers["X-Title"] = os.getenv("OPENROUTER_SITE_NAME")

        response = None
        error_message = ""
        for i in range(model_parameters.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model_parameters.model,
                    messages=self.message_history,
                    tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
                    temperature=model_parameters.temperature,
                    top_p=model_parameters.top_p,
                    max_tokens=model_parameters.max_tokens,
                    extra_headers=extra_headers if extra_headers else openai.NOT_GIVEN,
                    n=1,
                )
                break
            except Exception as e:
                error_message += f"Error {i + 1}: {str(e)}\n"
                # Randomly sleep for 3-30 seconds
                time.sleep(random.randint(3, 30))
                continue

        if response is None:
            raise ValueError(
                f"Failed to get response from OpenRouter after max retries: {error_message}"
            )

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

        # update message history
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
                provider="openrouter",
                model=model_parameters.model,
                tools=tools,
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        # Most modern models on OpenRouter support tool calling
        # We'll be conservative and check for known capable models
        tool_capable_patterns = [
            "gpt-4",
            "gpt-3.5-turbo",
            "claude-3",
            "claude-2",
            "gemini",
            "mistral",
            "llama-3",
            "command-r",
        ]
        return any(pattern in model_parameters.model.lower() for pattern in tool_capable_patterns)

    def parse_messages(self, messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
        openrouter_messages: list[ChatCompletionMessageParam] = []
        for msg in messages:
            if msg.tool_call:
                openrouter_messages.append(
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
            elif msg.tool_result:
                result: str = ""
                if msg.tool_result.result:
                    result = result + msg.tool_result.result + "\n"
                if msg.tool_result.error:
                    result += "Tool call failed with error:\n"
                    result += msg.tool_result.error
                result = result.strip()

                openrouter_messages.append(
                    ChatCompletionToolMessageParam(
                        content=result,
                        role="tool",
                        tool_call_id=msg.tool_result.call_id,
                    )
                )
            elif msg.role == "system":
                if not msg.content:
                    raise ValueError("System message content is required")
                openrouter_messages.append(
                    ChatCompletionSystemMessageParam(content=msg.content, role="system")
                )
            elif msg.role == "user":
                if not msg.content:
                    raise ValueError("User message content is required")
                openrouter_messages.append(
                    ChatCompletionUserMessageParam(content=msg.content, role="user")
                )
            elif msg.role == "assistant":
                if not msg.content:
                    raise ValueError("Assistant message content is required")
                openrouter_messages.append(
                    ChatCompletionAssistantMessageParam(content=msg.content, role="assistant")
                )
            else:
                raise ValueError(f"Invalid message role: {msg.role}")
        return openrouter_messages
