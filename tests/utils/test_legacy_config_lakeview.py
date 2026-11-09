# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Lakeview model_provider must exist in model_providers."""

import pytest

from trae_agent.utils.legacy_config import LegacyConfig


def _base_config(**overrides):
    config = {
        "default_provider": "anthropic",
        "max_steps": 20,
        "model_providers": {
            "anthropic": {
                "model": "claude-sonnet-4-20250514",
                "api_key": "test-key",
            }
        },
    }
    config.update(overrides)
    return config


class TestLakeviewModelProviderValidation:
    """default_provider not in model_providers must raise a clear error.

    The old code accessed self.model_providers[model_provider] directly,
    raising an unhelpful KeyError when default_provider named a provider
    that was not defined in model_providers.
    """

    def test_missing_provider_raises_clear_error(self):
        config = _base_config(
            default_provider="openai",
            enable_lakeview=True,
        )
        with pytest.raises(ValueError, match="openai.*not defined.*model_providers"):
            LegacyConfig(config)

    def test_valid_provider_works(self):
        config = _base_config(enable_lakeview=True)
        lc = LegacyConfig(config)
        assert lc.lakeview_config is not None
        assert lc.lakeview_config.model_provider == "anthropic"

    def test_explicit_lakeview_provider_not_in_providers_raises(self):
        config = _base_config(
            enable_lakeview=True,
            lakeview_config={"model_provider": "groq", "model_name": "llama3"},
        )
        with pytest.raises(ValueError, match="groq.*not defined.*model_providers"):
            LegacyConfig(config)

    def test_lakeview_disabled_skips_check(self):
        """When lakeview is disabled, the provider check is not needed."""
        config = _base_config(
            default_provider="openai",
            enable_lakeview=False,
        )
        lc = LegacyConfig(config)
        assert lc.lakeview_config is None
