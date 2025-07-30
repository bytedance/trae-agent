# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
This test file is used to test the Ollama client. This test program is expected to verify basic functionalities and check if the results match the expected output.

Currently, we only test init, chat, and set chat history.

WARNING: This Ollama test should not be used in the GitHub Actions workflow, as using Ollama for testing consumes too much time due to installation.
"""

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.ollama_client import OllamaClient

TEST_MODEL = "qwen3:4b"


@unittest.skipIf(
    os.getenv("SKIP_OLLAMA_TEST", "").lower() == "true",
    "Ollama tests skipped due to SKIP_OLLAMA_TEST environment variable",
)
class TestOllamaClient(unittest.TestCase):
    def test_OllamaClient_init(self):
        """
        Test ollama client provides a test case for initialize the ollama client
        It should not be used to check any configiguration based on BaseLLMClient instead we should just check the parameters
        that will change during the init process.
        """
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="ollama",
                api_key="ollama",
                base_url="http://localhost:11434/v1",
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        ollama_client = OllamaClient(model_config)
        self.assertEqual(ollama_client.api_key, "ollama")
        self.assertEqual(ollama_client.base_url, "http://localhost:11434/v1")

    def test_ollama_set_chat_history(self):
        """
        There is nothing we have to assert for this test case just see if it can run
        """
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="ollama",
                api_key="ollama",
                base_url="http://localhost:11434/v1",
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        ollama_client = OllamaClient(model_config)
        message = LLMMessage("user", "this is a test message")
        ollama_client.set_chat_history(messages=[message])
        self.assertTrue(True)  # runnable

    def test_ollama_chat(self):
        """
        There is nothing we have to assert for this test case just see if it can run
        """
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="ollama",
                api_key="ollama",
                base_url="http://localhost:11434/v1",
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        ollama_client = OllamaClient(model_config)
        message = LLMMessage("user", "this is a test message")
        ollama_client.chat(messages=[message], model_config=model_config)
        self.assertTrue(True)  # runnable

    def test_supports_tool_calling(self):
        """
        A test case to check the support tool calling function
        """
        model_config = ModelConfig(
            TEST_MODEL,
            model_provider=ModelProvider(
                provider="ollama",
                api_key="ollama",
                base_url="http://localhost:11434/v1",
                api_version=None,
            ),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        ollama_client = OllamaClient(model_config)
        self.assertEqual(ollama_client.supports_tool_calling(model_config), True)
        model_config.model = "no such model"
        self.assertEqual(ollama_client.supports_tool_calling(model_config), False)


if __name__ == "__main__":
    unittest.main()
