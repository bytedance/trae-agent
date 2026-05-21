# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import os
import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.atomic_chat_client import (
    DEFAULT_ATOMIC_CHAT_BASE_URL,
    AtomicChatClient,
)
from trae_agent.utils.llm_clients.llm_client import LLMClient, LLMProvider


class TestAtomicChatClient(unittest.TestCase):
    def test_default_base_url_and_api_key(self):
        model_config = ModelConfig(
            model="gemma-4-E4B-it-IQ4_XS",
            model_provider=ModelProvider(
                provider="atomic_chat",
                api_key="",
                base_url=None,
            ),
            max_tokens=4096,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=True,
            max_retries=3,
        )
        client = AtomicChatClient(model_config)
        self.assertEqual(client.base_url, DEFAULT_ATOMIC_CHAT_BASE_URL)
        self.assertEqual(model_config.model_provider.api_key, "noop")

    def test_llm_client_provider_enum(self):
        model_config = ModelConfig(
            model="test-model",
            model_provider=ModelProvider(
                provider="atomic_chat",
                api_key="noop",
                base_url=DEFAULT_ATOMIC_CHAT_BASE_URL,
            ),
            max_tokens=1024,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=True,
            max_retries=1,
        )
        llm = LLMClient(model_config)
        self.assertEqual(llm.provider, LLMProvider.ATOMIC_CHAT)

    def test_supports_tool_calling_heuristic(self):
        model_config = ModelConfig(
            model="Qwen3_5-9B-Q4_K_M",
            model_provider=ModelProvider(
                provider="atomic_chat",
                api_key="noop",
                base_url=DEFAULT_ATOMIC_CHAT_BASE_URL,
            ),
            max_tokens=1024,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=True,
            max_retries=1,
        )
        client = AtomicChatClient(model_config)
        self.assertTrue(client.supports_tool_calling(model_config))
        model_config.model = "unknown-embed-model"
        self.assertFalse(client.supports_tool_calling(model_config))


@unittest.skipIf(
    os.getenv("SKIP_ATOMIC_CHAT_TEST", "").lower() == "true",
    "Atomic Chat live tests skipped (set SKIP_ATOMIC_CHAT_TEST=false to run)",
)
class TestAtomicChatClientLive(unittest.TestCase):
    def test_chat_requires_running_server(self):
        model_config = ModelConfig(
            model=os.getenv("ATOMIC_CHAT_MODEL", "gemma-4-E4B-it-IQ4_XS"),
            model_provider=ModelProvider(
                provider="atomic_chat",
                api_key=os.getenv("ATOMIC_CHAT_API_KEY", "noop"),
                base_url=os.getenv("ATOMIC_CHAT_BASE_URL", DEFAULT_ATOMIC_CHAT_BASE_URL),
            ),
            max_tokens=256,
            temperature=0.5,
            top_p=1,
            top_k=0,
            parallel_tool_calls=False,
            max_retries=1,
        )
        from trae_agent.utils.llm_clients.llm_basics import LLMMessage

        client = AtomicChatClient(model_config)
        response = client.chat(
            messages=[LLMMessage(role="user", content="Reply with exactly: ok")],
            model_config=model_config,
            reuse_history=False,
        )
        self.assertTrue(response.content)


if __name__ == "__main__":
    unittest.main()
