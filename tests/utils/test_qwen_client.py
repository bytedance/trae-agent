# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Unit tests for the QwenClient.

WARNING: These tests should not be run in a GitHub Actions workflow
because they require an API key.
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.qwen_client import QwenClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

TEST_MODEL = "qwen-plus"


@unittest.skipIf(
    os.getenv("SKIP_QWEN_TEST", "").lower() == "true",
    "Qwen tests skipped due to SKIP_QWEN_TEST environment variable",
)
class TestQwenClient(unittest.TestCase):
    def test_qwen_client_init(self):
        """Test the initialization of the QwenClient."""
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("QWEN_API_KEY", "test-api-key"),
                provider="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        qwen_client = QwenClient(model_config)
        self.assertEqual(qwen_client.base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertIsNotNone(qwen_client.client)

    def test_set_chat_history(self):
        """Test setting chat history."""
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("QWEN_API_KEY", "test-api-key"),
                provider="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        qwen_client = QwenClient(model_config)
        message = LLMMessage("user", "this is a test message")
        qwen_client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_qwen_chat(self):
        """
        Test the chat method with a simple user message.
        There is nothing we have to assert for this test case just see if it can run.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("QWEN_API_KEY", "test-api-key"),
                provider="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        qwen_client = QwenClient(model_config)
        message = LLMMessage("user", "this is a test message")
        qwen_client.chat(messages=[message], model_config=model_config)
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        """
        Test the supports_tool_calling method.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                api_key=os.getenv("QWEN_API_KEY", "test-api-key"),
                provider="qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        qwen_client = QwenClient(model_config)
        self.assertEqual(qwen_client.supports_tool_calling(model_config), True)
        model_config.model = "no such model"
        self.assertEqual(qwen_client.supports_tool_calling(model_config), True)


if __name__ == "__main__":
    unittest.main()