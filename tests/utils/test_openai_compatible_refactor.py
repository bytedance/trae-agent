# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for OpenAI-compatible client refactoring."""

import unittest
from unittest.mock import Mock

from trae_agent.utils.azure_client import AzureClient
from trae_agent.utils.config import ModelParameters
from trae_agent.utils.doubao_client import DoubaoClient
from trae_agent.utils.openai_compatible import create_openai_compatible_client
from trae_agent.utils.openai_compatible.base import OpenAICompatibleClient
from trae_agent.utils.openrouter_client import OpenRouterClient


class TestOpenAICompatibleRefactor(unittest.TestCase):
    """Test the OpenAI-compatible client refactoring."""

    def setUp(self):
        """Set up test fixtures."""
        self.model_parameters = ModelParameters(
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

    def test_factory_returns_openai_compatible_client(self):
        """Test that factory returns OpenAI compatible client."""
        # Mock the OpenAI client creation to avoid API key requirement
        with unittest.mock.patch(
            "trae_agent.utils.openai_compatible.providers.openrouter.openai.OpenAI"
        ) as mock_openai:
            mock_openai.return_value = Mock()

            client = create_openai_compatible_client("openrouter", self.model_parameters)
            self.assertIsInstance(client, OpenAICompatibleClient)

    def test_openrouter_client_factory(self):
        """Test OpenRouter client factory function."""
        with unittest.mock.patch(
            "trae_agent.utils.openai_compatible.providers.openrouter.openai.OpenAI"
        ) as mock_openai:
            mock_openai.return_value = Mock()

            client = OpenRouterClient(self.model_parameters)
            self.assertIsInstance(client, OpenAICompatibleClient)

    def test_azure_client_factory(self):
        """Test Azure client factory function."""
        with unittest.mock.patch(
            "trae_agent.utils.openai_compatible.providers.azure.openai.AzureOpenAI"
        ) as mock_azure:
            mock_azure.return_value = Mock()

            client = AzureClient(self.model_parameters)
            self.assertIsInstance(client, OpenAICompatibleClient)

    def test_doubao_client_factory(self):
        """Test Doubao client factory function."""
        with unittest.mock.patch(
            "trae_agent.utils.openai_compatible.providers.doubao.openai.OpenAI"
        ) as mock_openai:
            mock_openai.return_value = Mock()

            client = DoubaoClient(self.model_parameters)
            self.assertIsInstance(client, OpenAICompatibleClient)

    def test_invalid_provider(self):
        """Test invalid provider raises ValueError."""
        with self.assertRaises(ValueError):
            create_openai_compatible_client("invalid_provider", self.model_parameters)

    def test_client_has_required_methods(self):
        """Test that clients have all required methods."""
        with unittest.mock.patch(
            "trae_agent.utils.openai_compatible.providers.openrouter.openai.OpenAI"
        ) as mock_openai:
            mock_openai.return_value = Mock()

            client = OpenRouterClient(self.model_parameters)

            # Check that all required methods exist
            self.assertTrue(hasattr(client, "chat"))
            self.assertTrue(hasattr(client, "set_chat_history"))
            self.assertTrue(hasattr(client, "supports_tool_calling"))
            self.assertTrue(hasattr(client, "set_trajectory_recorder"))


if __name__ == "__main__":
    unittest.main()
