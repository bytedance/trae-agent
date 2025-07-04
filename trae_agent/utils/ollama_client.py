# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Ollama API client wrapper with native API support."""

import os
import json
import random
import time
import requests
from typing import override

from ..tools.base import Tool, ToolCall, ToolResult
from ..utils.config import ModelParameters
from .base_client import BaseLLMClient
from .llm_basics import LLMMessage, LLMResponse, LLMUsage


class OllamaClient(BaseLLMClient):
    """Ollama client wrapper using native Ollama API."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters)
        
        # Ollama doesn't need API key
        self.api_key = "ollama"
        
        # Default Ollama endpoint
        self.base_url = model_parameters.base_url or "http://localhost:11434"
        
        # Remove /v1 suffix if present (Ollama native API doesn't use it)
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
            
        self.message_history: list[dict] = []

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    @override
    def chat(self, messages: list[LLMMessage], model_parameters: ModelParameters, tools: list[Tool] | None = None, reuse_history: bool = True) -> LLMResponse:
        """Send chat messages to Ollama using native API."""
        ollama_messages: list[dict] = self.parse_messages(messages)

        if reuse_history:
            self.message_history = self.message_history + ollama_messages
        else:
            self.message_history = ollama_messages

        # Prepare request payload for Ollama native API
        payload = {
            "model": model_parameters.model,
            "messages": self.message_history,
            "stream": False,
            "options": {
                "temperature": model_parameters.temperature,
                "top_p": model_parameters.top_p,
                "num_predict": model_parameters.max_tokens
            }
        }

        # Add tools if available (Ollama has limited tool support)
        if tools and self.supports_tool_calling(model_parameters):
            # Ollama tool format is different from OpenAI
            payload["tools"] = [self._convert_tool_to_ollama_format(tool) for tool in tools]

        response = None
        error_message = ""
        
        for i in range(model_parameters.max_retries):
            try:
                # Use Ollama's native /api/chat endpoint
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=60
                )
                response.raise_for_status()
                response_data = response.json()
                break
            except Exception as e:
                error_message += f"Error {i + 1}: {str(e)}\n"
                # Shorter sleep for local service
                time.sleep(random.randint(1, 5))
                continue

        if response is None or not response_data:
            raise ValueError(f"Failed to get response from Ollama after max retries: {error_message}")

        # Parse Ollama response
        content = response_data.get("message", {}).get("content", "")
        tool_calls: list[ToolCall] = []

        # Handle tool calls if present (Ollama format)
        if "tool_calls" in response_data.get("message", {}):
            for tool_call in response_data["message"]["tool_calls"]:
                tool_calls.append(ToolCall(
                    call_id=tool_call.get("id", ""),
                    name=tool_call.get("function", {}).get("name", ""),
                    arguments=tool_call.get("function", {}).get("arguments", {}),
                    id=tool_call.get("id", "")
                ))

        # Add assistant message to history
        assistant_message = {
            "role": "assistant",
            "content": content
        }
        self.message_history.append(assistant_message)

        # Ollama doesn't provide detailed usage stats
        usage = LLMUsage(
            input_tokens=response_data.get("prompt_eval_count", 0),
            output_tokens=response_data.get("eval_count", 0),
            cache_read_input_tokens=0,
            reasoning_tokens=0
        )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response_data.get("model", model_parameters.model),
            finish_reason="stop",  # Ollama doesn't provide finish_reason
            tool_calls=tool_calls if len(tool_calls) > 0 else None
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="ollama",
                model=model_parameters.model,
                tools=tools
            )

        return llm_response

    @override
    def supports_tool_calling(self, model_parameters: ModelParameters) -> bool:
        """Check if the current model supports tool calling."""
        # Ollama has limited tool support, mainly in newer models
        tool_capable_models = [
            "llama3.1", "llama3.2", "mistral", "codellama"
        ]
        
        model_name = model_parameters.model.lower()
        return any(model in model_name for model in tool_capable_models)

    def parse_messages(self, messages: list[LLMMessage]) -> list[dict]:
        """Parse the messages to Ollama native format."""
        ollama_messages: list[dict] = []
        for msg in messages:
            if msg.tool_result:
                ollama_messages.append(self.parse_tool_call_result(msg.tool_result))
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
                ollama_messages.append(message)
        
        return ollama_messages

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> dict:
        """Parse the tool call result to Ollama format."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += f"Error: {tool_call_result.error}"
        result = result.strip()

        return {
            "role": "tool",
            "content": result
        }

    def _convert_tool_to_ollama_format(self, tool: Tool) -> dict:
        """Convert tool to Ollama's expected format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_input_schema()
            }
        }

    def check_connection(self) -> bool:
        """Check if Ollama service is running."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def list_models(self) -> list[str]:
        """List available models in Ollama."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
        except:
            pass
        return []
