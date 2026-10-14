"""Doubao must default to the Ark endpoint when base_url is unset."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.doubao_client import DoubaoClient


def _config(base_url: str | None) -> ModelConfig:
    return ModelConfig(
        "doubao-seed-1.6",
        model_provider=ModelProvider(
            provider="doubao",
            api_key="test-key",
            base_url=base_url,
            api_version=None,
        ),
        max_tokens=128,
        temperature=0.0,
        top_p=1.0,
        top_k=1,
        parallel_tool_calls=False,
        max_retries=1,
    )


@patch("trae_agent.utils.llm_clients.doubao_client.openai.OpenAI")
def test_doubao_defaults_base_url_when_none(mock_openai: MagicMock) -> None:
    mock_openai.return_value = MagicMock()
    client = DoubaoClient(_config(None))
    assert client.base_url == DoubaoClient.DEFAULT_BASE_URL
    mock_openai.assert_called_once()
    assert mock_openai.call_args.kwargs["base_url"] == DoubaoClient.DEFAULT_BASE_URL
    assert mock_openai.call_args.kwargs["api_key"] == "test-key"


@patch("trae_agent.utils.llm_clients.doubao_client.openai.OpenAI")
def test_doubao_defaults_base_url_when_empty(mock_openai: MagicMock) -> None:
    mock_openai.return_value = MagicMock()
    client = DoubaoClient(_config(""))
    assert client.base_url == DoubaoClient.DEFAULT_BASE_URL
    assert mock_openai.call_args.kwargs["base_url"] == DoubaoClient.DEFAULT_BASE_URL


@patch("trae_agent.utils.llm_clients.doubao_client.openai.OpenAI")
def test_doubao_keeps_explicit_base_url(mock_openai: MagicMock) -> None:
    mock_openai.return_value = MagicMock()
    custom = "https://example.volces.com/api/v3/"
    client = DoubaoClient(_config(custom))
    assert client.base_url == custom
    assert mock_openai.call_args.kwargs["base_url"] == custom
