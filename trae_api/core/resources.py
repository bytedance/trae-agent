"""Production-grade resource management utilities."""

import asyncio
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional, Set
from uuid import uuid4

import structlog
from fastapi import HTTPException, Request

logger = structlog.get_logger(__name__)


class CleanupScheduler:
    """
    Production-grade cleanup scheduler with proper task management.
    
    This replaces ad-hoc asyncio.create_task calls with managed scheduling.
    """
    
    def __init__(self):
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        self.completed_cleanups: Set[str] = set()
        self._lock = asyncio.Lock()
    
    async def schedule_cleanup(
        self, 
        resource_id: str, 
        cleanup_func: Callable, 
        delay_seconds: float = 300.0
    ) -> None:
        """
        Schedule a cleanup task with automatic tracking.
        
        Args:
            resource_id: Unique ID for the resource
            cleanup_func: Async function to call for cleanup
            delay_seconds: Delay before cleanup runs
        """
        async with self._lock:
            # Cancel existing task if any
            if resource_id in self.scheduled_tasks:
                self.scheduled_tasks[resource_id].cancel()
            
            # Create new cleanup task
            task = asyncio.create_task(
                self._run_cleanup(resource_id, cleanup_func, delay_seconds)
            )
            self.scheduled_tasks[resource_id] = task
    
    async def _run_cleanup(
        self, 
        resource_id: str, 
        cleanup_func: Callable, 
        delay_seconds: float
    ) -> None:
        """Execute cleanup after delay."""
        try:
            await asyncio.sleep(delay_seconds)
            await cleanup_func()
            
            async with self._lock:
                self.completed_cleanups.add(resource_id)
                self.scheduled_tasks.pop(resource_id, None)
            
            logger.info(
                "Cleanup completed",
                resource_id=resource_id
            )
        except asyncio.CancelledError:
            logger.debug(
                "Cleanup cancelled",
                resource_id=resource_id
            )
        except Exception as e:
            logger.error(
                "Cleanup failed",
                resource_id=resource_id,
                error=str(e)
            )
            async with self._lock:
                self.scheduled_tasks.pop(resource_id, None)
    
    async def cancel_cleanup(self, resource_id: str) -> bool:
        """Cancel a scheduled cleanup."""
        async with self._lock:
            task = self.scheduled_tasks.pop(resource_id, None)
            if task:
                task.cancel()
                return True
            return False
    
    async def shutdown(self) -> None:
        """Cancel all pending cleanups on shutdown."""
        async with self._lock:
            for task in self.scheduled_tasks.values():
                task.cancel()
            
            # Wait for cancellations to complete
            await asyncio.gather(
                *self.scheduled_tasks.values(),
                return_exceptions=True
            )
            
            self.scheduled_tasks.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        return {
            "pending_cleanups": len(self.scheduled_tasks),
            "completed_cleanups": len(self.completed_cleanups),
            "active_tasks": list(self.scheduled_tasks.keys())
        }


# Global cleanup scheduler instance
_cleanup_scheduler = CleanupScheduler()


def get_cleanup_scheduler() -> CleanupScheduler:
    """Get the global cleanup scheduler instance."""
    return _cleanup_scheduler


# Decorator for monitored endpoints
def monitored_endpoint(
    operation_name: str,
    record_metrics: bool = True,
    timeout_seconds: Optional[float] = None
):
    """
    Decorator for monitoring FastAPI endpoints.
    
    Automatically handles:
    - Request ID generation
    - Duration tracking
    - Request/response size metrics
    - Structured logging
    - Timeout handling
    
    Args:
        operation_name: Name of the operation for logging
        record_metrics: Whether to record metrics
        timeout_seconds: Optional timeout for the operation
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request object
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            # Start timing
            start_time = time.time()
            request_id = str(uuid4())
            
            # Set correlation context
            from trae_api.core.logging import set_correlation_context
            set_correlation_context(request_id=request_id)
            
            # Get metrics instance if needed
            metrics = None
            if record_metrics:
                from trae_api.core.metrics import get_metrics
                metrics = get_metrics()
            
            try:
                # Record request size if we have metrics and request
                if metrics and request:
                    try:
                        # Try to get request body size
                        if hasattr(kwargs.get('request'), 'model_dump_json'):
                            request_size = len(
                                kwargs['request'].model_dump_json().encode('utf-8')
                            )
                            metrics.record_request_size(request_size)
                    except (AttributeError, TypeError, ValueError, UnicodeEncodeError) as e:
                        logger.debug("Failed to record request size", error=str(e))
                
                # Log operation start
                logger.info(
                    f"{operation_name} started",
                    request_id=request_id,
                    operation=operation_name
                )
                
                # Execute with optional timeout
                if timeout_seconds:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=timeout_seconds
                    )
                else:
                    result = await func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Record response size if we have metrics
                if metrics and hasattr(result, 'model_dump_json'):
                    try:
                        response_size = len(
                            result.model_dump_json().encode('utf-8')
                        )
                        metrics.record_response_size(response_size)
                    except (AttributeError, TypeError, ValueError, UnicodeEncodeError) as e:
                        logger.debug("Failed to record response size", error=str(e))
                
                # Log success
                logger.info(
                    f"{operation_name} completed",
                    request_id=request_id,
                    operation=operation_name,
                    duration_ms=duration_ms,
                    success=True
                )
                
                return result
                
            except asyncio.TimeoutError:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"{operation_name} timed out",
                    request_id=request_id,
                    operation=operation_name,
                    duration_ms=duration_ms,
                    timeout_seconds=timeout_seconds
                )
                raise HTTPException(
                    status_code=408,
                    detail={
                        "error": "timeout",
                        "message": f"Operation timed out after {timeout_seconds} seconds",
                        "request_id": request_id
                    }
                )
            except HTTPException:
                # Re-raise HTTP exceptions as-is
                duration_ms = (time.time() - start_time) * 1000
                logger.warning(
                    f"{operation_name} failed",
                    request_id=request_id,
                    operation=operation_name,
                    duration_ms=duration_ms,
                    exc_info=True
                )
                raise
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"{operation_name} error",
                    request_id=request_id,
                    operation=operation_name,
                    duration_ms=duration_ms,
                    error=str(e),
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": "internal_error",
                        "message": "An unexpected error occurred",
                        "request_id": request_id
                    }
                )
        
        return wrapper
    return decorator


@asynccontextmanager
async def managed_resource(
    resource_id: str,
    cleanup_func: Optional[Callable] = None,
    cleanup_delay: float = 300.0,
    resource: Any = None
):
    """
    Context manager for resources with automatic cleanup scheduling.
    
    Usage:
        async with managed_resource(exec_id, cleanup_func, resource=my_resource) as resource:
            # Use resource
            pass
        # Cleanup is automatically scheduled
    """
    try:
        # Yield the provided resource
        yield resource
    finally:
        # Schedule cleanup if function provided
        if cleanup_func:
            scheduler = get_cleanup_scheduler()
            await scheduler.schedule_cleanup(
                resource_id,
                cleanup_func,
                cleanup_delay
            )