# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""An unset API key has to be reported as a configuration problem, not a network one.

These tests touch no network: the check runs in `BaseLLMClient.__init__`, before any SDK
client is constructed, so every case here is a construction-time assertion. The clients that
live behind the `SKIP_*_TEST`-gated files in `tests/utils/` construct with
`api_key=""` today and fail later with `openai.APIConnectionError: Connection error.`
"""

import unittest

from trae_agent.utils.config import ConfigError, ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.anthropic_client import AnthropicClient
from trae_agent.utils.llm_clients.azure_client import AzureClient
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.doubao_client import DoubaoClient
from trae_agent.utils.llm_clients.google_client import GoogleClient
from trae_agent.utils.llm_clients.ollama_client import OllamaClient
from trae_agent.utils.llm_clients.openai_client import OpenAIClient
from trae_agent.utils.llm_clients.openrouter_client import OpenRouterClient

CLIENTS: list[tuple[str, type[BaseLLMClient]]] = [
    ("openai", OpenAIClient),
    ("anthropic", AnthropicClient),
    ("google", GoogleClient),
    ("ollama", OllamaClient),
    ("openrouter", OpenRouterClient),
    ("azure", AzureClient),
    ("doubao", DoubaoClient),
]


def make_model_config(provider: str, api_key: str, base_url: str | None = None) -> ModelConfig:
    return ModelConfig(
        model="example-model",
        model_provider=ModelProvider(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            api_version="2024-02-01" if provider == "azure" else None,
        ),
        temperature=0.5,
        top_p=0.5,
        top_k=5,
        parallel_tool_calls=False,
        max_retries=3,
    )


class TestEmptyApiKeyIsRejected(unittest.TestCase):
    def test_every_client_raises_before_the_sdk_client_exists(self):
        for provider, client_class in CLIENTS:
            with self.subTest(provider=provider):
                with self.assertRaises(ConfigError) as raised:
                    client_class(make_model_config(provider, ""))
                self.assertNotIn("Connection error", str(raised.exception))

    def test_the_message_names_the_value_the_user_has_to_set(self):
        for provider, client_class in CLIENTS:
            with self.subTest(provider=provider):
                with self.assertRaises(ConfigError) as raised:
                    client_class(make_model_config(provider, ""))
                message = str(raised.exception)
                self.assertIn(provider, message)
                # the convention `ModelConfig.resolve_config_values` reads (config.py:97)
                self.assertIn(f"{provider.upper()}_API_KEY", message)
                self.assertIn("--api-key", message)

    def test_a_configured_key_still_builds_the_client(self):
        for provider, client_class in CLIENTS:
            with self.subTest(provider=provider):
                # Azure needs an endpoint to construct at all; nothing here connects.
                client = client_class(
                    make_model_config(
                        provider, "a-real-enough-key", base_url="http://127.0.0.1:1/v1"
                    )
                )
                self.assertEqual(client.api_key, "a-real-enough-key")


if __name__ == "__main__":
    unittest.main()
