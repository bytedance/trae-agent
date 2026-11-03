# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Offline tests for tool history sent by Chat Completions clients."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import openai
import pytest

from trae_agent.tools.base import Tool, ToolCall, ToolExecutor
from trae_agent.tools.json_edit_tool import JSONEditTool
from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.azure_client import AzureClient, AzureProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.openai_compatible_base import (
    OpenAICompatibleClient,
    ProviderConfig,
)
from trae_agent.utils.llm_clients.openrouter_client import OpenRouterClient, OpenRouterProvider


@pytest.mark.parametrize("provider", ["openrouter", "azure"])
@pytest.mark.parametrize("history_mode", ["set_history", "replace", "live"])
@pytest.mark.parametrize("tool_count", [1, 2])
@pytest.mark.asyncio
async def test_tool_history_preserves_calls_and_results(
    tmp_path: Path, provider: str, history_mode: str, tool_count: int
) -> None:
    """Restored and live tool turns send matching assistant calls and results."""
    config = ModelConfig(
        model="test-model",
        model_provider=ModelProvider(
            api_key="offline-test-key",
            provider=provider,
            base_url="https://offline.test",
            api_version="2024-10-21",
        ),
        temperature=0,
        top_p=1,
        top_k=1,
        parallel_tool_calls=True,
        max_retries=0,
        max_tokens=128,
    )
    calls = []
    for index in range(tool_count):
        path = tmp_path / f"input-{index}.json"
        path.write_text(json.dumps({"value": index}), encoding="utf-8")
        calls.append(
            ToolCall(
                call_id=f"read-{index}",
                name="json_edit_tool",
                arguments={"operation": "view", "file_path": str(path)},
            )
        )
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body["messages"][-1] == {"role": "user", "content": "begin"}:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in calls
                ],
            }
            finish_reason = "tool_calls"
        else:
            message = {"role": "assistant", "content": "finished"}
            finish_reason = "stop"
        return httpx.Response(
            200,
            json={
                "id": "completion",
                "object": "chat.completion",
                "created": 0,
                "model": config.model,
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            },
        )

    tools: list[Tool] = [JSONEditTool(provider)]
    executor = ToolExecutor(tools)
    adapter_class: type[OpenAICompatibleClient]
    provider_class: type[ProviderConfig]
    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        if provider == "azure":
            sdk = openai.AzureOpenAI(
                azure_endpoint="https://offline.test",
                api_version=config.model_provider.api_version,
                api_key="offline-test-key",
                http_client=http_client,
            )
            adapter_class, provider_class = AzureClient, AzureProvider
        else:
            sdk = openai.OpenAI(
                base_url="https://offline.test", api_key="offline-test-key", http_client=http_client
            )
            adapter_class, provider_class = OpenRouterClient, OpenRouterProvider
        with sdk, patch.object(provider_class, "create_client", return_value=sdk):
            client = adapter_class(config)
            initial = LLMMessage(role="user", content="begin")
            if history_mode == "live":
                first = client.chat([initial], config, tools=tools)
                assert first.tool_calls == calls
            results = await executor.parallel_tool_call(calls)
            assert all(result.success for result in results)
            result_messages = [
                LLMMessage(role="user", tool_result=result) for result in reversed(results)
            ]
            history = (
                [initial]
                + [LLMMessage(role="assistant", tool_call=call) for call in calls]
                + result_messages
            )
            if history_mode == "set_history":
                client.set_chat_history(history)
                response = client.chat([], config, tools=tools)
            elif history_mode == "replace":
                response = client.chat(history, config, tools=tools, reuse_history=False)
            else:
                response = client.chat(result_messages, config, tools=tools)

    messages = requests[-1]["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"] + [
        "tool"
    ] * tool_count
    restored_calls = messages[1]["tool_calls"]
    assert [call["id"] for call in restored_calls] == [call.call_id for call in calls]
    assert [json.loads(call["function"]["arguments"]) for call in restored_calls] == [
        call.arguments for call in calls
    ]
    assert all(call["function"]["name"] == "json_edit_tool" for call in restored_calls)
    for message, result in zip(messages[2:], reversed(results), strict=True):
        assert message["tool_call_id"] == result.call_id
        assert result.result is not None
        assert message["content"] == result.result.strip()
    assert response.content == "finished"
