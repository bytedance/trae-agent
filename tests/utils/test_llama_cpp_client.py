# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
This file provides basic testing with the Llama.cpp client. The purpose of these tests is to ensure that the client can be initialized, handle chat history, and make chat calls properly.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from trae_agent.utils.config import ModelParameters
from trae_agent.utils.llm_basics import LLMMessage
from trae_agent.utils.llama_cpp_client import LlamaCppClient

# It is recommended to use a small, fast model for testing purposes
TEST_MODEL = os.getenv("LLAMA_CPP_TEST_MODEL", "gguf-model-name")


class TestLlamaCppClient(unittest.TestCase):
    """
    Test cases for the Llama.cpp client.
    """

    def setUp(self):
        """Set up the test environment for each test case."""
        self.model_parameters = ModelParameters(
            model=TEST_MODEL,
            api_key="sk-12345",  # Llama.cpp server might not require an API key
            base_url=os.getenv("LLAMA_CPP_BASE_URL", "http://127.0.0.1:8080"),
            max_tokens=1000,
            temperature=0.8,
            top_p=0.9,
            top_k=40,
            parallel_tool_calls=False,
            max_retries=1,
        )
        self.llama_cpp_client = LlamaCppClient(self.model_parameters)

    def test_LlamaCppClient_init(self):
        """Test the initialization of the LlamaCppClient."""
        self.assertEqual(
            self.llama_cpp_client.client.base_url, str(self.model_parameters.base_url)
        )

    def test_set_chat_history(self):
        """Test the set_chat_history method."""
        message = LLMMessage(role="user", content="This is a test message.")
        self.llama_cpp_client.set_chat_history(messages=[message])
        self.assertEqual(len(self.llama_cpp_client.message_history), 1)
        self.assertEqual(
            self.llama_cpp_client.message_history[0]["content"], "This is a test message."
        )

    @patch("openai.OpenAI")
    def test_llama_cpp_chat_mocked(self, mock_openai):
        """
        Test the chat method with a mocked API call to ensure it processes the response correctly.
        """
        # Arrange
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, this is a mocked response."
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = TEST_MODEL
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_client.chat.completions.create.return_value = mock_response

        client = LlamaCppClient(self.model_parameters)
        message = LLMMessage(role="user", content="Hello, this is a test.")

        # Act
        response = client.chat(messages=[message], model_parameters=self.model_parameters)

        # Assert
        self.assertIsNotNone(response)
        self.assertEqual(response.content, "Hello, this is a mocked response.")
        self.assertEqual(response.model, TEST_MODEL)
        self.assertIsNotNone(response.usage)
        self.assertEqual(response.usage.input_tokens, 10)
        self.assertEqual(response.usage.output_tokens, 20)
        mock_client.chat.completions.create.assert_called_once()

    def test_supports_tool_calling(self):
        """
        Test the supports_tool_calling method.
        """
        self.assertTrue(self.llama_cpp_client.supports_tool_calling(self.model_parameters))


if __name__ == "__main__":
    unittest.main()
