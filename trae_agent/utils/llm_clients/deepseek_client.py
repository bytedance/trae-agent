# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenAI API client wrapper with tool integration."""

import json
from typing import override

import openai
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from openai.types.chat.chat_completion import ChatCompletion

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class DeepSeekClient(BaseLLMClient):
    """DeepSeek client wrapper with tool schema generation."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

        self.client: openai.OpenAI = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.message_history: list[ChatCompletionMessageParam] = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    def _create_deepseek_response(
        self,
        api_call_input: list[ChatCompletionMessageParam],
        model_config: ModelConfig,
        tool_schemas: list[ChatCompletionToolParam] | None,
    ) -> ChatCompletion:
        """Create a response using DeepSeek API. This method will be decorated with retry logic."""
        return self.client.chat.completions.create(
            messages=api_call_input,
            model=model_config.model,
            tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            max_tokens=model_config.max_tokens,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to DeepSeek with optional tool support."""
        openai_messages: list[ChatCompletionMessageParam] = self.parse_messages(messages)

        tool_schemas: list[ChatCompletionToolParam] | None = None
        if tools:
            tool_schemas = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.get_input_schema(),
                    },
                }
                for tool in tools
            ]

        api_call_input: list[ChatCompletionMessageParam] = []
        if reuse_history:
            api_call_input.extend(self.message_history)
        api_call_input.extend(openai_messages)

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_deepseek_response,
            provider_name="DeepSeek",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(api_call_input, model_config, tool_schemas)

        response_message = response.choices[0].message
        content = response_message.content or ""
        tool_calls: list[ToolCall] = []

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=json.loads(tool_call.function.arguments),
                        id=tool_call.id,
                    )
                )
            self.message_history.append(
                {
                    "role": "assistant",
                    "tool_calls": response_message.tool_calls,
                }
            )

        if content:
            self.message_history.append({"role": "assistant", "content": content})

        usage = None
        if response.usage:
            usage = LLMUsage(
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.choices[0].finish_reason,
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="deepseek",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
        """Parse the messages to OpenAI format."""
        openai_messages: list[ChatCompletionMessageParam] = []
        for msg in messages:
            if msg.tool_result:
                openai_messages.append(self.parse_tool_call_result(msg.tool_result))
            elif msg.tool_call:
                openai_messages.append(self.parse_tool_call(msg.tool_call))
            else:
                if not msg.content:
                    raise ValueError("Message content is required")
                if msg.role == "system":
                    openai_messages.append({"role": "system", "content": msg.content})
                elif msg.role == "user":
                    openai_messages.append({"role": "user", "content": msg.content})
                elif msg.role == "assistant":
                    openai_messages.append({"role": "assistant", "content": msg.content})
                else:
                    raise ValueError(f"Invalid message role: {msg.role}")
        return openai_messages

    def parse_tool_call(self, tool_call: ToolCall) -> ChatCompletionMessageParam:
        """Parse the tool call from the LLM response."""
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                }
            ],
        }

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> ChatCompletionMessageParam:
        """Parse the tool call result from the LLM response to FunctionCallOutput format."""
        result_content: str = ""
        if tool_call_result.result is not None:
            result_content += str(tool_call_result.result)
        if tool_call_result.error:
            result_content += f"\nError: {tool_call_result.error}"
        result_content = result_content.strip()

        return {
            "role": "tool",
            "tool_call_id": tool_call_result.call_id,
            "content": result_content,
        }
