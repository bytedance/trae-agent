# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Ollama API client wrapper with tool integration
"""

import json
from typing import override

import openai
from ollama import chat as ollama_chat
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    ResponseFunctionToolCallParam,
    ResponseInputParam,
)
from openai.types.responses.response_input_param import FunctionCallOutput

from ..tools.base import Tool, ToolCall, ToolResult
from ..utils.config import ModelParameters
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse
from .retry_utils import retry_with


class OllamaClient(BaseLLMClient):
    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)

        self.client: openai.OpenAI = openai.OpenAI(
            # by default ollama doesn't require any api key. It should set to be "ollama".
            api_key=self.api_key,
            base_url=model_parameters.base_url
            if model_parameters.base_url
            else "http://localhost:11434/v1",
        )

        self.message_history: ResponseInputParam = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        self.message_history = self.parse_messages(messages)

    def _create_ollama_response(
        self,
        model_parameters: ModelParameters,
        tool_schemas: list[FunctionToolParam] | None,
    ):
        """Create a response using Ollama API. This method will be decorated with retry logic."""
        tools_param = None
        if tool_schemas:
            tools_param = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool["parameters"],
                    },
                }
                for tool in tool_schemas
            ]
        return ollama_chat(
            messages=self.message_history,
            model=model_parameters.model,
            tools=tools_param,
            # temperature=model_parameters.temperature,
            # top_p=model_parameters.top_p,
            # max_output_tokens=model_parameters.max_tokens,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_parameters: ModelParameters,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to Ollama with optional tool support."""
        openai_messages: ResponseInputParam = self.parse_messages(messages)

        tool_schemas = None
        if tools:
            tool_schemas = [
                FunctionToolParam(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.get_input_schema(),
                    strict=True,
                    type="function",
                )
                for tool in tools
            ]

        if reuse_history:
            self.message_history = self.message_history + openai_messages
        else:
            self.message_history = openai_messages

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_ollama_response,
            service_name="Ollama",
            max_retries=model_parameters.max_retries,
        )
        response = retry_decorator(model_parameters, tool_schemas)

        content = response.message.content
        tool_calls: list[ToolCall] = []
        if response.message.tool_calls:
            for output_block in response.message.tool_calls:
                if output_block.type == "function_call":
                    tool_calls.append(
                        ToolCall(
                            call_id=output_block.call_id,
                            name=output_block.name,
                            arguments=json.loads(output_block.arguments)
                            if output_block.arguments
                            else {},
                            id=output_block.id,
                        )
                    )
                    tool_call_param = ResponseFunctionToolCallParam(
                        arguments=output_block.arguments,
                        call_id=output_block.call_id,
                        name=output_block.name,
                        type="function_call",
                    )
                    if output_block.status:
                        tool_call_param["status"] = output_block.status
                    if output_block.id:
                        tool_call_param["id"] = output_block.id
                    self.message_history.append(tool_call_param)
                elif output_block.type == "message":
                    for content_block in output_block.content:
                        if content_block.type == "output_text":
                            content += content_block.text

        if content != "":
            self.message_history.append(
                EasyInputMessageParam(content=content, role="assistant", type="message")
            )
        usage = None
        # ollama doesn't provide usage
        # TODO is there any method that we could actually count the token ?
        """
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=response.usage.input_tokens_details.cached_tokens,
            reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens,
        )
        """

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.done_reason,
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="ollama",
                model=model_parameters.model,
                tools=tools,
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """
        Check if the current model supports tool calling.
        TODO: there should be a more robust way to handle tool_support check or we have to manually type every supported model which is not really that feasible. for example deepseek familay has deepseek:1.5b deepseek:7b ...
        """
        tool_support_model = [
            "deepseek-r1",
            "qwen3",
            "llama3.1",
            "llama3.2",
            "mistral",
            "qwen2.5",
            "qwen2.5-coder",
            "mistral-nemo",
            "llama3.3",
            "qwq",
            "mistral-small",
            "mixtral",
            "smollm2",
            "llama4",
            "command-r",
            "hermes3",
            "phi4-mini",
            "granite3.3",
            "devstral",
            "mistral-small3.1",
        ]

        return any(model in model_parameters.model for model in tool_support_model)

    def parse_messages(self, messages: list[LLMMessage]) -> ResponseInputParam:
        """
        Ollama parse messages should be compatible with openai handling
        """
        openai_messages: ResponseInputParam = []
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

    def parse_tool_call(self, tool_call: ToolCall) -> ResponseFunctionToolCallParam:
        """Parse the tool call from the LLM response."""
        return ResponseFunctionToolCallParam(
            call_id=tool_call.call_id,
            name=tool_call.name,
            arguments=json.dumps(tool_call.arguments),
            type="function_call",
        )

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> FunctionCallOutput:
        """Parse the tool call result from the LLM response."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += tool_call_result.error
        result = result.strip()

        return FunctionCallOutput(
            call_id=tool_call_result.call_id,
            id=tool_call_result.id,
            output=result,
            type="function_call_output",
        )
