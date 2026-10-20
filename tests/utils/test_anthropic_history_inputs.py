import json

import anthropic
import httpx
import pytest

from trae_agent.tools.base import ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.anthropic_client import AnthropicClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


@pytest.mark.parametrize(
    "arguments",
    [{}, {"query": "中文"}, {"options": {"enabled": True, "limit": 3}, "items": [None, "x"]}],
)
def test_restored_tool_history_sends_an_object_input(arguments):
    config = ModelConfig(
        model="claude-test",
        model_provider=ModelProvider(api_key="test-key", provider="anthropic"),
        temperature=0,
        top_p=1,
        top_k=1,
        parallel_tool_calls=False,
        max_retries=0,
        max_tokens=128,
    )
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "done"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = AnthropicClient(config)
    client.client.close()
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client.client = anthropic.Anthropic(
            api_key="test-key", http_client=transport, max_retries=0
        )
        client.set_chat_history(
            [
                LLMMessage(role="user", content="Search"),
                LLMMessage(
                    role="assistant",
                    tool_call=ToolCall(name="search", call_id="tool_1", arguments=arguments),
                ),
            ]
        )
        response = client.chat(
            [
                LLMMessage(
                    role="user",
                    tool_result=ToolResult(
                        name="search", call_id="tool_1", success=True, result="found"
                    ),
                ),
            ],
            config,
        )

    assert response.content == "done"
    tool_use = captured[0]["messages"][1]["content"][0]
    assert tool_use["input"] == arguments
    assert tool_use["type"] == "tool_use"
    assert tool_use["id"] == "tool_1"
    assert captured[0]["messages"][2]["content"][0]["tool_use_id"] == "tool_1"
