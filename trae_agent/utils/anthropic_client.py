# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Anthropic API client wrapper with tool integration."""

import json
import random
import time
from typing import override

import anthropic
from anthropic.types.tool_union_param import TextEditor20250429

from ..tools.base import Tool, ToolCall, ToolResult
from ..utils.config import ModelParameters
from ..utils.llm_basics import LLMMessage, LLMResponse, LLMUsage
from .base_client import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    """Anthropic client wrapper with tool schema generation."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)

        self.client: anthropic.Anthropic = anthropic.Anthropic(
            api_key=self.api_key, base_url=self.base_url
        )
        self.message_history: list[anthropic.types.MessageParam] = []
        self.system_message: str | anthropic.NotGiven = anthropic.NOT_GIVEN

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
        """Send chat messages to Anthropic with optional tool support."""
        # Convert messages to Anthropic format
        anthropic_messages: list[anthropic.types.MessageParam] = self.parse_messages(messages)

        self.message_history = (
            self.message_history + anthropic_messages if reuse_history else anthropic_messages
        )

        # Add tools if provided
        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven = (
            anthropic.NOT_GIVEN
        )
        if tools:
            tool_schemas = []
            for tool in tools:
                if tool.name == "str_replace_based_edit_tool":
                    tool_schemas.append(
                        TextEditor20250429(
                            name="str_replace_based_edit_tool",
                            type="text_editor_20250429",
                        )
                    )
                elif tool.name == "bash":
                    tool_schemas.append(
                        anthropic.types.ToolBash20250124Param(name="bash", type="bash_20250124")
                    )
                else:
                    tool_schemas.append(
                        anthropic.types.ToolParam(
                            name=tool.name,
                            description=tool.description,
                            input_schema=tool.get_input_schema(),
                        )
                    )

        response = None
        error_message = ""
        for i in range(model_parameters.max_retries):
            try:
                response = self.client.messages.create(
                    model=model_parameters.model,
                    messages=self.message_history,
                    max_tokens=model_parameters.max_tokens,
                    system=self.system_message,
                    tools=tool_schemas if tool_schemas else anthropic.NOT_GIVEN,
                    temperature=model_parameters.temperature,
                    top_p=model_parameters.top_p,
                    top_k=model_parameters.top_k,
                )
                break
            except Exception as e:
                error_message += f"Error {i + 1}: {str(e)}\n"
                # Randomly sleep for 3-30 seconds
                time.sleep(random.randint(3, 30))
                continue

        if response is None:
            raise ValueError(
                f"Failed to get response from Anthropic after max retries: {error_message}"
            )

        # Handle tool calls in response
        content = ""
        tool_calls: list[ToolCall] = []

        for content_block in response.content:
            if content_block.type == "text":
                content += content_block.text
                self.message_history.append(
                    anthropic.types.MessageParam(role="assistant", content=content_block.text)
                )
            elif content_block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        call_id=content_block.id,
                        name=content_block.name,
                        arguments=content_block.input,  # pyright: ignore[reportArgumentType]
                    )
                )
                self.message_history.append(
                    anthropic.types.MessageParam(role="assistant", content=[content_block])
                )

        usage = None
        if response.usage:
            usage = LLMUsage(
                input_tokens=response.usage.input_tokens or 0,
                output_tokens=response.usage.output_tokens or 0,
                cache_creation_input_tokens=response.usage.cache_creation_input_tokens or 0,
                cache_read_input_tokens=response.usage.cache_read_input_tokens or 0,
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.stop_reason,
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="anthropic",
                model=model_parameters.model,
                tools=tools,
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        tool_capable_models = [
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3-5-opus",
            "claude-3-5-sonnet",
            "claude-3-5-haiku",
            "claude-3-7-sonnet",
            "claude-4-opus",
            "claude-4-sonnet",
        ]
        return any(model in model_parameters.model for model in tool_capable_models)

    def parse_messages(self, messages: list[LLMMessage]) -> list[anthropic.types.MessageParam]:
        """Parse the messages to Anthropic format."""
        anthropic_messages: list[anthropic.types.MessageParam] = []
        for msg in messages:
            if msg.role == "system":
                self.system_message = msg.content if msg.content else anthropic.NOT_GIVEN
            elif msg.tool_result:
                anthropic_messages.append(
                    anthropic.types.MessageParam(
                        role="user",
                        content=[self.parse_tool_call_result(msg.tool_result)],
                    )
                )
            elif msg.tool_call:
                anthropic_messages.append(
                    anthropic.types.MessageParam(
                        role="assistant", content=[self.parse_tool_call(msg.tool_call)]
                    )
                )
            else:
                if msg.role == "user":
                    role = "user"
                elif msg.role == "assistant":
                    role = "assistant"
                else:
                    raise ValueError(f"Invalid message role: {msg.role}")

                if not msg.content:
                    raise ValueError("Message content is required")

                anthropic_messages.append(
                    anthropic.types.MessageParam(role=role, content=msg.content)
                )
        return anthropic_messages

    def parse_tool_call(self, tool_call: ToolCall) -> anthropic.types.ToolUseBlockParam:
        """Parse the tool call from the LLM response."""
        return anthropic.types.ToolUseBlockParam(
            type="tool_use",
            id=tool_call.call_id,
            name=tool_call.name,
            input=json.dumps(tool_call.arguments),
        )

    def parse_tool_call_result(
        self, tool_call_result: ToolResult
    ) -> anthropic.types.ToolResultBlockParam:
        """Parse the tool call result from the LLM response."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += "Tool call failed with error:\n"
            result += tool_call_result.error
        result = result.strip()

        return anthropic.types.ToolResultBlockParam(
            tool_use_id=tool_call_result.call_id,
            type="tool_result",
            content=result,
            is_error=not tool_call_result.success,
        )
