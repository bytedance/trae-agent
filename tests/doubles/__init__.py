"""Test doubles package for reliable testing without external dependencies."""

from .agent_doubles import (
    FakeAgentExecutorService,
    FailingAgentExecutorService, 
    ResourceConstrainedAgentService,
    SlowAgentExecutorService,
)

__all__ = [
    "FakeAgentExecutorService",
    "FailingAgentExecutorService",
    "ResourceConstrainedAgentService", 
    "SlowAgentExecutorService",
]