# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import httpx
import openai
import pytest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMUsage
from trae_agent.utils.llm_clients.openai_client import OpenAIClient


@pytest.mark.parametrize(
    ("details", "cached_tokens", "reasoning_tokens"),
    [
        ({"output_tokens_details": {"reasoning_tokens": 3}}, 0, 3),
        ({"input_tokens_details": {"cached_tokens": 4}}, 4, 0),
        ({"input_tokens_details": None, "output_tokens_details": None}, 0, 0),
        (
            {
                "input_tokens_details": {"cached_tokens": 4},
                "output_tokens_details": {"reasoning_tokens": 3},
            },
            4,
            3,
        ),
    ],
)
def test_responses_usage_details_are_optional(
    details: dict[str, dict[str, int] | None], cached_tokens: int, reasoning_tokens: int
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "model": "gpt-4.1",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "Hello", "annotations": []}],
                    },
                ],
                "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17, **details},
            },
        )

    provider = ModelProvider(
        provider="openai", api_key="test-key", base_url="https://example.invalid/v1"
    )
    config = ModelConfig(
        model="gpt-4.1",
        model_provider=provider,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=0,
    )
    client = OpenAIClient(config)
    with (
        client.client,
        openai.OpenAI(
            api_key=provider.api_key,
            base_url=provider.base_url,
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        ) as sdk,
    ):
        client.client = sdk
        response = client.chat([LLMMessage(role="user", content="Say hello.")], config)

    assert response.content == "Hello"
    assert response.usage == LLMUsage(
        input_tokens=12,
        output_tokens=5,
        cache_read_input_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )
