"""End-to-end tests for task endpoints."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status


class TestTaskEndpoints:
    """Test task management endpoints."""

    @pytest.mark.anyio
    async def test_submit_background_processing_task(
        self,
        client: AsyncClient,
        fastapi_app: FastAPI,
    ) -> None:
        """Test submitting a background processing task."""

        test_items = [
            {"id": 1, "name": "item1"},
            {"id": 2, "name": "item2"},
            {"id": 3, "name": "item3"},
        ]

        response = await client.post(
            "/api/tasks/process",
            json={"items": test_items, "batch_size": 2},
        )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["status"] == "submitted"
        assert "task_id" in data
        assert "Processing task submitted with 3 items" in data["message"]

    @pytest.mark.anyio
    async def test_get_task_status(
        self,
        client: AsyncClient,
        fastapi_app: FastAPI,
    ) -> None:
        """Test getting task status."""

        # First submit a task
        test_items = [{"id": 1, "name": "item1"}]

        submit_response = await client.post(
            "/api/tasks/process",
            json={"items": test_items, "batch_size": 1},
        )

        assert submit_response.status_code == status.HTTP_200_OK
        task_id = submit_response.json()["task_id"]

        # Then check status
        status_response = await client.get(f"/api/tasks/{task_id}/status")

        assert status_response.status_code == status.HTTP_200_OK

        status_data = status_response.json()
        assert status_data["task_id"] == task_id
        assert status_data["status"] in ["pending", "running", "completed", "failed"]

    @pytest.mark.anyio
    async def test_task_endpoint_validation(self, client: AsyncClient) -> None:
        """Test task endpoint input validation."""
        # Test invalid request for processing task
        response = await client.post(
            "/api/tasks/process",
            json={},  # Missing required 'items' field
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.anyio
    async def test_multiple_concurrent_task_submissions(
        self,
        client: AsyncClient,
        fastapi_app: FastAPI,
    ) -> None:
        """Test multiple concurrent task submissions."""

        # Execute multiple task submissions concurrently
        async def submit_processing_task(batch_num: int) -> httpx.Response:
            items = [{"id": i + batch_num * 10, "name": f"item{i + batch_num * 10}"} for i in range(2)]
            return await client.post(
                "/api/tasks/process",
                json={"items": items, "batch_size": 1},
            )

        # Run multiple task submissions
        tasks = []
        for i in range(3):
            task = submit_processing_task(i)
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        # Verify all tasks were submitted successfully
        task_ids = []
        for response in responses:
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "submitted"
            assert "task_id" in data
            task_ids.append(data["task_id"])

        # Verify all task IDs are unique
        assert len(set(task_ids)) == len(task_ids)


class TestTaskEndpointErrors:
    """Test error scenarios for task endpoints."""

    @pytest.mark.anyio
    async def test_task_endpoint_with_invalid_json(self, client: AsyncClient) -> None:
        """Test task endpoint with invalid JSON."""
        response = await client.post(
            "/api/tasks/process",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.anyio
    async def test_processing_with_invalid_data(
        self,
        client: AsyncClient,
    ) -> None:
        """Test processing with invalid input."""
        response = await client.post(
            "/api/tasks/process",
            json={
                "items": "not a list",  # Should be a list
                "batch_size": -1,  # Invalid batch size
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.anyio
    async def test_get_status_for_nonexistent_task(
        self,
        client: AsyncClient,
    ) -> None:
        """Test getting status for non-existent task."""
        fake_task_id = "nonexistent-task-123"

        response = await client.get(f"/api/tasks/{fake_task_id}/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["task_id"] == fake_task_id
        assert data["status"] == "pending"  # Should gracefully handle missing tasks
