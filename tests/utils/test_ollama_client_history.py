"""Verify the Ollama client persists assistant turns in message_history.

These tests guard against the regression fixed in #427: the client must record
the assistant's own response in the Ollama-native message shape so that
subsequent turns can be sent back to ollama.chat successfully.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.ollama_client import OllamaClient


def _config() -> ModelConfig:
    return ModelConfig(
        "qwen3:4b",
        model_provider=ModelProvider(
            provider="ollama",
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            api_version=None,
        ),
        max_tokens=1000,
        temperature=0.8,
        top_p=7.0,
        top_k=8,
        parallel_tool_calls=False,
        max_retries=1,
    )


@pytest.mark.asyncio
async def test_chat_persists_tool_call_in_ollama_native_shape() -> None:
    """Tool-call turns must be persisted as `{role, content, tool_calls}`."""
    client = OllamaClient(_config())
    tool_function = SimpleNamespace(name="bash", arguments={"command": "ls"})
    message = SimpleNamespace(content="", tool_calls=[SimpleNamespace(function=tool_function)])

    with patch("trae_agent.utils.llm_clients.ollama_client.ollama_chat") as mock_chat:
        mock_chat.return_value = SimpleNamespace(message=message)
        client.chat(
            messages=[LLMMessage("user", "list the files")],
            model_config=_config(),
        )

    appended = client.message_history[-1]
    assert appended["role"] == "assistant"
    assert appended["content"] == ""
    assert appended["tool_calls"] == [
        {"function": {"name": "bash", "arguments": {"command": "ls"}}}
    ]


@pytest.mark.asyncio
async def test_chat_persists_text_response_in_message_history() -> None:
    """Text-only assistant turns must be persisted with `role` and `content`."""
    client = OllamaClient(_config())
    message = SimpleNamespace(content="Here is the answer.", tool_calls=None)

    with patch("trae_agent.utils.llm_clients.ollama_client.ollama_chat") as mock_chat:
        mock_chat.return_value = SimpleNamespace(message=message)
        client.chat(
            messages=[LLMMessage("user", "hello")],
            model_config=_config(),
        )

    appended = client.message_history[-1]
    assert appended == {"role": "assistant", "content": "Here is the answer."}


@pytest.mark.asyncio
async def test_chat_does_not_append_openai_function_call_records() -> None:
    """Regression guard: OpenAI function_call items break ollama.chat."""
    client = OllamaClient(_config())
    message = SimpleNamespace(
        content="",
        tool_calls=[SimpleNamespace(function=SimpleNamespace(name="bash", arguments={}))],
    )

    with patch("trae_agent.utils.llm_clients.ollama_client.ollama_chat") as mock_chat:
        mock_chat.return_value = SimpleNamespace(message=message)
        client.chat(
            messages=[LLMMessage("user", "run it")],
            model_config=_config(),
        )

    for record in client.message_history:
        assert "type" not in record, f"Unexpected typed record: {record!r}"
