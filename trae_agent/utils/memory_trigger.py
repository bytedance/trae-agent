# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Memory trigger factory for long-term memory extraction."""

from abc import ABC, abstractmethod

from trae_agent.agent.agent_basics import AgentStep


class MemoryTrigger(ABC):
    """Abstract base class for memory extraction triggers."""

    @abstractmethod
    def should_trigger(self, step: AgentStep, steps_completed: int) -> bool:
        """Decide whether to trigger memory extraction.

        Args:
            step: The step that just completed.
            steps_completed: Total number of completed steps so far.

        Returns:
            True if memory extraction should be triggered now.
        """
        pass

    @abstractmethod
    def trigger_type_name(self) -> str:
        """Return a human-readable name for this trigger type."""
        pass


class ManualMemoryTrigger(MemoryTrigger):
    """Only triggers when explicitly called by the user."""

    def should_trigger(self, step: AgentStep, steps_completed: int) -> bool:
        return False

    def trigger_type_name(self) -> str:
        return "manual"


class PeriodicMemoryTrigger(MemoryTrigger):
    """Triggers every N steps."""

    def __init__(self, interval: int = 10):
        self._interval = interval
        self._last_triggered_at: int = 0

    def should_trigger(self, step: AgentStep, steps_completed: int) -> bool:
        if steps_completed > 0 and steps_completed % self._interval == 0 and steps_completed != self._last_triggered_at:
            self._last_triggered_at = steps_completed
            return True
        return False

    def trigger_type_name(self) -> str:
        return f"periodic(every {self._interval} steps)"


def create_memory_trigger(trigger_type: str, periodic_interval: int = 10) -> MemoryTrigger:
    """Factory: create the appropriate trigger based on config."""
    match trigger_type:
        case "manual":
            return ManualMemoryTrigger()
        case "periodic":
            return PeriodicMemoryTrigger(interval=periodic_interval)
        case _:
            raise ValueError(f"Unknown memory trigger_type: {trigger_type}")
