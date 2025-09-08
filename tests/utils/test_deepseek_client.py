# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Unit tests for the DeepSeekClient.

WARNING: These tests should not be run in a GitHub Actions workflow
because they require an API key.
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.deepseek_client import DeepSeekClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

TEST_MODEL = "deepseek-chat"


@unittest.skipIf(
    os.getenv("SKIP_DEEPSEEK_TEST", "").lower() == "true",
    "DeepSeek tests skipped due to SKIP_DEEPSEEK_TEST environment variable",
)
class TestDeepSeekClient(unittest.TestCase):
    def test_deepseek_client_init(self):
        """Test the initialization of the DeepSeekClient."""
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("DEEPSEEK_API_KEY", "test-api-key"),
                provider="deepseek",
                base_url="https://api.deepseek.com",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        deepseek_client = DeepSeekClient(model_config)
        self.assertEqual(deepseek_client.base_url, "https://api.deepseek.com")
        self.assertIsNotNone(deepseek_client.client)

    def test_set_chat_history(self):
        """Test setting chat history."""
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("DEEPSEEK_API_KEY", "test-api-key"),
                provider="deepseek",
                base_url="https://api.deepseek.com",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        deepseek_client = DeepSeekClient(model_config)
        message = LLMMessage("user", "this is a test message")
        deepseek_client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_deepseek_chat(self):
        """
        Test the chat method with a simple user message.
        There is nothing we have to assert for this test case just see if it can run.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("DEEPSEEK_API_KEY", "test-api-key"),
                provider="deepseek",
                base_url="https://api.deepseek.com",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        deepseek_client = DeepSeekClient(model_config)
        message = LLMMessage("user", "this is a test message")
        deepseek_client.chat(messages=[message], model_config=model_config)
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        """
        Test the supports_tool_calling method.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("DEEPSEEK_API_KEY", "test-api-key"),
                provider="deepseek",
                base_url="https://api.deepseek.com",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        deepseek_client = DeepSeekClient(model_config)
        self.assertEqual(deepseek_client.supports_tool_calling(model_config), True)
        model_config.model = "no such model"
        self.assertEqual(deepseek_client.supports_tool_calling(model_config), True)


if __name__ == "__main__":
    unittest.main()