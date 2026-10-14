"""Azure requires api_version; None/\"\" must not reach the SDK as a blank version."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.azure_client import AzureClient

AZURE_ENDPOINT = "https://demo.openai.azure.com"
CONFIGURED_VERSION = "2024-03-01-preview"
ENVIRONMENT_VERSION = "2024-05-01-preview"
MANAGED_VARS = ("AZURE_API_VERSION", "OPENAI_API_VERSION")


def _config(
    *,
    base_url: str | None = AZURE_ENDPOINT,
    api_version: str | None = CONFIGURED_VERSION,
) -> ModelConfig:
    return ModelConfig(
        "gpt-4o",
        model_provider=ModelProvider(
            provider="azure",
            api_key="test-key",
            base_url=base_url,
            api_version=api_version,
        ),
        max_tokens=1000,
        temperature=0.8,
        top_p=0.7,
        top_k=8,
        parallel_tool_calls=False,
        max_retries=1,
    )


def _env_without_api_versions(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in MANAGED_VARS}
    env.update(extra)
    return env


@patch("openai.AzureOpenAI")
def test_configured_api_version_reaches_sdk(mock_azure: MagicMock) -> None:
    mock_azure.return_value = MagicMock()
    with patch.dict(os.environ, _env_without_api_versions(), clear=True):
        AzureClient(_config())
    assert mock_azure.call_args.kwargs["api_version"] == CONFIGURED_VERSION


@patch("openai.AzureOpenAI")
def test_azure_api_version_env_is_honoured(mock_azure: MagicMock) -> None:
    mock_azure.return_value = MagicMock()
    with patch.dict(
        os.environ,
        _env_without_api_versions(AZURE_API_VERSION=ENVIRONMENT_VERSION),
        clear=True,
    ):
        AzureClient(_config(api_version=None))
    assert mock_azure.call_args.kwargs["api_version"] == ENVIRONMENT_VERSION


@patch("openai.AzureOpenAI")
def test_openai_api_version_env_still_works(mock_azure: MagicMock) -> None:
    mock_azure.return_value = MagicMock()
    with patch.dict(
        os.environ,
        _env_without_api_versions(OPENAI_API_VERSION=ENVIRONMENT_VERSION),
        clear=True,
    ):
        AzureClient(_config(api_version=None))
    assert mock_azure.call_args.kwargs["api_version"] == ENVIRONMENT_VERSION


@patch("openai.AzureOpenAI")
def test_config_wins_over_environment(mock_azure: MagicMock) -> None:
    mock_azure.return_value = MagicMock()
    with patch.dict(
        os.environ,
        _env_without_api_versions(AZURE_API_VERSION=ENVIRONMENT_VERSION),
        clear=True,
    ):
        AzureClient(_config(api_version=CONFIGURED_VERSION))
    assert mock_azure.call_args.kwargs["api_version"] == CONFIGURED_VERSION


def test_missing_api_version_names_config_field() -> None:
    with (
        patch.dict(os.environ, _env_without_api_versions(), clear=True),
        pytest.raises(ValueError, match="api_version is required for AzureClient") as captured,
    ):
        AzureClient(_config(api_version=None))
    assert "AZURE_API_VERSION" in str(captured.value)


def test_empty_api_version_is_rejected() -> None:
    with (
        patch.dict(os.environ, _env_without_api_versions(), clear=True),
        pytest.raises(ValueError, match="api_version is required for AzureClient"),
    ):
        AzureClient(_config(api_version=""))


def test_empty_api_version_can_fall_back_to_env() -> None:
    """Blank config should not win over AZURE_API_VERSION."""
    with patch("openai.AzureOpenAI") as mock_azure:
        mock_azure.return_value = MagicMock()
        with patch.dict(
            os.environ,
            _env_without_api_versions(AZURE_API_VERSION=ENVIRONMENT_VERSION),
            clear=True,
        ):
            AzureClient(_config(api_version=""))
        assert mock_azure.call_args.kwargs["api_version"] == ENVIRONMENT_VERSION


def test_base_url_still_required() -> None:
    with (
        patch.dict(os.environ, _env_without_api_versions(), clear=True),
        pytest.raises(ValueError, match="base_url is required for AzureClient"),
    ):
        AzureClient(_config(base_url=None))


def test_resolved_client_targets_azure_endpoint() -> None:
    with patch.dict(os.environ, _env_without_api_versions(), clear=True):
        client = AzureClient(_config())
    assert str(client.client.base_url) == f"{AZURE_ENDPOINT}/openai/"
