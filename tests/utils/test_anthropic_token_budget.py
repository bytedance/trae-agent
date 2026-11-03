"""Exercise Anthropic request construction without a live provider."""

import json

import anthropic
import httpx
import pytest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.anthropic_client import AnthropicClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


@pytest.mark.parametrize(
    ("max_tokens", "max_completion_tokens", "expected"),
    [(None, None, 4096), (123, None, 123), (123, 234, 123), (None, 234, 4096), (0, None, 0)],
)
def test_anthropic_receives_a_concrete_token_budget(max_tokens, max_completion_tokens, expected):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if not isinstance(body.get("max_tokens"), int):
            return httpx.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "max_tokens must be an integer",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    config = ModelConfig(
        model="test",
        model_provider=ModelProvider(api_key="test", provider="anthropic"),
        temperature=0.1,
        top_p=0.9,
        top_k=1,
        parallel_tool_calls=False,
        max_retries=1,
        max_tokens=max_tokens,
        max_completion_tokens=max_completion_tokens,
    )
    client = AnthropicClient(config)
    client.client = anthropic.Anthropic(
        api_key="test",
        base_url="https://example.test",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    )
    try:
        response = client.chat([LLMMessage(role="user", content="hi")], config)
        assert response.content == "ok"
        assert len(requests) == 1
        assert requests[0]["max_tokens"] == expected
    finally:
        client.client.close()


@pytest.mark.parametrize("stop_sequences", [None, [], ["END", "<stop>"]])
def test_anthropic_forwards_optional_stop_sequences(stop_sequences):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    config = ModelConfig(
        model="test",
        model_provider=ModelProvider(api_key="test", provider="anthropic"),
        temperature=0.1,
        top_p=0.9,
        top_k=1,
        parallel_tool_calls=False,
        max_retries=1,
        max_tokens=100,
        stop_sequences=stop_sequences,
    )
    client = AnthropicClient(config)
    client.client = anthropic.Anthropic(
        api_key="test",
        base_url="https://example.test",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    )
    try:
        client.chat([LLMMessage(role="user", content="hi")], config)
        if not stop_sequences:
            assert "stop_sequences" not in requests[0]
        else:
            assert requests[0]["stop_sequences"] == stop_sequences
    finally:
        client.client.close()
