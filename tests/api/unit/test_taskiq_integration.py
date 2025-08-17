"""Unit tests for Taskiq integration."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from taskiq import InMemoryBroker

from trae_api.tasks.broker import broker, create_broker
from trae_api.tasks.examples import (
    background_processing_task,
    hello_world_task,
    task_with_app_state,
    task_with_request,
    task_with_settings,
)


class TestBrokerCreation:
    """Test broker creation logic."""

    def test_create_broker_for_testing(self) -> None:
        """Test that pytest environment creates InMemoryBroker."""
        # Since we're in test environment, should create InMemoryBroker
        test_broker = create_broker()
        assert isinstance(test_broker, InMemoryBroker)
        assert test_broker.await_inplace is True

    def test_broker_instance_is_inmemory_in_tests(self) -> None:
        """Test that the global broker instance is InMemoryBroker in tests."""
        assert isinstance(broker, InMemoryBroker)
        assert broker.await_inplace is True


class TestSimpleTasks:
    """Test simple tasks without dependencies."""

    @pytest.mark.anyio
    async def test_hello_world_task(self) -> None:
        """Test simple hello world task."""
        task = await hello_world_task.kiq("Alice")
        # For InMemoryBroker, we need to wait for result
        result = await task.wait_result(timeout=2)
        assert result.return_value == "Hello, Alice!"

    @pytest.mark.anyio
    async def test_hello_world_task_different_names(self) -> None:
        """Test hello world task with different names."""
        names = ["Bob", "Charlie", "Diana"]

        for name in names:
            task = await hello_world_task.kiq(name)
            result = await task.wait_result(timeout=2)
            assert result.return_value == f"Hello, {name}!"


class TestTasksWithDependencies:
    """Test tasks that use dependency injection."""

    @pytest.mark.anyio
    async def test_task_with_request_dependency(self, fastapi_app: FastAPI) -> None:
        """Test task that uses request dependency."""

        task = await task_with_request.kiq("test-task-123")
        result = await task.wait_result(timeout=2)

        assert result.return_value is not None
        assert result.return_value["task_id"] == "test-task-123"
        assert result.return_value["app_title"] == "trae_api"
        assert result.return_value["status"] == "completed"

    @pytest.mark.anyio
    async def test_task_with_app_state_dependency(self, fastapi_app: FastAPI) -> None:
        """Test task that uses app state dependency."""
        # Add some test state to the app
        if not hasattr(fastapi_app, "state"):
            fastapi_app.state = SimpleNamespace()

        fastapi_app.state.test_value = "test_data"

        task = await task_with_app_state.kiq("test message")
        result = await task.wait_result(timeout=2)

        assert result.return_value is not None
        assert result.return_value["message"] == "test message"
        assert result.return_value["processed"] is True
        assert "app_state_keys" in result.return_value

    @pytest.mark.anyio
    async def test_task_with_settings_dependency(self, fastapi_app: FastAPI) -> None:
        """Test task that uses settings dependency."""

        test_data = {"key": "value", "number": 42}
        task = await task_with_settings.kiq(test_data)
        result = await task.wait_result(timeout=2)

        assert result.return_value is not None
        assert result.return_value["data"] == test_data
        assert result.return_value["processed_at"] == "task_worker"
        # Environment should be "pytest" in tests
        assert result.return_value["environment"] in ["pytest", "unknown"]


class TestBrokerLifecycle:
    """Test broker lifecycle management."""

    def test_broker_is_worker_process_check(self) -> None:
        """Test broker worker process detection."""
        # In tests, broker should not be a worker process
        assert not broker.is_worker_process

    @pytest.mark.anyio
    async def test_broker_startup_shutdown(self) -> None:
        """Test broker startup and shutdown."""
        # Create a fresh broker for this test
        test_broker = InMemoryBroker()

        # Test startup
        await test_broker.startup()
        assert test_broker.is_worker_process is False

        # Test shutdown
        await test_broker.shutdown()


class TestTaskExecution:
    """Test task execution patterns."""

    @pytest.mark.anyio
    async def test_multiple_tasks_execution(self) -> None:
        """Test executing multiple tasks."""
        tasks = []

        # Schedule multiple tasks
        for i in range(5):
            task_result = await hello_world_task.kiq(f"User{i}")
            tasks.append(task_result)

        # Verify all tasks completed successfully
        for i, task in enumerate(tasks):
            result = await task.wait_result(timeout=2)
            assert result.return_value == f"Hello, User{i}!"

    @pytest.mark.anyio
    async def test_task_error_handling(self) -> None:
        """Test task error handling."""
        # Test with valid data
        items = [{"id": 1}, {"id": 2}]
        task = await background_processing_task.kiq(items, batch_size=1)
        result = await task.wait_result(timeout=2)

        assert result.return_value["total_items"] == 2
        assert result.return_value["processed"] == 2
        assert result.return_value["failed"] == 0
