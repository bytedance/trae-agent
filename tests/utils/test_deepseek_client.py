# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the DeepSeek client.

Verifies initialization, provider configuration, message handling,
and tool-calling support.  Chat integration tests that require a live
API key are skipped by default (set SKIP_DEEPSEEK_TEST=true).
"""

import os
import unittest
from unittest.mock import patch

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.deepseek_client import DeepSeekClient, DeepSeekProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


class TestDeepSeekProvider(unittest.TestCase):
    """Unit tests for the DeepSeekProvider configuration."""

    def setUp(self) -> None:
        self.provider = DeepSeekProvider()

    def test_service_name(self) -> None:
        """Service name should identify DeepSeek for retry logging."""
        self.assertEqual(self.provider.get_service_name(), "DeepSeek")

    def test_provider_name(self) -> None:
        """Provider name should match the trajectory-recording identifier."""
        self.assertEqual(self.provider.get_provider_name(), "deepseek")

    def test_extra_headers_is_empty(self) -> None:
        """DeepSeek does not require extra HTTP headers."""
        self.assertEqual(self.provider.get_extra_headers(), {})

    def test_supports_tool_calling(self) -> None:
        """All DeepSeek chat models should advertise tool-calling support."""
        self.assertTrue(self.provider.supports_tool_calling("deepseek-chat"))
        self.assertTrue(self.provider.supports_tool_calling("deepseek-reasoner"))
        self.assertTrue(self.provider.supports_tool_calling("unknown-model"))


class TestDeepSeekClientInit(unittest.TestCase):
    """Tests for DeepSeekClient instantiation and basic properties."""

    @staticmethod
    def _model_config(**overrides: object) -> ModelConfig:
        """Build a minimal ModelConfig for DeepSeek testing."""
        defaults: dict[str, object] = {
            "model": "deepseek-chat",
            "model_provider": ModelProvider(
                provider="deepseek",
                api_key="test-api-key",
                base_url="https://api.deepseek.com/v1",
                api_version=None,
            ),
            "max_tokens": 4096,
            "temperature": 0.5,
            "top_p": 1.0,
            "top_k": 0,
            "parallel_tool_calls": False,
            "max_retries": 3,
        }
        defaults.update(overrides)
        return ModelConfig(**defaults)  # type: ignore[arg-type]

    def test_init_stores_api_key(self) -> None:
        """API key from config should be propagated to the client."""
        client = DeepSeekClient(self._model_config())
        self.assertEqual(client.api_key, "test-api-key")

    def test_init_stores_base_url(self) -> None:
        """Base URL from config should be propagated to the client."""
        client = DeepSeekClient(self._model_config())
        self.assertEqual(client.base_url, "https://api.deepseek.com/v1")

    def test_init_without_base_url(self) -> None:
        """When no base_url is provided the OpenAI SDK will use its default."""
        client = DeepSeekClient(
            self._model_config(
                model_provider=ModelProvider(
                    provider="deepseek",
                    api_key="test-key",
                    base_url=None,
                    api_version=None,
                )
            )
        )
        self.assertIsNone(client.base_url)

    def test_set_chat_history(self) -> None:
        """set_chat_history should parse and store messages without error."""
        client = DeepSeekClient(self._model_config())
        message = LLMMessage(role="user", content="Hello, DeepSeek!")
        client.set_chat_history(messages=[message])
        self.assertTrue(True)  # Runnable — no exception raised.

    @patch("trae_agent.utils.llm_clients.openai_compatible_base.openai.OpenAI")
    def test_chat_mock(self, mock_openai_class: object) -> None:
        """chat() should construct a valid request (mocked API call)."""
        mock_client = mock_openai_class.return_value

        # Build a minimal ChatCompletion response.
        mock_choice = unittest.mock.MagicMock()
        mock_choice.message.content = "Hello from DeepSeek"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_choice.index = 0

        mock_response = unittest.mock.MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "deepseek-chat"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5

        mock_client.chat.completions.create.return_value = mock_response

        client = DeepSeekClient(self._model_config(max_retries=1))
        # Override the auto-created OpenAI client with our mock.
        client.client = mock_client

        message = LLMMessage(role="user", content="Hi")
        result = client.chat(
            messages=[message],
            model_config=self._model_config(max_retries=1),
            tools=None,
            reuse_history=False,
        )

        self.assertEqual(result.content, "Hello from DeepSeek")
        self.assertIsNone(result.tool_calls)
        self.assertEqual(result.model, "deepseek-chat")

    def test_supports_tool_calling(self) -> None:
        """The DeepSeekClient should delegate to DeepSeekProvider."""
        client = DeepSeekClient(self._model_config())
        self.assertTrue(client.supports_tool_calling(self._model_config()))


class TestDeepSeekConfigIntegration(unittest.TestCase):
    """Verify that the DeepSeek provider is registered in LLMClient."""

    def test_llm_client_creates_deepseek(self) -> None:
        """LLMClient should instantiate DeepSeekClient for provider='deepseek'."""
        from trae_agent.utils.llm_clients.llm_client import LLMClient

        model_config = ModelConfig(
            model="deepseek-chat",
            model_provider=ModelProvider(
                provider="deepseek",
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
                api_version=None,
            ),
            max_tokens=4096,
            temperature=0.5,
            top_p=1.0,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=3,
        )
        llm_client = LLMClient(model_config)
        self.assertIsInstance(llm_client.client, DeepSeekClient)
        self.assertEqual(llm_client.provider.value, "deepseek")

    def test_resolve_api_key_from_env(self) -> None:
        """Config should fall back to DEEPSEEK_API_KEY when api_key is empty."""
        with unittest.mock.patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "env-key-123"}, clear=False
        ):
            from trae_agent.utils.config import Config

            yaml_config = """
agents:
    trae_agent:
        enable_lakeview: false
        model: ds
        max_steps: 3
        tools: [bash, task_done]
model_providers:
    ds_provider:
        api_key: ""
        provider: deepseek
        base_url: https://api.deepseek.com/v1
models:
    ds:
        model_provider: ds_provider
        model: deepseek-chat
        max_tokens: 4096
        temperature: 0.5
        top_p: 1
        top_k: 0
        max_retries: 3
        parallel_tool_calls: false
"""
            config = Config.create(config_string=yaml_config)
            config.resolve_config_values()
            self.assertEqual(
                config.trae_agent.model.model_provider.api_key, "env-key-123"
            )


if __name__ == "__main__":
    unittest.main()
