# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Unit tests for the CheaperInferenceClient.

These tests mock the OpenAI SDK, so they do not need an API key or network access.
"""

import unittest
from unittest.mock import MagicMock, patch

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.cheaperinference_client import CheaperInferenceClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.llm_client import LLMClient, LLMProvider

TEST_MODEL = "gpt-5.4-mini"
DEFAULT_BASE_URL = "https://api.cheaperinference.com/v1"


def make_model_config(base_url: str | None = None) -> ModelConfig:
    return ModelConfig(
        model=TEST_MODEL,
        model_provider=ModelProvider(
            api_key="test-api-key",
            provider="cheaperinference",
            base_url=base_url,
        ),
        max_tokens=1000,
        temperature=0.8,
        top_p=1,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=1,
    )


class TestCheaperInferenceClient(unittest.TestCase):
    def test_default_base_url(self):
        client = CheaperInferenceClient(make_model_config())
        self.assertEqual(client.base_url, DEFAULT_BASE_URL)
        self.assertEqual(str(client.client.base_url).rstrip("/"), DEFAULT_BASE_URL)

    def test_custom_base_url(self):
        client = CheaperInferenceClient(make_model_config("https://example.com/v1"))
        self.assertEqual(client.base_url, "https://example.com/v1")

    def test_provider_config(self):
        client = CheaperInferenceClient(make_model_config())
        self.assertEqual(client.provider_config.get_provider_name(), "cheaperinference")
        self.assertEqual(client.provider_config.get_service_name(), "Cheaper Inference")
        self.assertEqual(client.provider_config.get_extra_headers(), {})
        self.assertTrue(client.provider_config.supports_tool_calling(TEST_MODEL))

    def test_llm_client_routes_to_cheaperinference(self):
        llm_client = LLMClient(make_model_config())
        self.assertEqual(llm_client.provider, LLMProvider.CHEAPERINFERENCE)
        self.assertIsInstance(llm_client.client, CheaperInferenceClient)

    def test_chat(self):
        client = CheaperInferenceClient(make_model_config())
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = TEST_MODEL
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 1

        with patch.object(
            client.client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            model_config = make_model_config()
            response = client.chat(
                [LLMMessage(role="user", content="Hi")], model_config=model_config
            )

        self.assertEqual(response.content, "Hello")
        self.assertEqual(response.model, TEST_MODEL)
        self.assertEqual(mock_create.call_args.kwargs["model"], TEST_MODEL)


if __name__ == "__main__":
    unittest.main()
