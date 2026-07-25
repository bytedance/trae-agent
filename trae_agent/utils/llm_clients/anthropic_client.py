# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Anthropic API client wrapper with tool integration."""

from typing_extensions import override

import anthropic
from anthropic.types.tool_union_param import TextEditor20250429

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class AnthropicClient(BaseLLMClient):
    """Anthropic client wrapper with tool schema generation."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

        self.client: anthropic.Anthropic = anthropic.Anthropic(
            api_key=self.api_key, base_url=self.base_url
        )
        self.message_history: list[anthropic.types.MessageParam] = []
        self.system_message: str | anthropic.NotGiven = anthropic.NOT_GIVEN

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        # P0-4 修复:parse_messages 现在返回 (messages, system_message) tuple。
        # set_chat_history 只关心 message_history,丢弃 system 部分(它由
        # 每次 chat() 调用时从 messages 重新提取)。
        parsed_messages, _ = self.parse_messages(messages)
        self.message_history = parsed_messages

    def _create_anthropic_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven,
        system_message: str | anthropic.NotGiven = anthropic.NOT_GIVEN,
    ) -> anthropic.types.Message:
        """Create a response using Anthropic API. This method will be decorated with retry logic."""
        return self.client.messages.create(
            model=model_config.model,
            messages=self.message_history,
            # max_tokens 是 Anthropic 必填项;config 默认 None 时必须给一个兜底值。
            max_tokens=model_config.max_tokens or 4096,
            # P0-4 修复:从 chat() 调用方传入的局部变量读取 system prompt,
            # 不再依赖 self.system_message(被 parse_messages 直接改的实例状态)。
            system=system_message,
            tools=tool_schemas,
            temperature=model_config.temperature,
            top_p=model_config.top_p,
            # Anthropic 不接受 top_k=0(要求 >= 1),未配置时交给 SDK 用默认值(传 NOT_GIVEN)。
            top_k=model_config.top_k if model_config.top_k > 0 else anthropic.NOT_GIVEN,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to Anthropic with optional tool support."""
        # P0-4 修复:之前每次 chat() 都直接修改 self.system_message,
        # 同一个 client 实例被复用于多个任务时,上一个任务的 system prompt
        # 会污染下一个任务。现在改为局部变量 + 提取后传 API。
        parsed_messages, system_message = self.parse_messages(messages)

        # Agent sends the full accumulated message history on each call.
        # Replace history to avoid duplication.
        self.message_history = parsed_messages

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

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_anthropic_response,
            provider_name="Anthropic",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(model_config, tool_schemas, system_message)

        # Handle tool calls in response
        content = ""
        tool_calls: list[ToolCall] = []
        # 同一 assistant turn 的所有 content blocks 必须合并到一条 message 里。
        assistant_blocks: list = []

        for content_block in response.content:
            if content_block.type == "text":
                content += content_block.text
                assistant_blocks.append(content_block.text)
            elif content_block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        call_id=content_block.id,
                        name=content_block.name,
                        arguments=content_block.input,  # pyright: ignore[reportArgumentType]
                    )
                )
                assistant_blocks.append(content_block)

        # P0 修复:原代码把每个 block 单独 append 成一条 assistant message,
        # 导致含 thinking/text+tool_use 的响应里出现孤儿 text 段,API 直接拒绝。
        # 正确做法是合并成一条 message(content 为 block 列表)。
        if assistant_blocks:
            self.message_history.append(
                anthropic.types.MessageParam(role="assistant", content=assistant_blocks)
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
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[list[anthropic.types.MessageParam], str | anthropic.NotGiven]:
        """Parse messages to Anthropic format.

        Returns a tuple ``(anthropic_messages, system_message)`` so callers
        can pass the system message to the API without mutating instance
        state (P0-4 fix).
        """
        anthropic_messages: list[anthropic.types.MessageParam] = []
        system_message: str | anthropic.NotGiven = anthropic.NOT_GIVEN
        for msg in messages:
            if msg.role == "system":
                # P0-4 修复:用局部变量累积 system prompt,不修改 self。
                # Anthropic API 的 system 参数只接受一条字符串,所以多个
                # system 消息会被 join 起来(取第一个非空的;若有多个则用
                # \n\n 拼起来)。
                if msg.content:
                    if system_message is anthropic.NOT_GIVEN:
                        system_message = msg.content
                    elif isinstance(system_message, str):
                        system_message = system_message + "\n\n" + msg.content
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
        return anthropic_messages, system_message

    def parse_tool_call(self, tool_call: ToolCall) -> anthropic.types.ToolUseBlockParam:
        """Parse the tool call from the LLM response."""
        # P0 修复:Anthropic 期望 input 是 dict,原代码 json.dumps 成字符串会
        # 触发 "Input should be a valid dictionary"。tool_call.arguments 已是 dict。
        return anthropic.types.ToolUseBlockParam(
            type="tool_use",
            id=tool_call.call_id,
            name=tool_call.name,
            input=tool_call.arguments,
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

        # Provide a default error message if the tool failed but didn't provide details
        if not tool_call_result.success and not result:
            result = "Tool execution failed without providing error details."

        return anthropic.types.ToolResultBlockParam(
            tool_use_id=tool_call_result.call_id,
            type="tool_result",
            content=result,
            is_error=not tool_call_result.success,
        )
