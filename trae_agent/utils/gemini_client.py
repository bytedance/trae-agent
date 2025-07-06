# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Google Gemini API client wrapper with tool integration."""
import os
import time
import random
import json
from typing import override
import google.generativeai as genai
from google.generativeai.types import content_types

from ..tools.base import Tool, ToolCall
from ..utils.config import ModelParameters
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse, LLMUsage


class GeminiClient(BaseLLMClient):
    """Gemini client wrapper with tool schema generation."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)

        if self.api_key == "":
            self.api_key: str = os.getenv("GOOGLE_API_KEY", "")

        if self.api_key == "":
            raise ValueError("Google API key not provided. Set GOOGLE_API_KEY in environment variables or config file.")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(model_parameters.model)
        self.chat = None
        self.message_history = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)
        self.chat = self.model.start_chat(history=self.message_history)

    @override
    def chat(self, messages: list[LLMMessage], model_parameters: ModelParameters, tools: list[Tool] | None = None, reuse_history: bool = True) -> LLMResponse:
        """Send chat messages to Gemini with optional tool support."""
        gemini_messages = self.parse_messages(messages)

        if reuse_history:
            if self.chat is None:
                self.chat = self.model.start_chat(history=self.message_history + gemini_messages)
            else:
                self.message_history = self.message_history + gemini_messages
        else:
            self.chat = self.model.start_chat(history=gemini_messages)
            self.message_history = gemini_messages

        # Add tools if provided
        if tools:
            tool_schemas = {
                tool.name: {
                    "description": tool.description,
                    "parameters": tool.get_input_schema()
                } for tool in tools
            }
            self.model.tools = tool_schemas

        response = None
        error_message = ""
        for i in range(model_parameters.max_retries):
            try:
                response = self.chat.send_message(
                    content=messages[-1].content,
                    generation_config=genai.types.GenerationConfig(
                        temperature=model_parameters.temperature,
                        top_p=model_parameters.top_p,
                        top_k=model_parameters.top_k,
                        max_output_tokens=model_parameters.max_tokens,
                    )
                )
                break
            except Exception as e:
                error_message += f"Error {i + 1}: {str(e)}\n"
                time.sleep(random.randint(3, 30))
                continue

        if response is None:
            raise ValueError(f"Failed to get response from Gemini after max retries: {error_message}")

        content = ""
        tool_calls = []

        # Parse response content and tool calls
        if response.text:
            content = response.text

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if isinstance(part, content_types.FunctionCall):
                    tool_calls.append(ToolCall(
                        call_id=part.name,  # Gemini doesn't provide call IDs, using function name
                        name=part.name,
                        arguments=json.loads(part.args)
                    ))

        # Update message history
        if content:
            self.message_history.append({
                "role": "model",
                "parts": [{"text": content}]
            })

        usage = None
        if hasattr(response, 'usage'):
            usage = LLMUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=model_parameters.model,
            finish_reason="stop",  # Gemini doesn't provide finish reason
            tool_calls=tool_calls if tool_calls else None
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="gemini",
                model=model_parameters.model,
                tools=tools
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        tool_capable_models = [
            "gemini-pro",
            "gemini-ultra",
            "gemini-1.0-pro",
            "gemini-1.0-ultra",
        ]
        return any(model in model_parameters.model for model in tool_capable_models)

    def parse_messages(self, messages: list[LLMMessage]) -> list[dict]:
        """Parse the messages to Gemini format."""
        gemini_messages = []
        for msg in messages:
            if msg.tool_result:
                gemini_messages.append({
                    "role": "function",
                    "parts": [{
                        "function_response": {
                            "name": msg.tool_result.id,
                            "response": {
                                "content": msg.tool_result.result if msg.tool_result.result else msg.tool_result.error
                            }
                        }
                    }]
                })
            elif msg.tool_call:
                gemini_messages.append({
                    "role": "model",
                    "parts": [{
                        "function_call": {
                            "name": msg.tool_call.name,
                            "args": json.dumps(msg.tool_call.arguments)
                        }
                    }]
                })
            else:
                if msg.role == "system":
                    role = "user"
                elif msg.role == "user":
                    role = "user"
                elif msg.role == "assistant":
                    role = "model"
                else:
                    continue

                gemini_messages.append({
                    "role": role,
                    "parts": [{"text": msg.content}] if msg.content else []
                })

        return gemini_messages
