# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for OpenAI-compatible client refactoring."""

import pytest

from trae_agent.utils.azure_client import AzureClient
from trae_agent.utils.config import ModelParameters
from trae_agent.utils.doubao_client import DoubaoClient
from trae_agent.utils.models.openai_compatible_base import OpenAICompatibleClient
from trae_agent.utils.models.openai_compatible_factory import create_openai_compatible_client
from trae_agent.utils.openrouter_client import OpenRouterClient


@pytest.fixture
def model_parameters():
    """Test fixture for model parameters."""
    return ModelParameters(
        model="test-model",
        api_key="test-key",
        max_tokens=1000,
        temperature=0.8,
        top_p=1.0,
        top_k=8,
        parallel_tool_calls=False,
        max_retries=3,
        base_url="https://test.api.com",
        api_version=None,
    )


def test_factory_returns_openai_compatible_client(model_parameters, mocker):
    """Test that factory returns OpenAI compatible client."""
    mock_openai = mocker.patch("trae_agent.utils.models.openrouter.openai.OpenAI")
    mock_openai.return_value = mocker.Mock()

    client = create_openai_compatible_client("openrouter", model_parameters)
    assert isinstance(client, OpenAICompatibleClient)


def test_openrouter_client_factory(model_parameters, mocker):
    """Test OpenRouter client factory function."""
    mock_openai = mocker.patch("trae_agent.utils.models.openrouter.openai.OpenAI")
    mock_openai.return_value = mocker.Mock()

    client = OpenRouterClient(model_parameters)
    assert isinstance(client, OpenAICompatibleClient)


def test_azure_client_factory(model_parameters, mocker):
    """Test Azure client factory function."""
    mock_azure = mocker.patch("trae_agent.utils.models.azure.openai.AzureOpenAI")
    mock_azure.return_value = mocker.Mock()

    client = AzureClient(model_parameters)
    assert isinstance(client, OpenAICompatibleClient)


def test_doubao_client_factory(model_parameters, mocker):
    """Test Doubao client factory function."""
    mock_openai = mocker.patch("trae_agent.utils.models.doubao.openai.OpenAI")
    mock_openai.return_value = mocker.Mock()

    client = DoubaoClient(model_parameters)
    assert isinstance(client, OpenAICompatibleClient)


def test_invalid_provider(model_parameters):
    """Test invalid provider raises ValueError."""
    with pytest.raises(ValueError):
        create_openai_compatible_client("invalid_provider", model_parameters)


def test_client_has_required_methods(model_parameters, mocker):
    """Test that clients have all required methods."""
    mock_openai = mocker.patch("trae_agent.utils.models.openrouter.openai.OpenAI")
    mock_openai.return_value = mocker.Mock()

    client = OpenRouterClient(model_parameters)

    assert hasattr(client, "chat")
    assert hasattr(client, "set_chat_history")
    assert hasattr(client, "supports_tool_calling")
    assert hasattr(client, "set_trajectory_recorder")
