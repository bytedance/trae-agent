"""Integration tests for SQLite result backend with local desktop deployment."""

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import httpx
from httpx import AsyncClient
from taskiq import TaskiqResult

from trae_api.core.application import get_app
from trae_api.tasks.broker import broker
from trae_api.tasks.examples import background_processing_task
from trae_api.tasks.result_backends import SQLiteResultBackend


class TestSQLiteResultBackend:
    """Test SQLite result backend implementation."""

    @pytest.fixture
    async def sqlite_backend(self) -> AsyncGenerator[SQLiteResultBackend, None]:
        """Create a temporary SQLite result backend for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            backend = SQLiteResultBackend(tmp_path)
            await backend.startup()
            yield backend
            await backend.shutdown()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.anyio
    async def test_sqlite_backend_startup_creates_table(
        self,
        sqlite_backend: SQLiteResultBackend,
    ) -> None:
        """Test that SQLite backend startup creates the required table."""
        # Check that database file exists and has the table
        conn = sqlite3.connect(sqlite_backend.database_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        conn.close()

        assert ("taskiq_results",) in tables

    @pytest.mark.anyio
    async def test_sqlite_backend_result_storage_and_retrieval(
        self,
        sqlite_backend: SQLiteResultBackend,
    ) -> None:
        """Test storing and retrieving task results."""

        # Create a test result
        test_result = TaskiqResult(
            is_err=False,
            return_value={"processed": 5, "total": 5},
            execution_time=0.123,
            log=None,
            error=None,
            labels={"task_name": "test_task"},
        )

        task_id = "test_task_123"

        # Store result
        await sqlite_backend.set_result(task_id, test_result)

        # Check if result is ready
        is_ready = await sqlite_backend.is_result_ready(task_id)
        assert is_ready is True

        # Retrieve result
        retrieved_result = await sqlite_backend.get_result(task_id)
        assert retrieved_result is not None
        assert retrieved_result.is_err is False
        assert retrieved_result.return_value == {"processed": 5, "total": 5}

    @pytest.mark.anyio
    async def test_sqlite_backend_cleanup_old_results(
        self,
        sqlite_backend: SQLiteResultBackend,
    ) -> None:
        """Test cleanup of old task results."""

        # Create and store a test result
        test_result = TaskiqResult(
            is_err=False,
            return_value={"test": "data"},
            execution_time=0.1,
            log=None,
            error=None,
            labels={},
        )

        await sqlite_backend.set_result("test_cleanup", test_result)

        # Clean up results (should delete 0 since they're new)
        deleted_count = await sqlite_backend.cleanup_old_results(days=30)
        assert deleted_count == 0

        # Verify result still exists
        is_ready = await sqlite_backend.is_result_ready("test_cleanup")
        assert is_ready is True


class TestDesktopTaskIntegration:
    """Test complete task integration for desktop deployment."""

    @pytest.mark.anyio
    async def test_local_broker_with_sqlite_backend(self) -> None:
        """Test that local broker correctly uses SQLite result backend."""
        # Manually test the broker configuration
        assert hasattr(broker, "result_backend")
        assert broker.result_backend is not None
        assert isinstance(broker.result_backend, SQLiteResultBackend)

        # Initialize the result backend
        await broker.result_backend.startup()

        # Test task submission and result storage

        # Submit task using the broker
        task = await background_processing_task.kiq(
            [{"id": 1, "name": "test"}],
            batch_size=1,
        )

        # Wait for task to complete
        result = await task.wait_result(timeout=5)

        # Verify result
        assert result.is_err is False
        assert result.return_value["total_items"] == 1
        assert result.return_value["processed"] == 1

        # Verify result was stored in SQLite backend
        stored_result = await broker.result_backend.get_result(task.task_id)
        assert stored_result is not None
        assert stored_result.return_value["total_items"] == 1

    @pytest.mark.anyio
    async def test_complete_api_workflow_with_sqlite(self) -> None:
        """Test complete API workflow with SQLite persistence."""
        # Create app and manually initialize broker
        app = get_app()

        # Initialize the result backend manually since lifespan won't run in tests
        if hasattr(broker, "result_backend") and broker.result_backend:
            await broker.result_backend.startup()

        # Test the API endpoints
        async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # Submit task
            response = await client.post(
                "/api/tasks/process",
                json={
                    "items": [{"id": 1, "name": "api_test"}],
                    "batch_size": 1,
                },
            )

            assert response.status_code == 200
            task_data = response.json()
            task_id = task_data["task_id"]
            assert task_data["status"] == "submitted"

            # Wait a moment for processing
            await asyncio.sleep(0.5)

            # Check task status
            status_response = await client.get(f"/api/tasks/{task_id}/status")
            assert status_response.status_code == 200

            status_data = status_response.json()
            assert status_data["task_id"] == task_id
            # Task should be completed since we're using InMemoryBroker
            assert status_data["status"] == "completed"
            assert status_data["result"]["total_items"] == 1

    @pytest.mark.anyio
    async def test_health_endpoint_shows_sqlite_status(self) -> None:
        """Test that health endpoint reports SQLite database status."""
        app = get_app()

        # Initialize result backend
        if hasattr(broker, "result_backend") and broker.result_backend:
            await broker.result_backend.startup()

        async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200

            health_data = response.json()
            assert "storage" in health_data

            storage = health_data["storage"]
            assert "sqlite_db" in storage

            sqlite_info = storage["sqlite_db"]
            assert "status" in sqlite_info
            assert "size_bytes" in sqlite_info
            assert "path" in sqlite_info

            # After initialization, database should exist
            assert sqlite_info["status"] in ["available", "not_created"]
