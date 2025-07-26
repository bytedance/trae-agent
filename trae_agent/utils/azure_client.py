# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Azure client wrapper with tool integrations"""

from .config import ModelParameters
from .models.azure import AzureProvider
from .models.openai_compatible_base import OpenAICompatibleClient


class AzureClient(OpenAICompatibleClient):
    """Azure client wrapper that maintains compatibility while using the new architecture."""

    def __init__(self, model_parameters: ModelParameters):
        super().__init__(model_parameters, AzureProvider())
