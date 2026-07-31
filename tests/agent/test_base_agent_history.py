# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for BaseAgent message history truncation functionality."""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock tree_sitter_languages before importing trae_agent modules
# to avoid ModuleNotFoundError in test environment
sys.modules.setdefault("tree_sitter_languages", MagicMock())

from trae_agent.agent.base_agent import BaseAgent
from trae_agent.utils.config import AgentConfig, ModelConfig
from trae_agent.utils.llm_clients.llm_basics import LLMMessage


class MockAgent(BaseAgent):
    """Mock agent for testing BaseAgent functionality."""

    def __init__(self, agent_config: AgentConfig):
        """Initialize mock agent."""
        super().__init__(agent_config)

    async def new_task(self, task: str, **kwargs):
        """Mock new_task implementation."""
        pass

    async def cleanup_mcp_clients(self):
        """Mock cleanup implementation."""
        pass


class TestBaseAgentHistoryLength(unittest.TestCase):
    """Test cases for BaseAgent max_history_length functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock model config
        self.mock_model_config = MagicMock(spec=ModelConfig)
        self.mock_model_config.model = "test-model"
        self.mock_model_config.model_provider = "test-provider"

        # Patch LLMClient to avoid actual initialization
        self.llm_patcher = patch("trae_agent.agent.base_agent.LLMClient")
        self.mock_llm_client = self.llm_patcher.start()

        # Patch tools_registry to avoid tool initialization
        self.tools_patcher = patch("trae_agent.agent.base_agent.tools_registry", {})
        self.tools_patcher.start()

    def tearDown(self):
        """Tear down test fixtures."""
        self.llm_patcher.stop()
        self.tools_patcher.stop()

    def test_default_max_history_length(self):
        """Test that default max_history_length is 100 when not specified."""
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.model = self.mock_model_config
        agent_config.max_steps = 10
        agent_config.tools = []
        # Remove max_history_length attribute to simulate it not being set
        if hasattr(agent_config, "max_history_length"):
            delattr(agent_config, "max_history_length")

        agent = MockAgent(agent_config)

        self.assertEqual(agent.max_history_length, 100)
        self.assertEqual(agent._max_history_length, 100)

    def test_custom_max_history_length(self):
        """Test that custom max_history_length is read from config."""
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.model = self.mock_model_config
        agent_config.max_steps = 10
        agent_config.tools = []
        agent_config.max_history_length = 50

        agent = MockAgent(agent_config)

        self.assertEqual(agent.max_history_length, 50)
        self.assertEqual(agent._max_history_length, 50)

    def test_max_history_length_with_none_value(self):
        """Test that None value falls back to default 100."""
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.model = self.mock_model_config
        agent_config.max_steps = 10
        agent_config.tools = []
        agent_config.max_history_length = None

        agent = MockAgent(agent_config)

        self.assertEqual(agent.max_history_length, 100)


class TestTruncateMessages(unittest.TestCase):
    """Test cases for _truncate_messages method."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_model_config = MagicMock(spec=ModelConfig)
        self.mock_model_config.model = "test-model"
        self.mock_model_config.model_provider = "test-provider"

        # Patch dependencies
        self.llm_patcher = patch("trae_agent.agent.base_agent.LLMClient")
        self.mock_llm_client = self.llm_patcher.start()

        self.tools_patcher = patch("trae_agent.agent.base_agent.tools_registry", {})
        self.tools_patcher.start()

    def tearDown(self):
        """Tear down test fixtures."""
        self.llm_patcher.stop()
        self.tools_patcher.stop()

    def _create_agent_with_history_length(self, max_length: int) -> MockAgent:
        """Helper to create agent with specific max_history_length."""
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.model = self.mock_model_config
        agent_config.max_steps = 10
        agent_config.tools = []
        agent_config.max_history_length = max_length
        return MockAgent(agent_config)

    def _create_message(self, role: str, content: str = None) -> LLMMessage:
        """Helper to create LLMMessage."""
        return LLMMessage(role=role, content=content or f"{role} message")

    def test_truncate_no_truncation_needed(self):
        """Test that messages under limit are not truncated."""
        agent = self._create_agent_with_history_length(10)

        messages = [
            self._create_message("system", "You are a helpful assistant"),
            self._create_message("user", "Hello"),
            self._create_message("assistant", "Hi there"),
        ]

        result = agent._truncate_messages(messages)

        self.assertEqual(len(result), 3)
        self.assertEqual(result, messages)

    def test_truncate_exactly_at_limit(self):
        """Test that messages exactly at limit are not truncated."""
        agent = self._create_agent_with_history_length(2)

        messages = [
            self._create_message("user", "Message 1"),
            self._create_message("assistant", "Message 2"),
        ]

        result = agent._truncate_messages(messages)

        self.assertEqual(len(result), 2)
        self.assertEqual(result, messages)

    def test_truncate_conversation_messages(self):
        """Test that conversation messages are truncated while preserving system messages."""
        agent = self._create_agent_with_history_length(3)

        messages = [
            self._create_message("system", "System prompt"),
            self._create_message("user", "User 1"),
            self._create_message("assistant", "Assistant 1"),
            self._create_message("user", "User 2"),
            self._create_message("assistant", "Assistant 2"),
            self._create_message("user", "User 3"),
            self._create_message("assistant", "Assistant 3"),
        ]

        result = agent._truncate_messages(messages)

        # Should have 1 system + 3 most recent conversation messages
        self.assertEqual(len(result), 4)
        # System message should be first
        self.assertEqual(result[0].role, "system")
        self.assertEqual(result[0].content, "System prompt")
        # Should keep the 3 most recent conversation messages
        self.assertEqual(result[1].content, "Assistant 2")
        self.assertEqual(result[2].content, "User 3")
        self.assertEqual(result[3].content, "Assistant 3")

    def test_truncate_preserves_all_system_messages(self):
        """Test that all system messages are preserved regardless of limit."""
        agent = self._create_agent_with_history_length(2)

        messages = [
            self._create_message("system", "System prompt 1"),
            self._create_message("system", "System prompt 2"),
            self._create_message("user", "User 1"),
            self._create_message("assistant", "Assistant 1"),
            self._create_message("user", "User 2"),
            self._create_message("assistant", "Assistant 2"),
            self._create_message("user", "User 3"),
        ]

        result = agent._truncate_messages(messages)

        # Should have 2 system + 2 most recent conversation messages
        self.assertEqual(len(result), 4)
        # Both system messages should be preserved
        self.assertEqual(result[0].role, "system")
        self.assertEqual(result[0].content, "System prompt 1")
        self.assertEqual(result[1].role, "system")
        self.assertEqual(result[1].content, "System prompt 2")
        # Should keep the 2 most recent conversation messages
        self.assertEqual(result[2].content, "Assistant 2")
        self.assertEqual(result[3].content, "User 3")

    def test_truncate_empty_messages(self):
        """Test truncation with empty message list."""
        agent = self._create_agent_with_history_length(10)

        result = agent._truncate_messages([])

        self.assertEqual(len(result), 0)

    def test_truncate_only_system_messages(self):
        """Test truncation with only system messages."""
        agent = self._create_agent_with_history_length(1)

        messages = [
            self._create_message("system", "System 1"),
            self._create_message("system", "System 2"),
        ]

        result = agent._truncate_messages(messages)

        # All system messages should be preserved
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].role, "system")
        self.assertEqual(result[1].role, "system")

    def test_truncate_keeps_most_recent_messages(self):
        """Test that truncation keeps the most recent messages."""
        agent = self._create_agent_with_history_length(2)

        messages = [
            self._create_message("user", "Old message 1"),
            self._create_message("assistant", "Old message 2"),
            self._create_message("user", "Recent message 1"),
            self._create_message("assistant", "Recent message 2"),
        ]

        result = agent._truncate_messages(messages)

        # Should keep only the 2 most recent conversation messages
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].content, "Recent message 1")
        self.assertEqual(result[1].content, "Recent message 2")

    def test_truncate_with_zero_limit(self):
        """Test truncation with max_history_length of 0."""
        agent = self._create_agent_with_history_length(0)

        messages = [
            self._create_message("system", "System prompt"),
            self._create_message("user", "User message"),
            self._create_message("assistant", "Assistant message"),
        ]

        result = agent._truncate_messages(messages)

        # Should only keep system messages
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].role, "system")

    def test_truncate_preserves_message_order(self):
        """Test that message order is preserved after truncation."""
        agent = self._create_agent_with_history_length(4)

        messages = [
            self._create_message("system", "System"),
            self._create_message("user", "1"),
            self._create_message("assistant", "2"),
            self._create_message("user", "3"),
            self._create_message("assistant", "4"),
            self._create_message("user", "5"),
            self._create_message("assistant", "6"),
        ]

        result = agent._truncate_messages(messages)

        # Should have system + 4 most recent in original order
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0].content, "System")
        self.assertEqual(result[1].content, "3")
        self.assertEqual(result[2].content, "4")
        self.assertEqual(result[3].content, "5")
        self.assertEqual(result[4].content, "6")


if __name__ == "__main__":
    unittest.main()
