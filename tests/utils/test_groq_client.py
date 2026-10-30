# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
This file provides basic testing with the Groq client. The purpose of the test is to check that
initialization, chat history handling, chat, and tool-calling detection run properly.

WARNING: This Groq test should not be used in the GitHub Actions workflow because it requires an
API key to make real requests.
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.groq_client import GroqClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

TEST_MODEL = "llama-3.3-70b-versatile"


@unittest.skipIf(
    os.getenv("SKIP_GROQ_TEST", "").lower() == "true",
    "Groq tests skipped due to SKIP_GROQ_TEST environment variable",
)
class TestGroqClient(unittest.TestCase):
    def test_GroqClient_init(self):
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="groq",
                api_key=os.getenv("GROQ_API_KEY", ""),
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
        groq_client = GroqClient(model_config)
        self.assertEqual(groq_client.base_url, "https://api.groq.com/openai/v1")

    def test_set_chat_history(self):
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="groq",
                api_key=os.getenv("GROQ_API_KEY", ""),
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
        groq_client = GroqClient(model_config)
        message = LLMMessage("user", "this is a test message")
        groq_client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(
                provider="groq",
                api_key=os.getenv("GROQ_API_KEY", ""),
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
        groq_client = GroqClient(model_config)
        self.assertEqual(groq_client.supports_tool_calling(model_config), True)
        model_config.model = "no such model"
        self.assertEqual(groq_client.supports_tool_calling(model_config), False)


if __name__ == "__main__":
    unittest.main()
