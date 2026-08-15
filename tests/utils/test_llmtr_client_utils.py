# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the LLMTR client.

The routing tests are offline: they stub the model catalogue fetch, so they run
in CI without an API key. The live tests need a real key and are skipped when
SKIP_LLMTR_TEST is set.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trae_agent.utils.config import ModelConfig, ModelProvider
from trae_agent.utils.llm_clients.llm_basics import LLMMessage
from trae_agent.utils.llm_clients.llmtr_client import (
    LLMTR_BASE_URL,
    LLMTRChatCompletionsClient,
    LLMTRClient,
    LLMTRModelCatalog,
    LLMTRProvider,
    LLMTRResponsesClient,
    LLMTRRoute,
    is_reasoning_model,
    normalise_model_name,
)

# A slice of the real https://llmtr.com/v1/models response, covering every route.
CATALOG_FIXTURE = {
    "anthropic/claude-sonnet-5": ["/v1/chat/completions"],
    "llmtr/trendyol-asure-12b": ["/v1/chat/completions"],
    "google/gemini-2.5-pro": ["/v1/chat/completions", "/v1/responses"],
    "openai/gpt-5.3-codex": ["/v1/responses"],
    "xai/grok-4.3": ["/v1/responses"],
    "google/gemini-embedding-001": ["/v1/embeddings"],
    "google/veo-3.1-generate-001": ["/v1/video/generations"],
}

TEST_MODEL = "llmtr/qwen3-5-4b"


def make_model_config(model: str, api_key: str = "llmtr-test", base_url: str | None = None):
    return ModelConfig(
        model=model,
        model_provider=ModelProvider(
            provider="llmtr",
            api_key=api_key,
            base_url=base_url,
            api_version=None,
        ),
        max_tokens=1000,
        temperature=0.5,
        top_p=1.0,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=1,
    )


class TestModelNameHelpers(unittest.TestCase):
    def test_normalise_strips_reasoning_effort_suffix(self):
        self.assertEqual(normalise_model_name("openai/gpt-5.3-codex:high"), "openai/gpt-5.3-codex")
        self.assertEqual(
            normalise_model_name("anthropic/claude-sonnet-5"), "anthropic/claude-sonnet-5"
        )

    def test_reasoning_model_detection_ignores_suffix(self):
        self.assertTrue(is_reasoning_model("openai/gpt-5.3-codex:high"))
        self.assertTrue(is_reasoning_model("openai/o4-mini"))
        self.assertFalse(is_reasoning_model("anthropic/claude-sonnet-5"))
        self.assertFalse(is_reasoning_model("llmtr/trendyol-asure-12b"))


class TestLLMTRModelCatalog(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp_dir.name) / "llmtr_models.json"
        self.addCleanup(self._tmp_dir.cleanup)

    def make_catalog(self) -> LLMTRModelCatalog:
        return LLMTRModelCatalog("llmtr-test", LLMTR_BASE_URL, cache_path=self.cache_path)

    def test_routes_chat_completions_model(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertIs(
                catalog.route_for("anthropic/claude-sonnet-5"), LLMTRRoute.CHAT_COMPLETIONS
            )
            self.assertIs(
                catalog.route_for("llmtr/trendyol-asure-12b"), LLMTRRoute.CHAT_COMPLETIONS
            )

    def test_routes_responses_only_model(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertIs(catalog.route_for("openai/gpt-5.3-codex"), LLMTRRoute.RESPONSES)
            self.assertIs(catalog.route_for("xai/grok-4.3"), LLMTRRoute.RESPONSES)

    def test_reasoning_effort_suffix_still_routes(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertIs(catalog.route_for("openai/gpt-5.3-codex:high"), LLMTRRoute.RESPONSES)

    def test_dual_endpoint_model_prefers_chat_completions(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertIs(catalog.route_for("google/gemini-2.5-pro"), LLMTRRoute.CHAT_COMPLETIONS)

    def test_non_chat_models_are_unsupported(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertIs(catalog.route_for("google/gemini-embedding-001"), LLMTRRoute.UNSUPPORTED)
            self.assertIs(catalog.route_for("google/veo-3.1-generate-001"), LLMTRRoute.UNSUPPORTED)

    def test_unknown_model_falls_back_to_chat_completions(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertIs(catalog.route_for("brand/new-model"), LLMTRRoute.CHAT_COMPLETIONS)
            self.assertIsNone(catalog.supported_endpoints("brand/new-model"))

    def test_catalog_fetch_failure_does_not_raise(self):
        with patch.object(LLMTRModelCatalog, "_fetch", side_effect=OSError("network down")):
            catalog = self.make_catalog()
            self.assertEqual(catalog.endpoints(), {})
            self.assertIs(catalog.route_for("anything/at-all"), LLMTRRoute.CHAT_COMPLETIONS)

    def test_catalog_is_cached_to_disk_and_reused(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE) as fetch:
            self.make_catalog().endpoints()
            self.assertEqual(fetch.call_count, 1)
        self.assertTrue(self.cache_path.exists())

        # A fresh instance reads the cache instead of hitting the network.
        with patch.object(LLMTRModelCatalog, "_fetch", side_effect=AssertionError("refetched")):
            catalog = self.make_catalog()
            self.assertIs(catalog.route_for("openai/gpt-5.3-codex"), LLMTRRoute.RESPONSES)

    def test_expired_cache_triggers_refetch(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            self.make_catalog().endpoints()

        with patch.object(LLMTRModelCatalog, "_fetch", return_value={"a/b": ["/v1/embeddings"]}):
            catalog = LLMTRModelCatalog(
                "llmtr-test", LLMTR_BASE_URL, cache_path=self.cache_path, ttl_seconds=0
            )
            self.assertEqual(catalog.endpoints(), {"a/b": ["/v1/embeddings"]})

    def test_chat_capable_models_filters_by_owner(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            catalog = self.make_catalog()
            self.assertEqual(
                catalog.chat_capable_models(owner_prefix="openai"), ["openai/gpt-5.3-codex"]
            )
            self.assertNotIn("google/veo-3.1-generate-001", catalog.chat_capable_models())


class TestLLMTRClientRouting(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp_dir.name) / "llmtr_models.json"
        self.addCleanup(self._tmp_dir.cleanup)
        patcher = patch(
            "trae_agent.utils.llm_clients.llmtr_client.CATALOG_CACHE_PATH", self.cache_path
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_base_url(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            client = LLMTRClient(make_model_config("anthropic/claude-sonnet-5"))
        self.assertEqual(client.base_url, LLMTR_BASE_URL)

    def test_custom_base_url_is_preserved(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            client = LLMTRClient(
                make_model_config("anthropic/claude-sonnet-5", base_url="https://proxy.local/v1")
            )
        self.assertEqual(client.base_url, "https://proxy.local/v1")

    def test_chat_model_builds_chat_completions_client(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            client = LLMTRClient(make_model_config("anthropic/claude-sonnet-5"))
        self.assertIs(client.route, LLMTRRoute.CHAT_COMPLETIONS)
        self.assertIsInstance(client.client, LLMTRChatCompletionsClient)

    def test_responses_model_builds_responses_client(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            client = LLMTRClient(make_model_config("openai/gpt-5.3-codex"))
        self.assertIs(client.route, LLMTRRoute.RESPONSES)
        self.assertIsInstance(client.client, LLMTRResponsesClient)

    def test_non_chat_model_raises_immediately(self):
        with (
            patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE),
            self.assertRaises(ValueError) as ctx,
        ):
            LLMTRClient(make_model_config("google/gemini-embedding-001"))
        message = str(ctx.exception)
        self.assertIn("/v1/embeddings", message)
        # The error should point the user at something that actually works.
        self.assertIn("google/gemini-2.5-pro", message)

    def test_endpoint_mismatch_switches_to_responses(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            client = LLMTRClient(make_model_config("anthropic/claude-sonnet-5"))
        mismatch = Exception(
            'Error code: 400 - {"error": {"message": "Model \\"x\\" requires the '
            '/v1/responses endpoint instead of /v1/chat/completions.", '
            '"type": "endpoint_mismatch"}}'
        )
        self.assertTrue(client._can_switch_to_responses(mismatch))
        # Unrelated failures must propagate rather than trigger a route switch.
        self.assertFalse(client._can_switch_to_responses(Exception("rate_limit_exceeded")))
        # And the switch is only valid before the first successful exchange.
        client._completed_exchanges = 1
        self.assertFalse(client._can_switch_to_responses(mismatch))


class TestLLMTRProvider(unittest.TestCase):
    def test_provider_metadata(self):
        provider = LLMTRProvider()
        self.assertEqual(provider.get_service_name(), "LLMTR")
        self.assertEqual(provider.get_provider_name(), "llmtr")
        self.assertEqual(provider.get_extra_headers(), {})

    def test_tool_calling_is_not_name_gated(self):
        provider = LLMTRProvider()
        # LLMTR model ids do not encode capabilities, so no name heuristic applies.
        self.assertTrue(provider.supports_tool_calling("anthropic/claude-opus-5"))
        self.assertTrue(provider.supports_tool_calling("llmtr/trendyol-asure-12b"))
        self.assertTrue(provider.supports_tool_calling("moonshot/kimi-k3"))

    def test_supports_tool_calling_respects_model_config(self):
        with patch.object(LLMTRModelCatalog, "_fetch", return_value=CATALOG_FIXTURE):
            model_config = make_model_config("anthropic/claude-sonnet-5")
            client = LLMTRClient(model_config)
        self.assertTrue(client.supports_tool_calling(model_config))
        model_config.supports_tool_calling = False
        self.assertFalse(client.supports_tool_calling(model_config))


@unittest.skipIf(
    os.getenv("SKIP_LLMTR_TEST", "").lower() == "true",
    "LLMTR tests skipped due to SKIP_LLMTR_TEST environment variable",
)
class TestLLMTRClientLive(unittest.TestCase):
    """Live tests against the LLMTR gateway. Requires LLMTR_API_KEY."""

    def setUp(self):
        if not os.getenv("LLMTR_API_KEY"):
            self.skipTest("LLMTR_API_KEY is not set")

    def test_catalogue_is_publicly_readable(self):
        catalog = LLMTRModelCatalog(os.getenv("LLMTR_API_KEY", ""), LLMTR_BASE_URL)
        self.assertGreater(len(catalog.endpoints()), 0)

    def test_chat_completions_route(self):
        model_config = make_model_config(TEST_MODEL, api_key=os.getenv("LLMTR_API_KEY", ""))
        client = LLMTRClient(model_config)
        self.assertIs(client.route, LLMTRRoute.CHAT_COMPLETIONS)
        response = client.chat([LLMMessage("user", "Reply with the word OK.")], model_config)
        self.assertTrue(response.content)

    def test_responses_route(self):
        model_config = make_model_config("xai/grok-4.3", api_key=os.getenv("LLMTR_API_KEY", ""))
        client = LLMTRClient(model_config)
        self.assertIs(client.route, LLMTRRoute.RESPONSES)
        response = client.chat([LLMMessage("user", "Reply with the word OK.")], model_config)
        self.assertTrue(response.content)


if __name__ == "__main__":
    unittest.main()
