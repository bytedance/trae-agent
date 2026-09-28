# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""`openai.OpenAI(base_url=None)` means "send this key to api.openai.com", not "no endpoint yet".

`DoubaoClient` passed the configured `base_url` straight through, so a doubao config without one
posted the user's Doubao key to OpenAI's host and surfaced OpenAI's authentication error. These
tests only construct a client and read the URL it would use: `openai.OpenAI` does not connect
until a request, so no key and no network are involved.
"""

import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.doubao_client import DoubaoClient

TEST_MODEL = "doubao-seed-1.6"


def doubao_config(base_url: str | None) -> ModelConfig:
    return ModelConfig(
        TEST_MODEL,
        model_provider=ModelProvider(
            provider="doubao",
            api_key="a-key-that-does-not-need-to-work",
            base_url=base_url,
            api_version=None,
        ),
        max_tokens=1000,
        temperature=0.8,
        top_p=0.7,
        top_k=8,
        parallel_tool_calls=False,
        max_retries=1,
    )


class TestDoubaoBaseURL(unittest.TestCase):
    def target(self, base_url: str | None) -> tuple[str, str]:
        client = DoubaoClient(doubao_config(base_url))
        url = client.client.base_url
        return url.host, url.path.rstrip("/")

    def test_a_missing_base_url_targets_the_ark_endpoint(self):
        self.assertEqual(self.target(None), ("ark.cn-beijing.volces.com", "/api/v3"))

    def test_an_empty_base_url_targets_the_ark_endpoint(self):
        self.assertEqual(self.target(""), ("ark.cn-beijing.volces.com", "/api/v3"))

    def test_a_doubao_key_is_not_sent_to_openais_host(self):
        host, _ = self.target(None)
        self.assertNotEqual(host, "api.openai.com")

    def test_a_configured_base_url_is_used_as_configured(self):
        endpoint = "https://ark-vpc.internal.example.com/api/v3"
        self.assertEqual(self.target(endpoint), ("ark-vpc.internal.example.com", "/api/v3"))


if __name__ == "__main__":
    unittest.main()
