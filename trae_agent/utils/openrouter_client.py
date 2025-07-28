# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenRouter API client wrapper with tool integration."""

from .config import ModelParameters
from .models.openai_compatible_base import OpenAICompatibleClient
from .models.openrouter import OpenRouterProvider


class OpenRouterClient(OpenAICompatibleClient):
    """OpenRouter client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters, OpenRouterProvider())
