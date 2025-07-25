# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for OpenAI-compatible client refactoring."""

import unittest
from unittest.mock import Mock, patch

from trae_agent.utils.azure_client import AzureClient
from trae_agent.utils.config import ModelParameters
from trae_agent.utils.doubao_client import DoubaoClient
from trae_agent.utils.models.openai_compatible_base import OpenAICompatibleClient
from trae_agent.utils.models.openai_compatible_factory import create_openai_compatible_client
from trae_agent.utils.openrouter_client import OpenRouterClient


class TestOpenAICompatibleFactory(unittest.TestCase):
    """Test suite for OpenAI-compatible client refactoring."""

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

    @patch("trae_agent.utils.models.openrouter.openai.OpenAI")
    def test_factory_returns_openai_compatible_client(self, mock_openai):
        """Test that factory returns OpenAI compatible client."""
        mock_openai.return_value = Mock()

        client = create_openai_compatible_client("openrouter", self.model_parameters)
        self.assertIsInstance(client, OpenAICompatibleClient)

    @patch("trae_agent.utils.models.openrouter.openai.OpenAI")
    def test_openrouter_client_factory(self, mock_openai):
        """Test OpenRouter client factory function."""
        mock_openai.return_value = Mock()

        client = OpenRouterClient(self.model_parameters)
        self.assertIsInstance(client, OpenAICompatibleClient)

    @patch("trae_agent.utils.models.azure.openai.AzureOpenAI")
    def test_azure_client_factory(self, mock_azure):
        """Test Azure client factory function."""
        mock_azure.return_value = Mock()

        client = AzureClient(self.model_parameters)
        self.assertIsInstance(client, OpenAICompatibleClient)

    @patch("trae_agent.utils.models.doubao.openai.OpenAI")
    def test_doubao_client_factory(self, mock_openai):
        """Test Doubao client factory function."""
        mock_openai.return_value = Mock()

        client = DoubaoClient(self.model_parameters)
        self.assertIsInstance(client, OpenAICompatibleClient)

    def test_invalid_provider(self):
        """Test invalid provider raises ValueError."""
        with self.assertRaises(ValueError):
            create_openai_compatible_client("invalid_provider", self.model_parameters)

    @patch("trae_agent.utils.models.openrouter.openai.OpenAI")
    def test_client_has_required_methods(self, mock_openai):
        """Test that clients have all required methods."""
        mock_openai.return_value = Mock()

        client = OpenRouterClient(self.model_parameters)

        self.assertTrue(hasattr(client, "chat"))
        self.assertTrue(hasattr(client, "set_chat_history"))
        self.assertTrue(hasattr(client, "supports_tool_calling"))
        self.assertTrue(hasattr(client, "set_trajectory_recorder"))


if __name__ == "__main__":
    unittest.main()
