# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""``supports_tool_calling`` has to answer for the model that was configured.

Three of the repository's own tests already say so (`test_ollama_client_utils.py:122`,
`test_openrouter_client_utils.py:118`, `test_google_client.py:311`), and all three are either
skipped in CI or die on an unrelated error first, so the claim goes unmeasured on a run.
Nothing here needs a daemon, a key that works, or a network: a client object is all the question
needs, and `openai.OpenAI(...)` does not connect until a request is made.
"""

import unittest

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.azure_client import AzureClient
from trae_agent.utils.llm_clients.doubao_client import DoubaoClient
from trae_agent.utils.llm_clients.llm_client import LLMClient
from trae_agent.utils.llm_clients.ollama_client import OllamaClient
from trae_agent.utils.llm_clients.openrouter_client import OpenRouterClient

CAPABLE_OPENROUTER_MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"
UNCAPABLE_MODEL = "no such model"


def make_model_config(
    provider: str,
    model: str = CAPABLE_OPENROUTER_MODEL,
    supports_tool_calling: bool = True,
) -> ModelConfig:
    endpoints = {
        "openrouter": "https://openrouter.ai/api/v1",
        "ollama": "http://127.0.0.1:11434/v1",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
        "azure": "https://example.azureopenai.com",
    }
    return ModelConfig(
        model=model,
        model_provider=ModelProvider(
            provider=provider,
            api_key="a-key-that-does-not-need-to-work",
            base_url=endpoints[provider],
            api_version="2024-02-01" if provider == "azure" else None,
        ),
        temperature=0.8,
        top_p=0.7,
        top_k=8,
        parallel_tool_calls=False,
        max_retries=1,
        supports_tool_calling=supports_tool_calling,
    )


class TestProviderListsAreReached(unittest.TestCase):
    def test_openrouter_answers_for_the_model_at_hand(self):
        capable = make_model_config("openrouter")
        self.assertTrue(OpenRouterClient(capable).supports_tool_calling(capable))

        uncapable = make_model_config("openrouter", model=UNCAPABLE_MODEL)
        self.assertFalse(OpenRouterClient(uncapable).supports_tool_calling(uncapable))

    def test_the_llm_client_wrapper_gives_the_same_answer(self):
        # `base_agent.py:37` and `lake_view.py:84` both go through LLMClient, so the answer has to
        # survive that hop rather than being re-derived from the config default.
        for model, expected in ((CAPABLE_OPENROUTER_MODEL, True), (UNCAPABLE_MODEL, False)):
            with self.subTest(model=model):
                model_config = make_model_config("openrouter", model=model)
                self.assertEqual(
                    LLMClient(model_config).supports_tool_calling(model_config), expected
                )

    def test_a_provider_that_accepts_every_model_still_answers_true(self):
        # Azure and Doubao state that all their deployments take tools; the check must not turn
        # that into False now that it is actually consulted.
        for provider, client in (("azure", AzureClient), ("doubao", DoubaoClient)):
            with self.subTest(provider=provider):
                model_config = make_model_config(provider, model=UNCAPABLE_MODEL)
                self.assertTrue(client(model_config).supports_tool_calling(model_config))

    def test_the_config_field_can_still_turn_the_capability_off(self):
        # The field stays an off switch: an explicit `supports_tool_calling: false` has to win over
        # a model name the provider list does accept.
        model_config = make_model_config("openrouter", supports_tool_calling=False)
        self.assertFalse(OpenRouterClient(model_config).supports_tool_calling(model_config))


class TestOllamaKeepsItsModelList(unittest.TestCase):
    def test_ollama_answers_for_the_tag_at_hand(self):
        capable = make_model_config("ollama", model="qwen3:4b")
        self.assertTrue(OllamaClient(capable).supports_tool_calling(capable))

        uncapable = make_model_config("ollama", model=UNCAPABLE_MODEL)
        self.assertFalse(OllamaClient(uncapable).supports_tool_calling(uncapable))

    def test_every_name_the_list_carries_still_matches(self):
        for name in OllamaClient.TOOL_CALLING_MODELS:
            with self.subTest(name=name):
                model_config = make_model_config("ollama", model=name)
                self.assertTrue(OllamaClient(model_config).supports_tool_calling(model_config))


if __name__ == "__main__":
    unittest.main()
