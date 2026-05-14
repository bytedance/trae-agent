# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Three-layer compression infrastructure: micro (in-loop), session (phase handoff), global (persistent)."""

from trae_agent.compression.compressor import (
    ContextCompressor,
    MicroCompressionStrategy,
    SessionCompressionStrategy,
)
from trae_agent.compression.global_state import GlobalStateManager, GlobalStateSchema
from trae_agent.compression.types import (
    CompressionContext,
    CompressionReport,
    CompressionTrigger,
    SessionSummary,
)

__all__ = [
    "CompressionContext",
    "CompressionReport",
    "CompressionTrigger",
    "ContextCompressor",
    "GlobalStateManager",
    "GlobalStateSchema",
    "MicroCompressionStrategy",
    "SessionCompressionStrategy",
    "SessionSummary",
]
