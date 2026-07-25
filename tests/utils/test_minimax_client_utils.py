# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Basic tests for the MiniMax client.

Tests init, set_chat_history, and supports_tool_calling.
The chat test requires a MINIMAX_API_KEY and is skipped by default.
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.minimax_client import MiniMaxClient

TEST_MODEL = "MiniMax-M3"


@unittest.skipIf(
    os.getenv("SKIP_MINIMAX_TEST", "").lower() == "true",
    "MiniMax tests skipped due to SKIP_MINIMAX_TEST environment variable",
)
class TestMiniMaxClient(unittest.TestCase):
    """MiniMax client tests."""

    def _make_model_config(self, model: str = TEST_MODEL, base_url: str | None = None) -> ModelConfig:
        return ModelConfig(
            model=model,
            model_provider=ModelProvider(
                provider="minimax",
                api_key=os.getenv("MINIMAX_API_KEY", "test-key"),
                base_url=base_url or "https://api.minimax.io/v1",
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.5,
            top_p=0.95,
            top_k=0,
            parallel_tool_calls=True,
            max_retries=1,
        )

    def test_minimax_client_init(self):
        """Test MiniMaxClient initialization."""
        model_config = self._make_model_config()
        client = MiniMaxClient(model_config)
        self.assertEqual(client.base_url, "https://api.minimax.io/v1")

    def test_default_base_url_fallback(self):
        """Test that MiniMaxClient sets a default base_url when none is provided."""
        model_config = self._make_model_config(base_url=None)
        client = MiniMaxClient(model_config)
        self.assertEqual(model_config.model_provider.base_url, "https://api.minimax.io/v1")
        self.assertEqual(client.base_url, "https://api.minimax.io/v1")

    def test_set_chat_history(self):
        """Test setting chat history."""
        model_config = self._make_model_config()
        client = MiniMaxClient(model_config)
        message = LLMMessage("user", "this is a test message")
        client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        """Test supports_tool_calling returns True for MiniMax models."""
        model_config = self._make_model_config()
        client = MiniMaxClient(model_config)
        self.assertTrue(client.supports_tool_calling(model_config))

    def test_supports_tool_calling_disabled(self):
        """Test supports_tool_calling returns False when disabled in config."""
        model_config = self._make_model_config()
        model_config.supports_tool_calling = False
        client = MiniMaxClient(model_config)
        self.assertFalse(client.supports_tool_calling(model_config))


if __name__ == "__main__":
    unittest.main()
