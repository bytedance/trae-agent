# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
This file provides basic testing with the Fireworks AI client. The purpose of the test is to check
that initialization, chat history handling, and tool-calling detection run properly.

WARNING: This test should not be used in the GitHub Actions workflow because it requires an API
key to make real requests.
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.fireworks_client import FireworksClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

TEST_MODEL = "accounts/fireworks/models/llama-v3p3-70b-instruct"


@unittest.skipIf(
    os.getenv("SKIP_FIREWORKS_TEST", "").lower() == "true",
    "Fireworks tests skipped due to SKIP_FIREWORKS_TEST environment variable",
)
class TestFireworksClient(unittest.TestCase):
    def test_FireworksClient_init(self):
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="fireworks",
                api_key=os.getenv("FIREWORKS_API_KEY", ""),
                base_url=None,
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        fireworks_client = FireworksClient(model_config)
        self.assertEqual(
            fireworks_client.base_url, "https://api.fireworks.ai/inference/v1"
        )

    def test_set_chat_history(self):
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="fireworks",
                api_key=os.getenv("FIREWORKS_API_KEY", ""),
                base_url=None,
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        fireworks_client = FireworksClient(model_config)
        message = LLMMessage("user", "this is a test message")
        fireworks_client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                provider="fireworks",
                api_key=os.getenv("FIREWORKS_API_KEY", ""),
                base_url=None,
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.7,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        fireworks_client = FireworksClient(model_config)
        self.assertEqual(fireworks_client.supports_tool_calling(model_config), True)
        model_config.model = "no such model"
        self.assertEqual(fireworks_client.supports_tool_calling(model_config), False)


if __name__ == "__main__":
    unittest.main()
