"""Real tests for production-grade resource management."""

import asyncio
import pytest
from pathlib import Path

from trae_api.core.resources import CleanupScheduler, monitored_endpoint, managed_resource
from fastapi import HTTPException


class TestCleanupScheduler:
    """Test the production cleanup scheduler."""
    
    @pytest.mark.asyncio
    async def test_schedule_cleanup(self):
        """Test that cleanup is scheduled and executed."""
        scheduler = CleanupScheduler()
        cleanup_executed = False
        
        async def cleanup_func():
            nonlocal cleanup_executed
            cleanup_executed = True
        
        # Schedule with short delay
        await scheduler.schedule_cleanup("test-resource", cleanup_func, 0.1)
        
        # Verify task is scheduled
        assert "test-resource" in scheduler.scheduled_tasks
        assert len(scheduler.scheduled_tasks) == 1
        
        # Wait for cleanup to execute
        await asyncio.sleep(0.2)
        
        # Verify cleanup was executed
        assert cleanup_executed
        assert "test-resource" not in scheduler.scheduled_tasks
        assert "test-resource" in scheduler.completed_cleanups
    
    @pytest.mark.asyncio
    async def test_cancel_cleanup(self):
        """Test that cleanup can be cancelled."""
        scheduler = CleanupScheduler()
        cleanup_executed = False
        
        async def cleanup_func():
            nonlocal cleanup_executed
            cleanup_executed = True
        
        # Schedule with longer delay
        await scheduler.schedule_cleanup("test-resource", cleanup_func, 1.0)
        
        # Cancel it
        cancelled = await scheduler.cancel_cleanup("test-resource")
        assert cancelled
        
        # Wait to ensure it doesn't execute
        await asyncio.sleep(0.1)
        
        # Verify cleanup was not executed
        assert not cleanup_executed
        assert "test-resource" not in scheduler.scheduled_tasks
    
    @pytest.mark.asyncio
    async def test_cleanup_error_handling(self):
        """Test that cleanup handles errors gracefully."""
        scheduler = CleanupScheduler()
        
        async def failing_cleanup():
            raise ValueError("Cleanup failed")
        
        # Schedule cleanup that will fail
        await scheduler.schedule_cleanup("failing-resource", failing_cleanup, 0.1)
        
        # Wait for it to execute and fail
        await asyncio.sleep(0.2)
        
        # Verify it's no longer scheduled (even though it failed)
        assert "failing-resource" not in scheduler.scheduled_tasks
        # It should not be in completed since it failed
        assert "failing-resource" not in scheduler.completed_cleanups
    
    @pytest.mark.asyncio
    async def test_scheduler_shutdown(self):
        """Test graceful shutdown cancels all tasks."""
        scheduler = CleanupScheduler()
        
        # Schedule multiple cleanups
        for i in range(5):
            await scheduler.schedule_cleanup(
                f"resource-{i}",
                lambda: asyncio.sleep(10),  # Long running
                1.0
            )
        
        assert len(scheduler.scheduled_tasks) == 5
        
        # Shutdown should cancel all
        await scheduler.shutdown()
        
        assert len(scheduler.scheduled_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test scheduler statistics."""
        scheduler = CleanupScheduler()
        
        # Schedule some cleanups
        await scheduler.schedule_cleanup("task1", lambda: None, 10)
        await scheduler.schedule_cleanup("task2", lambda: None, 10)
        
        stats = scheduler.get_stats()
        
        assert stats["pending_cleanups"] == 2
        assert stats["completed_cleanups"] == 0
        assert "task1" in stats["active_tasks"]
        assert "task2" in stats["active_tasks"]


class TestMonitoredEndpoint:
    """Test the monitored endpoint decorator."""
    
    @pytest.mark.asyncio
    async def test_successful_operation(self):
        """Test monitoring of successful operation."""
        call_count = 0
        
        @monitored_endpoint("test_operation", record_metrics=False)
        async def test_endpoint():
            nonlocal call_count
            call_count += 1
            return {"status": "success"}
        
        result = await test_endpoint()
        
        assert result == {"status": "success"}
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test that timeout is properly handled."""
        
        @monitored_endpoint("slow_operation", record_metrics=False, timeout_seconds=0.1)
        async def slow_endpoint():
            await asyncio.sleep(1.0)
            return {"status": "success"}
        
        with pytest.raises(HTTPException) as exc_info:
            await slow_endpoint()
        
        assert exc_info.value.status_code == 408
        assert exc_info.value.detail["error"] == "timeout"
    
    @pytest.mark.asyncio
    async def test_http_exception_passthrough(self):
        """Test that HTTP exceptions are passed through."""
        
        @monitored_endpoint("failing_operation", record_metrics=False)
        async def failing_endpoint():
            raise HTTPException(status_code=404, detail="Not found")
        
        with pytest.raises(HTTPException) as exc_info:
            await failing_endpoint()
        
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Not found"
    
    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self):
        """Test that unexpected errors are converted to 500."""
        
        @monitored_endpoint("error_operation", record_metrics=False)
        async def error_endpoint():
            raise ValueError("Unexpected error")
        
        with pytest.raises(HTTPException) as exc_info:
            await error_endpoint()
        
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["error"] == "internal_error"


class TestManagedResource:
    """Test the managed resource context manager."""
    
    @pytest.mark.asyncio
    async def test_cleanup_scheduled_on_exit(self):
        """Test that cleanup is scheduled when exiting context."""
        cleanup_scheduled = False
        
        async def cleanup_func():
            nonlocal cleanup_scheduled
            cleanup_scheduled = True
        
        async with managed_resource("test-resource", cleanup_func, 0.1):
            pass  # Just enter and exit
        
        # Wait for cleanup
        await asyncio.sleep(0.2)
        
        assert cleanup_scheduled
    
    @pytest.mark.asyncio
    async def test_cleanup_on_exception(self):
        """Test that cleanup is scheduled even on exception."""
        cleanup_scheduled = False
        
        async def cleanup_func():
            nonlocal cleanup_scheduled
            cleanup_scheduled = True
        
        with pytest.raises(ValueError):
            async with managed_resource("test-resource", cleanup_func, 0.1):
                raise ValueError("Test error")
        
        # Wait for cleanup
        await asyncio.sleep(0.2)
        
        assert cleanup_scheduled