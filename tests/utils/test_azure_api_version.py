# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Azure needs an api_version, but only the openai SDK ever told the user so.

`ModelProvider.api_version` is optional and `AzureProvider.create_client` passed it straight to
`openai.AzureOpenAI`, which raises its own error naming `OPENAI_API_VERSION` -- a variable no
trae-agent documentation mentions, while the convention this project uses for every other provider
field is `<PROVIDER>_API_KEY` / `<PROVIDER>_BASE_URL`. An empty `api_version` was worse: the SDK
accepts it and drops the `api-version` query parameter from every request.

These tests only build a client or capture the arguments handed to the SDK. `openai.AzureOpenAI`
does not connect until a request is made, so no usable key and no network are involved.
"""

import os
import unittest
from unittest.mock import patch

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.azure_client import AzureClient

TEST_MODEL = "gpt-4o"
AZURE_ENDPOINT = "https://demo.openai.azure.com"
CONFIGURED_VERSION = "2024-03-01-preview"
ENVIRONMENT_VERSION = "2024-05-01-preview"
MANAGED_VARS = ("AZURE_API_VERSION", "OPENAI_API_VERSION")


def azure_config(
    base_url: str | None = AZURE_ENDPOINT,
    api_version: str | None = CONFIGURED_VERSION,
) -> ModelConfig:
    return ModelConfig(
        TEST_MODEL,
        model_provider=ModelProvider(
            provider="azure",
            api_key="a-key-that-does-not-need-to-work",
            base_url=base_url,
            api_version=api_version,
        ),
        max_tokens=1000,
        temperature=0.8,
        top_p=0.7,
        top_k=8,
        parallel_tool_calls=False,
        max_retries=1,
    )


def env_without_api_versions(**extra: str) -> dict[str, str]:
    """The process environment, minus both api-version variables, plus whatever a test needs."""
    env = {key: value for key, value in os.environ.items() if key not in MANAGED_VARS}
    env.update(extra)
    return env


class TestAzureAPIVersion(unittest.TestCase):
    def api_version_given_to_the_sdk(self, model_config: ModelConfig) -> str:
        """Build the provider client with the SDK stubbed out and report the api_version it got."""
        with patch("openai.AzureOpenAI") as azure_openai:
            AzureClient(model_config)
        self.assertEqual(len(azure_openai.call_args_list), 1)
        return azure_openai.call_args_list[0].kwargs["api_version"]

    def test_a_configured_api_version_reaches_the_sdk(self):
        with patch.dict(os.environ, env_without_api_versions(), clear=True):
            self.assertEqual(self.api_version_given_to_the_sdk(azure_config()), CONFIGURED_VERSION)

    def test_azure_api_version_environment_variable_is_honoured(self):
        model_config = azure_config(api_version=None)
        environment = env_without_api_versions(AZURE_API_VERSION=ENVIRONMENT_VERSION)
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(self.api_version_given_to_the_sdk(model_config), ENVIRONMENT_VERSION)
        # The same configuration must also survive a real SDK client, not just the stub above.
        with patch.dict(os.environ, environment, clear=True):
            client = AzureClient(model_config)
        self.assertEqual(str(client.client.base_url), f"{AZURE_ENDPOINT}/openai/")

    def test_openai_api_version_environment_variable_still_works(self):
        model_config = azure_config(api_version=None)
        environment = env_without_api_versions(OPENAI_API_VERSION=ENVIRONMENT_VERSION)
        with patch.dict(os.environ, environment, clear=True):
            client = AzureClient(model_config)
        self.assertEqual(str(client.client.base_url), f"{AZURE_ENDPOINT}/openai/")

    def test_the_configured_value_wins_over_the_environment(self):
        model_config = azure_config(api_version=CONFIGURED_VERSION)
        environment = env_without_api_versions(AZURE_API_VERSION=ENVIRONMENT_VERSION)
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(self.api_version_given_to_the_sdk(model_config), CONFIGURED_VERSION)

    def test_a_resolved_client_targets_the_azure_endpoint(self):
        with patch.dict(os.environ, env_without_api_versions(), clear=True):
            client = AzureClient(azure_config())
        self.assertEqual(str(client.client.base_url), f"{AZURE_ENDPOINT}/openai/")

    def test_a_missing_api_version_names_the_configuration_field(self):
        model_config = azure_config(api_version=None)
        with (
            patch.dict(os.environ, env_without_api_versions(), clear=True),
            self.assertRaises(ValueError) as captured,
        ):
            AzureClient(model_config)
        message = str(captured.exception)
        self.assertIn("api_version is required for AzureClient", message)
        self.assertIn("AZURE_API_VERSION", message)

    def test_an_empty_api_version_is_not_passed_through(self):
        model_config = azure_config(api_version="")
        with (
            patch.dict(os.environ, env_without_api_versions(), clear=True),
            self.assertRaises(ValueError) as captured,
        ):
            AzureClient(model_config)
        self.assertIn("api_version is required for AzureClient", str(captured.exception))

    def test_base_url_is_still_required(self):
        model_config = azure_config(base_url=None)
        with (
            patch.dict(os.environ, env_without_api_versions(), clear=True),
            self.assertRaises(ValueError) as captured,
        ):
            AzureClient(model_config)
        self.assertIn("base_url is required for AzureClient", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
