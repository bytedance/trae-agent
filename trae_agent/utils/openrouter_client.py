# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenRouter API client wrapper with tool integration."""

from ..utils.config import ModelParameters
from .models.openai_compatible_factory import create_openai_compatible_client


def OpenRouterClient(model_parameters: ModelParameters):
    """Factory function to create OpenRouter client using the new architecture."""
    return create_openai_compatible_client("openrouter", model_parameters)
