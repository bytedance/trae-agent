"""
Llama.cpp API client wrapper with tool integration
"""

import json
from typing import override

import openai
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import Function
from openai.types.shared_params import FunctionParameters

from ..tools.base import Tool, ToolCall
from ..utils.config import ModelParameters
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse, LLMUsage
from .retry_utils import retry_with


class LlamaCppClient(BaseLLMClient):
    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)

        self.client: openai.OpenAI = openai.OpenAI(
            api_key=self.api_key,
            base_url=model_parameters.base_url,
        )

        self.message_history: list[ChatCompletionMessageParam] = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        self.message_history = self.parse_messages(messages)

    def _create_llama_cpp_response(
        self,
        model_parameters: ModelParameters,
        tool_schemas: list[dict] | None,
    ) -> ChatCompletion:
        """Create a response using Llama.cpp API. This method will be decorated with retry logic."""
        return self.client.chat.completions.create(
            messages=self.message_history,
            model=model_parameters.model,
            tools=tool_schemas,
            temperature=model_parameters.temperature,
            top_p=model_parameters.top_p,
            max_tokens=model_parameters.max_tokens,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_parameters: ModelParameters,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to Llama.cpp with optional tool support."""
        llama_cpp_messages = self.parse_messages(messages)

        if reuse_history:
            self.message_history.extend(llama_cpp_messages)
        else:
            self.message_history = llama_cpp_messages

        tool_schemas = None
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

        retry_decorator = retry_with(
            func=self._create_llama_cpp_response,
            max_retries=model_parameters.max_retries,
        )
        response = retry_decorator(model_parameters, tool_schemas)

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls: list[ToolCall] = []

        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=json.loads(tool_call.function.arguments),
                    )
                )
            self.message_history.append(
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ChatCompletionMessageToolCallParam(
                            id=tc.call_id,
                            function=Function(
                                name=tc.name,
                                arguments=json.dumps(tc.arguments),
                            ),
                            type="function",
                        )
                        for tc in tool_calls
                    ],
                )
            )

        if content:
            self.message_history.append(
                ChatCompletionAssistantMessageParam(role="assistant", content=content)
            )

        usage = None
        if response.usage:
            usage = LLMUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls if tool_calls else None,
        )

        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="llama_cpp",
                model=model_parameters.model,
                tools=tools,
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        # For now, assume all models support tool calling.
        # This can be refined later based on specific model capabilities.
        return True

    def parse_messages(self, messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
        """Parse messages to a format compatible with Llama.cpp."""
        llama_cpp_messages: list[ChatCompletionMessageParam] = []
        for msg in messages:
            if msg.role == "system":
                llama_cpp_messages.append(
                    ChatCompletionSystemMessageParam(role="system", content=msg.content)
                )
            elif msg.role == "user":
                llama_cpp_messages.append(
                    ChatCompletionUserMessageParam(role="user", content=msg.content)
                )
            elif msg.role == "assistant":
                if msg.tool_call:
                    llama_cpp_messages.append(
                        ChatCompletionAssistantMessageParam(
                            role="assistant",
                            content=msg.content,
                            tool_calls=[
                                ChatCompletionMessageToolCallParam(
                                    id=msg.tool_call.call_id,
                                    function=Function(
                                        name=msg.tool_call.name,
                                        arguments=json.dumps(msg.tool_call.arguments),
                                    ),
                                    type="function",
                                )
                            ],
                        )
                    )
                else:
                    llama_cpp_messages.append(
                        ChatCompletionAssistantMessageParam(
                            role="assistant", content=msg.content
                        )
                    )
            elif msg.role == "tool":
                if msg.tool_result:
                    llama_cpp_messages.append(
                        ChatCompletionToolMessageParam(
                            role="tool",
                            content=msg.tool_result.result,
                            tool_call_id=msg.tool_result.call_id,
                        )
                    )
        return llama_cpp_messages