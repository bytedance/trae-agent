# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenAI-compatible API client wrapper with tool integration."""

import os
import json
import random
import time
import openai
from typing import override

from ..tools.base import Tool, ToolCall, ToolResult
from ..utils.config import ModelParameters
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse, LLMUsage


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI-compatible client wrapper for services like OpenRouter, Together AI, etc."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)

        # Validate that base_url is provided for OpenAI-compatible services
        if not model_parameters.base_url:
            raise ValueError("base_url is required for OpenAI-compatible services. Please specify the API endpoint in your configuration.")

        # Get API key from model parameters or environment
        if self.api_key == "":
            # Try different environment variables based on the base_url
            if "openrouter.ai" in model_parameters.base_url:
                self.api_key = os.getenv("OPENROUTER_API_KEY", "")
            elif "together.xyz" in model_parameters.base_url:
                self.api_key = os.getenv("TOGETHER_API_KEY", "")
            elif "groq.com" in model_parameters.base_url:
                self.api_key = os.getenv("GROQ_API_KEY", "")
            elif "deepseek.com" in model_parameters.base_url:
                self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
            elif "aliyuncs.com" in model_parameters.base_url:
                self.api_key = os.getenv("ALIBABA_API_KEY", "")
            elif "novita.ai" in model_parameters.base_url:
                self.api_key = os.getenv("NOVITA_API_KEY", "")
            else:
                self.api_key = os.getenv("OPENAI_API_KEY", "")

        if self.api_key == "":
            service_name = self._get_service_name_from_url(model_parameters.base_url)
            raise ValueError(f"API key not provided for {service_name}. Set the appropriate environment variable or config file.")

        # Initialize client with custom base_url
        client_kwargs = {
            "api_key": self.api_key,
            "base_url": model_parameters.base_url
        }

        self.client: openai.OpenAI = openai.OpenAI(**client_kwargs)
        self.message_history: list[dict] = []

    def _get_service_name_from_url(self, base_url: str) -> str:
        """Extract service name from base URL for better error messages."""
        if "openrouter.ai" in base_url:
            return "OpenRouter"
        elif "together.xyz" in base_url:
            return "Together AI"
        elif "groq.com" in base_url:
            return "Groq"
        elif "deepseek.com" in base_url:
            return "DeepSeek"
        elif "aliyuncs.com" in base_url:
            return "Alibaba Cloud (DashScope)"
        elif "novita.ai" in base_url:
            return "Novita AI"
        else:
            return "OpenAI-compatible service"

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    @override
    def chat(self, messages: list[LLMMessage], model_parameters: ModelParameters, tools: list[Tool] | None = None, reuse_history: bool = True) -> LLMResponse:
        """Send chat messages to OpenAI-compatible service with optional tool support."""
        openai_messages: list[dict] = self.parse_messages(messages)

        tool_schemas = None
        if tools and self.supports_tool_calling(model_parameters):
            tool_schemas = [{
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.get_input_schema()
                }
            } for tool in tools]

        if reuse_history:
            self.message_history = self.message_history + openai_messages
        else:
            self.message_history = openai_messages

        response = None
        error_message = ""
        for i in range(model_parameters.max_retries):
            try:
                # Prepare request parameters
                request_params = {
                    "model": model_parameters.model,
                    "messages": self.message_history,
                    "temperature": model_parameters.temperature,
                    "top_p": model_parameters.top_p,
                    "max_tokens": model_parameters.max_tokens,
                }

                # Add tools if available and supported
                if tool_schemas:
                    request_params["tools"] = tool_schemas
                    if model_parameters.parallel_tool_calls:
                        request_params["tool_choice"] = "auto"

                response = self.client.chat.completions.create(**request_params)
                break
            except Exception as e:
                error_message += f"Error {i + 1}: {str(e)}\n"
                # Randomly sleep for 3-30 seconds
                time.sleep(random.randint(3, 30))
                continue

        if response is None:
            raise ValueError(f"Failed to get response from OpenAI-compatible service after max retries: {error_message}")

        content = response.choices[0].message.content or ""
        tool_calls: list[ToolCall] = []

        # Handle tool calls if present
        if response.choices[0].message.tool_calls:
            for tool_call in response.choices[0].message.tool_calls:
                tool_calls.append(ToolCall(
                    call_id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=json.loads(tool_call.function.arguments) if tool_call.function.arguments else {},
                    id=tool_call.id
                ))

        # Add assistant message to history
        assistant_message = {
            "role": "assistant",
            "content": content
        }
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments)
                    }
                } for tc in tool_calls
            ]

        self.message_history.append(assistant_message)

        # Parse usage information
        usage = None
        if response.usage:
            # Handle token details safely - they might be objects or dicts
            cache_tokens = 0
            reasoning_tokens = 0
            
            if hasattr(response.usage, 'prompt_tokens_details') and response.usage.prompt_tokens_details:
                prompt_details = response.usage.prompt_tokens_details
                if hasattr(prompt_details, 'cached_tokens'):
                    cache_tokens = prompt_details.cached_tokens
                elif isinstance(prompt_details, dict):
                    cache_tokens = prompt_details.get('cached_tokens', 0)
            
            if hasattr(response.usage, 'completion_tokens_details') and response.usage.completion_tokens_details:
                completion_details = response.usage.completion_tokens_details
                if hasattr(completion_details, 'reasoning_tokens'):
                    reasoning_tokens = completion_details.reasoning_tokens
                elif isinstance(completion_details, dict):
                    reasoning_tokens = completion_details.get('reasoning_tokens', 0)
            
            usage = LLMUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                cache_read_input_tokens=cache_tokens,
                reasoning_tokens=reasoning_tokens
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.choices[0].finish_reason,
            tool_calls=tool_calls if len(tool_calls) > 0 else None
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="openai_compatible",
                model=model_parameters.model,
                tools=tools
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        # Common models that support tool calling
        tool_capable_models = [
            # OpenAI models
            "gpt-4", "gpt-3.5-turbo",
            # Anthropic models via OpenRouter
            "claude-3", "claude-3.5",
            # Other popular models
            "llama-3", "mixtral", "qwen", "deepseek",
            # Meta models
            "meta-llama",
            # Mistral models
            "mistral",
            # Google models
            "gemini",
            # Alibaba models
            "qwen-turbo", "qwen-plus", "qwen-max"
        ]
        
        model_name = model_parameters.model.lower()
        return any(model in model_name for model in tool_capable_models)

    def parse_messages(self, messages: list[LLMMessage]) -> list[dict]:
        """Parse the messages to OpenAI-compatible format."""
        openai_messages: list[dict] = []
        for msg in messages:
            if msg.tool_result:
                openai_messages.append(self.parse_tool_call_result(msg.tool_result))
            elif msg.tool_call:
                # Tool calls are handled in the assistant message
                continue
            else:
                if not msg.content:
                    raise ValueError("Message content is required")
                
                message = {
                    "role": msg.role,
                    "content": msg.content
                }
                openai_messages.append(message)
        
        return openai_messages

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> dict:
        """Parse the tool call result to OpenAI-compatible format."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += f"Error: {tool_call_result.error}"
        result = result.strip()

        return {
            "role": "tool",
            "tool_call_id": tool_call_result.call_id,
            "content": result
        }
