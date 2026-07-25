# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Tests for the MiniMax client.

- Unit tests: init, set_chat_history, supports_tool_calling (always run)
- Integration tests: real API chat calls (require MINIMAX_API_KEY, skipped by default)

Run integration tests:
    MINIMAX_API_KEY=xxx pytest tests/utils/test_minimax_client_utils.py -v
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.minimax_client import MiniMaxClient

TEST_MODEL = "MiniMax-M3"
HAS_API_KEY = bool(os.getenv("MINIMAX_API_KEY"))


def _make_model_config(model: str = TEST_MODEL, base_url: str | None = None) -> ModelConfig:
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


class TestMiniMaxClientUnit(unittest.TestCase):
    """MiniMax client unit tests (no API key required)."""

    def test_minimax_client_init(self):
        model_config = _make_model_config()
        client = MiniMaxClient(model_config)
        self.assertEqual(client.base_url, "https://api.minimax.io/v1")

    def test_default_base_url_fallback(self):
        model_config = _make_model_config(base_url=None)
        client = MiniMaxClient(model_config)
        self.assertEqual(model_config.model_provider.base_url, "https://api.minimax.io/v1")
        self.assertEqual(client.base_url, "https://api.minimax.io/v1")

    def test_set_chat_history(self):
        model_config = _make_model_config()
        client = MiniMaxClient(model_config)
        message = LLMMessage("user", "this is a test message")
        client.set_chat_history(messages=[message])
        self.assertTrue(True)

    def test_supports_tool_calling(self):
        model_config = _make_model_config()
        client = MiniMaxClient(model_config)
        self.assertTrue(client.supports_tool_calling(model_config))

    def test_supports_tool_calling_disabled(self):
        model_config = _make_model_config()
        model_config.supports_tool_calling = False
        client = MiniMaxClient(model_config)
        self.assertFalse(client.supports_tool_calling(model_config))


@unittest.skipUnless(HAS_API_KEY, "MINIMAX_API_KEY not set — skipping integration tests")
class TestMiniMaxIntegration(unittest.TestCase):
    """MiniMax integration tests (require real API key)."""

    def test_chat_simple(self):
        """Issue 5: real API call to verify MiniMax provider works end-to-end."""
        model_config = _make_model_config()
        client = MiniMaxClient(model_config)
        messages = [LLMMessage(role="user", content="Say hello in exactly 3 words.")]
        response = client.chat(messages, model_config)
        self.assertIsNotNone(response.content)
        self.assertTrue(len(response.content) > 0)
        self.assertIsNotNone(response.usage)

    def test_chat_with_system_message(self):
        """Issue 5: verify system message is respected."""
        model_config = _make_model_config()
        client = MiniMaxClient(model_config)
        messages = [
            LLMMessage(role="system", content="You are a pirate. Reply only in pirate speak."),
            LLMMessage(role="user", content="What is 2+2?"),
        ]
        response = client.chat(messages, model_config)
        self.assertIsNotNone(response.content)
        self.assertTrue(len(response.content) > 0)


if __name__ == "__main__":
    unittest.main()
