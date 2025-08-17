"""Tests for TaskIQ broker factory configuration."""

from taskiq import InMemoryBroker, ZeroMQBroker

import trae_api.tasks.broker
from trae_api.core.config import Settings
from trae_api.tasks.broker import broker, create_broker


class TestBrokerFactory:
    """Test broker factory with different configurations."""

    def test_pytest_environment_creates_inmemory_broker(self) -> None:
        """Test that pytest environment always creates InMemoryBroker."""
        # Create settings with pytest environment
        settings = Settings()
        settings.environment = "pytest"

        # Mock settings temporarily
        original_settings = trae_api.tasks.broker.settings
        trae_api.tasks.broker.settings = settings

        try:
            broker = create_broker()
            assert isinstance(broker, InMemoryBroker)
            assert broker.await_inplace is True
        finally:
            # Restore original settings
            trae_api.tasks.broker.settings = original_settings

    def test_dev_environment_creates_inmemory_broker_with_sqlite(self) -> None:
        """Test that dev environment creates InMemoryBroker with SQLite backend by default."""
        # Create settings with dev environment
        settings = Settings()
        settings.environment = "dev"
        settings.taskiq_broker = None  # Default to InMemory + SQLite for desktop

        # Mock settings temporarily
        original_settings = trae_api.tasks.broker.settings
        trae_api.tasks.broker.settings = settings

        try:
            broker = create_broker()
            assert isinstance(broker, InMemoryBroker)
            # Should have SQLite result backend for desktop deployment
            assert hasattr(broker, "result_backend")
            assert broker.result_backend is not None
        finally:
            # Restore original settings
            trae_api.tasks.broker.settings = original_settings

    def test_explicit_inmemory_broker_override(self) -> None:
        """Test explicit inmemory broker selection via environment."""
        # Create settings with explicit inmemory broker
        settings = Settings()
        settings.environment = "dev"
        settings.taskiq_broker = "inmemory"

        # Mock settings temporarily
        original_settings = trae_api.tasks.broker.settings
        trae_api.tasks.broker.settings = settings

        try:
            broker = create_broker()
            assert isinstance(broker, InMemoryBroker)
        finally:
            # Restore original settings
            trae_api.tasks.broker.settings = original_settings

    def test_explicit_zmq_broker_configuration(self) -> None:
        """Test explicit ZMQ broker with custom hosts."""
        # Create settings with custom ZMQ configuration
        settings = Settings()
        settings.environment = "production"
        settings.taskiq_broker = "zmq"
        settings.taskiq_zmq_pub_host = "tcp://127.0.0.1:7777"
        settings.taskiq_zmq_sub_host = "tcp://127.0.0.1:7778"

        # Mock settings temporarily
        original_settings = trae_api.tasks.broker.settings
        trae_api.tasks.broker.settings = settings

        try:
            broker = create_broker()
            assert isinstance(broker, ZeroMQBroker)
            # Note: Can't easily test internal host configuration without
            # accessing private attributes, but we verify the broker type
        finally:
            # Restore original settings
            trae_api.tasks.broker.settings = original_settings

    def test_unknown_broker_returns_default(self) -> None:
        """Test that unknown broker type returns default InMemory + SQLite."""
        # Create settings with unknown broker
        settings = Settings()
        settings.environment = "dev"
        settings.taskiq_broker = "unknown_broker"

        # Mock settings temporarily
        original_settings = trae_api.tasks.broker.settings
        trae_api.tasks.broker.settings = settings

        try:
            # Should return default instead of raising error (desktop-friendly)
            broker = create_broker()
            assert isinstance(broker, InMemoryBroker)
            assert hasattr(broker, "result_backend")
        finally:
            # Restore original settings
            trae_api.tasks.broker.settings = original_settings

    def test_current_broker_is_inmemory_in_tests(self) -> None:
        """Test that the actual broker instance is InMemoryBroker in test environment."""
        # In test environment, should be InMemoryBroker
        assert isinstance(broker, InMemoryBroker)
        assert broker.await_inplace is True
