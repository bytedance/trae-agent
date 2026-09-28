# SPDX-License-Identifier: MIT

import json

import httpx
import openai
import pytest

from trae_agent.tools.task_done_tool import TaskDoneTool
from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.llm_client import LLMClient, LLMProvider
from trae_agent.utils.llm_clients.tsubasa_client import TsubasaClient


@pytest.mark.parametrize("model", ["tsubasa-fast", "tsubasa-pro"])
@pytest.mark.parametrize("base_url", [None, "https://custom.example/v1"])
def test_tsubasa_chat_transport(monkeypatch, model, base_url):
    monkeypatch.setenv("TSUBASA_API_KEY", "fixture-tsubasa-key")
    monkeypatch.delenv("TSUBASA_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.example/v1")
    config = ModelConfig(
        model=model,
        model_provider=ModelProvider(provider="tsubasa", api_key="", base_url=base_url),
        max_tokens=512,
        temperature=0,
        top_p=1,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=1,
    )
    config.resolve_config_values()
    requests = []

    def respond(request):
        assert str(request.url) == (base_url or "https://api.tsubasa.sh/v1") + "/chat/completions"
        assert request.headers["authorization"] == "Bearer fixture-tsubasa-key"
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == model
        assert body["max_tokens"] == 512
        assert body["top_p"] == 1
        assert body["tools"][0]["function"]["name"] == "task_done"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fixture",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_fixture",
                                    "type": "function",
                                    "function": {"name": "task_done", "arguments": "{}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            },
        )

    original = openai.OpenAI
    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: original(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))
        ),
    )
    client = LLMClient(config)
    assert client.provider is LLMProvider.TSUBASA
    assert isinstance(client.client, TsubasaClient)
    result = client.chat(
        [LLMMessage(role="user", content="Finish the fixture.")], config, [TaskDoneTool()]
    )
    assert len(requests) == 1
    assert result.tool_calls[0].name == "task_done"
    assert result.tool_calls[0].arguments == {}
    assert result.usage.input_tokens == 20
    assert client.client.message_history[-1]["tool_calls"][0]["id"] == "call_fixture"
