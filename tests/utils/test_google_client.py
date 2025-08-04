# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Unit tests for the GoogleClient.

WARNING: These tests should not be run in a GitHub Actions workflow
because they require an API key.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.google_client import GoogleClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage

TEST_MODEL = "gemini-2.5-flash"


@unittest.skipIf(
    os.getenv("SKIP_GOOGLE_TEST", "").lower() == "true",
    "Google tests skipped due to SKIP_GOOGLE_TEST environment variable",
)
class TestGoogleClient(unittest.TestCase):
    @patch("trae_agent.utils.google_client.genai.Client")
    def test_google_client_init(self, mock_genai_client):
        """Test the initialization of the GoogleClient."""
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="test-api-key", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        google_client = GoogleClient(model_config)
        mock_genai_client.assert_called_once_with(api_key="test-api-key")
        self.assertIsNotNone(google_client.client)

    @patch("trae_agent.utils.google_client.genai.Client")
    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-env-api-key"})
    def test_google_client_init_with_env_key(self, mock_genai_client):
        """
        Test that the google client initializes using the GOOGLE_API_KEY environment variable.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        google_client = GoogleClient(model_config)
        mock_genai_client.assert_called_once_with(api_key="test-env-api-key")
        self.assertEqual(google_client.api_key, "test-env-api-key")

    @patch.dict(os.environ, {"GOOGLE_API_KEY": ""})
    def test_google_client_init_no_key_raises_error(self):
        """
        Test that a ValueError is raised if no API key is provided.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        with self.assertRaises(ValueError):
            GoogleClient(model_config)

    @patch("trae_agent.utils.google_client.genai.Client")
    def test_google_set_chat_history(self, mock_genai_client):
        """
        Test that the chat history is correctly parsed and stored.
        """
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="test-api-key", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        google_client = GoogleClient(model_config)

        messages = [
            LLMMessage("system", "You are a helpful assistant."),
            LLMMessage("user", "Hello, world!"),
        ]
        google_client.set_chat_history(messages)

        self.assertEqual(google_client.system_instruction, "You are a helpful assistant.")
        self.assertEqual(len(google_client.message_history), 1)
        self.assertEqual(google_client.message_history[0].role, "user")
        self.assertEqual(google_client.message_history[0].parts[0].text, "Hello, world!")

    @patch("trae_agent.utils.google_client.genai.Client")
    def test_google_chat(self, mock_genai_client):
        """
        Test the chat method with a simple user message.
        """
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [MagicMock(text="Hello!")]
        mock_response.candidates[0].finish_reason.name = "STOP"
        mock_response.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=20)
        mock_model.generate_content.return_value = mock_response
        mock_genai_client.return_value.models = mock_model

        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="test-api-key", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
        )
        google_client = GoogleClient(model_config)
        message = LLMMessage("user", "this is a test message")
        response = google_client.chat(messages=[message], model_config=model_config)

        mock_model.generate_content.assert_called_once()
        self.assertEqual(response.content, "Hello!")
        self.assertEqual(response.usage.input_tokens, 10)
        self.assertEqual(response.usage.output_tokens, 20)
        self.assertEqual(response.finish_reason, "STOP")

    @patch("trae_agent.utils.google_client.genai.Client")
    def test_google_chat_with_tool_call(self, mock_genai_client):
        """
        Test the chat method's ability to handle tool calls.
        """
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_function_call = MagicMock()
        mock_function_call.name = "get_weather"
        mock_function_call.args = {"location": "Boston"}
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts = [
            MagicMock(function_call=mock_function_call, text=None)
        ]
        mock_response.candidates[0].finish_reason.name = "TOOL_CALL"
        mock_response.usage_metadata = MagicMock(prompt_token_count=30, candidates_token_count=15)
        mock_model.generate_content.return_value = mock_response
        mock_genai_client.return_value.models = mock_model

        mock_tool = MagicMock(spec=Tool)
        mock_tool.name = "get_weather"
        mock_tool.description = "Gets the weather for a location."
        mock_tool.get_input_schema.return_value = {
            "type": "object",
            "properties": {"location": {"type": "string"}},
        }

        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="test-api-key", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=1.0,
            top_k=1,
            parallel_tool_calls=True,
            max_retries=1,
        )
        google_client = GoogleClient(model_config)
        message = LLMMessage("user", "What is the weather in Boston?")
        response = google_client.chat(
            messages=[message], model_config=model_config, tools=[mock_tool]
        )

        self.assertEqual(response.content, "")
        self.assertIsNotNone(response.tool_calls)
        self.assertEqual(len(response.tool_calls), 1)
        tool_call = response.tool_calls[0]
        self.assertEqual(tool_call.name, "get_weather")
        self.assertEqual(tool_call.arguments, {"location": "Boston"})
        self.assertEqual(response.finish_reason, "TOOL_CALL")

    def test_parse_messages(self):
        """Test the parse_messages method with various message types."""
        google_client = GoogleClient(
            ModelConfig(
                model=TEST_MODEL,
                model_provider=ModelProvider(api_key="test-key", provider="google"),
                max_tokens=1000,
                temperature=0.8,
                top_p=1.0,
                top_k=1,
                parallel_tool_calls=True,
                max_retries=1,
            )
        )
        messages = [
            LLMMessage("system", "Be concise."),
            LLMMessage("user", "Hello"),
            LLMMessage(
                "model",
                "Hi there!",
                tool_call=ToolCall(name="search", arguments={"query": "news"}, call_id="tool-123"),
            ),
            LLMMessage(
                "tool",
                "Search results",
                tool_result=ToolResult(
                    call_id="12345", name="search", result="news data", success=True
                ),
            ),
        ]

        parsed_messages, system_instruction = google_client.parse_messages(messages)

        self.assertEqual(system_instruction, "Be concise.")
        self.assertEqual(len(parsed_messages), 3)
        self.assertEqual(parsed_messages[0].role, "user")
        self.assertEqual(parsed_messages[0].parts[0].text, "Hello")
        self.assertEqual(parsed_messages[1].role, "model")
        self.assertEqual(parsed_messages[1].parts[0].function_call.name, "search")
        self.assertEqual(parsed_messages[2].role, "tool")
        self.assertEqual(parsed_messages[2].parts[0].function_response.name, "search")

    def test_parse_tool_call_result(self):
        """
        Test the _parse_tool_call_result method.
        """
        google_client = GoogleClient(
            ModelConfig(
                model=TEST_MODEL,
                model_provider=ModelProvider(api_key="test-key", provider="google"),
                max_tokens=1000,
                temperature=0.8,
                top_p=1.0,
                top_k=1,
                parallel_tool_calls=True,
                max_retries=1,
            )
        )

        # Test with a simple result
        tool_result_simple = ToolResult(
            call_id="1", name="test_tool", result={"status": "done"}, success=True
        )
        parsed_part_simple = google_client.parse_tool_call_result(tool_result_simple)
        self.assertEqual(parsed_part_simple.function_response.name, "test_tool")
        self.assertEqual(
            parsed_part_simple.function_response.response,
            {"result": {"status": "done"}},
        )

        # Test with an error
        tool_result_error = ToolResult(
            call_id="2",
            name="test_tool",
            result="some data",
            error="Something went wrong",
            success=False,
        )
        parsed_part_error = google_client.parse_tool_call_result(tool_result_error)
        self.assertIn("error", parsed_part_error.function_response.response)
        self.assertEqual(
            parsed_part_error.function_response.response["error"],
            "Something went wrong",
        )

        # Test with non-serializable result
        non_serializable_obj = object()
        tool_result_non_serializable = ToolResult(
            call_id="3", name="test_tool", result=non_serializable_obj, success=True
        )
        parsed_part_non_serializable = google_client.parse_tool_call_result(
            tool_result_non_serializable
        )
        self.assertIn("result", parsed_part_non_serializable.function_response.response)
        self.assertEqual(
            parsed_part_non_serializable.function_response.response["result"],
            str(non_serializable_obj),
        )

    def test_supports_tool_calling(self):
        """Test the supports_tool_calling method."""
        model_config = ModelConfig(
            model=TEST_MODEL,
            model_provider=ModelProvider(api_key="test-api-key", provider="google"),
            max_tokens=1000,
            temperature=0.8,
            top_p=7.0,
            top_k=8,
            parallel_tool_calls=False,
            max_retries=1,
            base_url=None,
        )
        google_client = GoogleClient(model_config)
        self.assertEqual(google_client.supports_tool_calling(model_config), True)
        model_config.model = "no such model"
        self.assertEqual(google_client.supports_tool_calling(model_config), False)


if __name__ == "__main__":
    unittest.main()
