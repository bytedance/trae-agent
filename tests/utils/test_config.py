# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import unittest
from unittest.mock import patch

from trae_agent.utils.anthropic_client import AnthropicClient
from trae_agent.utils.config import Config, ModelParameters
from trae_agent.utils.openai_client import OpenAIClient


class TestConfigBaseURL(unittest.TestCase):
    def test_config_with_base_url_in_config(self):
        test_config = {
            "default_provider": "openai",
            "model_providers": {
                "openai": {
                    "model": "gpt-4o",
                    "api_key": "test-api-key",
                    "base_url": "https://custom-openai.example.com/v1",
                }
            },
        }

        config = Config(test_config)

        self.assertEqual(
            config.model_providers["openai"].base_url,
            "https://custom-openai.example.com/v1",
        )

    def test_config_without_base_url(self):
        test_config = {
            "default_provider": "openai",
            "model_providers": {
                "openai": {
                    "model": "gpt-4o",
                    "api_key": "test-api-key",
                }
            },
        }

        config = Config(test_config)

        self.assertIsNone(config.model_providers["openai"].base_url)

    def test_default_anthropic_base_url(self):
        config = Config({})

        # If there are no model providers, the default provider is anthropic
        # and the default base_url is https://api.anthropic.com
        self.assertEqual(config.model_providers["anthropic"].base_url, "https://api.anthropic.com")

    def test_multiple_providers_with_different_base_urls(self):
        """Test multiple providers each with their own base_url."""
        test_config = {
            "default_provider": "openai",
            "max_steps": 20,
            "model_providers": {
                "openai": {
                    "model": "gpt-4o",
                    "api_key": "openai-key",
                    "base_url": "https://custom-openai.example.com/v1",
                    "max_tokens": 4096,
                    "temperature": 0.5,
                    "top_p": 1,
                    "top_k": 0,
                    "parallel_tool_calls": False,
                    "max_retries": 10,
                },
                "anthropic": {
                    "model": "claude-sonnet-4-20250514",
                    "api_key": "anthropic-key",
                    "base_url": "https://custom-anthropic.example.com",
                    "max_tokens": 4096,
                    "temperature": 0.5,
                    "top_p": 1,
                    "top_k": 0,
                    "parallel_tool_calls": False,
                    "max_retries": 10,
                },
                "openrouter": {
                    "model": "openai/gpt-4o",
                    "api_key": "openrouter-key",
                    "base_url": "https://custom-openrouter.example.com/api/v1",
                    "max_tokens": 4096,
                    "temperature": 0.5,
                    "top_p": 1,
                    "top_k": 0,
                    "parallel_tool_calls": False,
                    "max_retries": 10,
                },
            },
        }

        config = Config(test_config)
        self.assertEqual(
            config.model_providers["openai"].base_url,
            "https://custom-openai.example.com/v1",
        )
        self.assertEqual(
            config.model_providers["anthropic"].base_url,
            "https://custom-anthropic.example.com",
        )
        self.assertEqual(
            config.model_providers["openrouter"].base_url,
            "https://custom-openrouter.example.com/api/v1",
        )

    @patch("trae_agent.utils.openai_client.openai.OpenAI")
    def test_openai_client_with_custom_base_url(self, mock_openai):
        model_params = ModelParameters(
            model="gpt-4o",
            api_key="test-api-key",
            base_url="https://custom-openai.example.com/v1",
            max_tokens=4096,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=10,
        )

        client = OpenAIClient(model_params)

        mock_openai.assert_called_once_with(
            api_key="test-api-key", base_url="https://custom-openai.example.com/v1"
        )
        self.assertEqual(client.base_url, "https://custom-openai.example.com/v1")

    @patch("trae_agent.utils.anthropic_client.anthropic.Anthropic")
    def test_anthropic_client_base_url_attribute_set(self, mock_anthropic):
        model_params = ModelParameters(
            model="claude-sonnet-4-20250514",
            api_key="test-api-key",
            base_url="https://custom-anthropic.example.com",
            max_tokens=4096,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=10,
        )

        client = AnthropicClient(model_params)

        self.assertEqual(client.base_url, "https://custom-anthropic.example.com")

    @patch("trae_agent.utils.anthropic_client.anthropic.Anthropic")
    def test_anthropic_client_with_custom_base_url(self, mock_anthropic):
        model_params = ModelParameters(
            model="claude-sonnet-4-20250514",
            api_key="test-api-key",
            base_url="https://custom-anthropic.example.com",
            max_tokens=4096,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=10,
        )

        client = AnthropicClient(model_params)

        mock_anthropic.assert_called_once_with(
            api_key="test-api-key", base_url="https://custom-anthropic.example.com"
        )
        self.assertEqual(client.base_url, "https://custom-anthropic.example.com")


if __name__ == "__main__":
    unittest.main()
