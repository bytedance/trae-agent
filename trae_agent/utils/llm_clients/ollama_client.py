# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Ollama API client wrapper with tool integration
"""

import json
import uuid
from typing_extensions import override

from ollama import chat as ollama_chat  # pyright: ignore[reportUnknownVariableType]

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse
from trae_agent.utils.llm_clients.retry_utils import retry_with


class OllamaClient(BaseLLMClient):
    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

        # P0-3 修复:之前这里创建了 openai.OpenAI 客户端但从未使用 — 实际
        # 的 LLM 调用走 ollama_python 的 `ollama.chat()`,self.client
        # 完全 dead code。删掉,避免误导。
        self.message_history: list[dict] = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        self.message_history = self.parse_messages(messages)

    def _create_ollama_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[dict] | None,
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
            model=model_config.model,
            tools=tools_param,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """
        A rewritten version of ollama chat
        """
        msgs: list[dict] = self.parse_messages(messages)

        tool_schemas = None
        if tools:
            tool_schemas = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.get_input_schema(),
                }
                for tool in tools
            ]

        # Agent sends the full accumulated message history on each call.
        # Replace history to avoid duplication.
        self.message_history = msgs

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_ollama_response,
            provider_name="Ollama",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(model_config, tool_schemas)

        content = ""
        tool_calls: list[ToolCall] = []

        if response.message.tool_calls:
            for tool in response.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=self._id_generator(),
                        name=tool.function.name,
                        arguments=dict(tool.function.arguments),
                        id=self._id_generator(),
                    )
                )
        else:
            # consider response is not a tool call
            content = response.message.content or ""

        llm_response = LLMResponse(
            content=content,
            usage=None,
            model=model_config.model,
            finish_reason=None,  # seems can't get finish reason will check docs soon
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="ollama",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> list[dict]:
        """
        Ollama parse messages using native Ollama message format.
        """
        ollama_messages: list[dict] = []
        for msg in messages:
            if msg.tool_result:
                ollama_messages.append(self.parse_tool_call_result(msg.tool_result))
            elif msg.tool_call:
                ollama_messages.append(self.parse_tool_call(msg.tool_call))
            else:
                if not msg.content:
                    raise ValueError("Message content is required")
                if msg.role == "system":
                    ollama_messages.append({"role": "system", "content": msg.content})
                elif msg.role == "user":
                    ollama_messages.append({"role": "user", "content": msg.content})
                elif msg.role == "assistant":
                    ollama_messages.append({"role": "assistant", "content": msg.content})
                else:
                    raise ValueError(f"Invalid message role: {msg.role}")
        return ollama_messages

    def parse_tool_call(self, tool_call: ToolCall) -> dict:
        """Parse the tool call for Ollama format."""
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                }
            ],
        }

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> dict:
        """Parse the tool call result for Ollama format."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += tool_call_result.error
        result = result.strip()

        return {
            "role": "tool",
            "content": result,
        }

    def _id_generator(self) -> str:
        """Generate a random ID string"""
        return str(uuid.uuid4())
