# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenAI API client wrapper with tool integration."""

import json
from typing_extensions import override

import openai
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    Response,
    ResponseFunctionToolCallParam,
    ResponseInputParam,
    ToolParam,
)
from openai.types.responses.response_input_param import FunctionCallOutput

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class OpenAIClient(BaseLLMClient):
    """OpenAI client wrapper with tool schema generation."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

        self.client: openai.OpenAI = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.message_history: ResponseInputParam = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    def _create_openai_response(
        self,
        api_call_input: ResponseInputParam,
        model_config: ModelConfig,
        tool_schemas: list[ToolParam] | None,
    ) -> Response:
        """Create a response using OpenAI API. This method will be decorated with retry logic."""
        return self.client.responses.create(
            input=api_call_input,
            model=model_config.model,
            tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
            temperature=model_config.temperature
            if "o3" not in model_config.model
            and "o4-mini" not in model_config.model
            and "gpt-5" not in model_config.model
            else openai.NOT_GIVEN,
            # top_p 未配置(None)时不能传给 SDK,否则 Invalid value。未设置走 NOT_GIVEN。
            top_p=model_config.top_p if model_config.top_p is not None else openai.NOT_GIVEN,
            max_output_tokens=model_config.max_tokens,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to OpenAI with optional tool support."""
        openai_messages: ResponseInputParam = self.parse_messages(messages)

        # Agent sends the full accumulated message history on each call.
        # Replace history to avoid duplication.
        self.message_history = openai_messages

        # P1-7 修复:Resume 时消息历史可能包含孤立的 function_call
        # (没有对应的 function_call_output),OpenAI API 会拒绝。
        # 清理:收集所有有对应 output 的 call_id,移除孤立的 function_call。
        self.message_history = self._sanitize_orphaned_function_calls(self.message_history)

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

        api_call_input: ResponseInputParam = self.message_history

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_openai_response,
            provider_name="OpenAI",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(api_call_input, model_config, tool_schemas)

        content = ""
        tool_calls: list[ToolCall] = []
        for output_block in response.output:
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
                parts: list[str] = []
                for content_block in output_block.content:
                    if content_block.type == "output_text":
                        parts.append(content_block.text)
                    elif content_block.type == "refusal":
                        # P1 修复:原代码只收 output_text,refusal 被静默丢弃,
                        # 用户看到"模型没说话"且无任何提示。这里把拒答回显。
                        refusal_text = getattr(content_block, "text", "") or ""
                        parts.append(
                            f"[MODEL REFUSAL] {refusal_text}"
                            if refusal_text
                            else "[MODEL REFUSAL] The model refused to answer."
                        )
                content = "".join(parts)

        if content != "":
            self.message_history.append(
                EasyInputMessageParam(content=content, role="assistant", type="message")
            )

        usage = None
        if response.usage:
            usage = LLMUsage(
                input_tokens=response.usage.input_tokens or 0,
                output_tokens=response.usage.output_tokens or 0,
                cache_read_input_tokens=response.usage.input_tokens_details.cached_tokens or 0,
                reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens or 0,
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.status,
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="openai",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> ResponseInputParam:
        """Parse the messages to OpenAI format."""
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
        """Parse the tool call result from the LLM response to FunctionCallOutput format."""
        result_content: str = ""
        if tool_call_result.result is not None:
            result_content += str(tool_call_result.result)
        if tool_call_result.error:
            result_content += f"\nError: {tool_call_result.error}"
        result_content = result_content.strip()

        return FunctionCallOutput(
            type="function_call_output",  # Explicitly set the type field
            call_id=tool_call_result.call_id,
            output=result_content,
        )

    @staticmethod
    def _sanitize_orphaned_function_calls(
        messages: ResponseInputParam,
    ) -> ResponseInputParam:
        """Remove orphaned function_call entries that lack a matching output.

        When resuming from a saved trajectory, the message history may contain
        function_call blocks whose corresponding function_call_output was never
        recorded (interruption happened mid-tool-call). The OpenAI Responses API
        rejects such malformed histories. This method filters them out.
        """
        # Collect call_ids that have matching outputs
        output_call_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, dict) and msg.get("type") == "function_call_output":
                output_call_ids.add(msg.get("call_id", ""))
            elif hasattr(msg, "call_id") and hasattr(msg, "type"):
                # FunctionCallOutput object
                if msg.type == "function_call_output":
                    output_call_ids.add(msg.call_id)

        sanitized: ResponseInputParam = []
        for msg in messages:
            # Check if this is a function_call without a matching output
            is_orphaned = False
            if isinstance(msg, dict) and msg.get("type") == "function_call":
                if msg.get("call_id") not in output_call_ids:
                    is_orphaned = True
            elif hasattr(msg, "type") and msg.type == "function_call":
                if not hasattr(msg, "call_id") or msg.call_id not in output_call_ids:
                    is_orphaned = True

            if not is_orphaned:
                sanitized.append(msg)

        return sanitized
