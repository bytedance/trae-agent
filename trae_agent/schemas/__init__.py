"""Shared schemas for trae_agent HTTP API and CLI."""

from .requests import ConfigReloadRequest, ConfigRequest, RunRequest
from .responses import (
    ConfigResponse,
    ErrorResponse,
    ExecutionStats,
    LLMInteraction,
    Patch,
    RunResponse,
    StreamEvent,
    TrajectoryData,
)

__all__ = [
    "RunRequest",
    "ConfigRequest", 
    "ConfigReloadRequest",
    "RunResponse",
    "ConfigResponse",
    "StreamEvent",
    "ErrorResponse",
    "TrajectoryData",
    "ExecutionStats",
    "LLMInteraction",
    "Patch",
]