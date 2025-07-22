# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenAI-compatible client factory and base classes."""

from .base import OpenAICompatibleClient
from .factory import create_openai_compatible_client
from .providers import AzureProvider, DoubaoProvider, OpenRouterProvider

__all__ = [
    "OpenAICompatibleClient",
    "create_openai_compatible_client",
    "OpenRouterProvider",
    "AzureProvider",
    "DoubaoProvider",
]
