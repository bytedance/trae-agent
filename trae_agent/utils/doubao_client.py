# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Doubao client wrapper with tool integrations"""

from .config import ModelParameters
from .models.openai_compatible_factory import create_openai_compatible_client


def DoubaoClient(model_parameters: ModelParameters):
    """Factory function to create Doubao client using the new architecture."""
    return create_openai_compatible_client("doubao", model_parameters)
