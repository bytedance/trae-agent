"""
TaskIQ metrics collection utilities.

Provides convenient functions for recording TaskIQ task metrics
using the integrated AdvancedMetricsMiddleware infrastructure.
"""

import logging
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from trae_api.core.logging import get_task_logger
from trae_api.core.middleware.advanced_metrics import get_metrics_middleware


def record_task_metrics(task_name: str, duration: float, status: str = "success") -> None:
    """
    Record TaskIQ task execution metrics.

    Args:
        task_name: Name of the executed task
        duration: Task execution duration in seconds
        status: Task status ("success" or "error")
    """
    middleware = get_metrics_middleware()
    if middleware:
        middleware.record_taskiq_metrics(task_name, duration, status)


def record_task_completion(task_name: str, duration: float) -> None:
    """Record successful task completion metrics."""
    record_task_metrics(task_name, duration, "success")


def record_task_error(task_name: str, duration: float) -> None:
    """Record task error metrics."""
    record_task_metrics(task_name, duration, "error")


@contextmanager
def task_metrics_context(task_name: str, task_id: Optional[str] = None) -> Iterator[logging.Logger]:
    """
    Context manager for automatic TaskIQ metrics collection.

    Automatically records task duration and status based on success/failure.
    Also provides structured logging for task lifecycle.

    Args:
        task_name: Name of the task being executed
        task_id: Optional task ID for correlation

    Example:
        >>> with task_metrics_context("process_items", "task-123") as logger:
        ...     logger.info("Processing started", items_count=100)
        ...     # ... task execution ...
        ...     logger.info("Processing completed")
    """
    start_time = time.time()
    logger = get_task_logger(task_name, task_id)

    try:
        logger.info("Task execution started", task_name=task_name, task_id=task_id)
        yield logger

        # Record success metrics
        duration = time.time() - start_time
        record_task_completion(task_name, duration)
        logger.info("Task execution completed", task_name=task_name, task_id=task_id, duration_seconds=duration)

    except Exception as exc:
        # Record error metrics
        duration = time.time() - start_time
        record_task_error(task_name, duration)
        logger.error(
            "Task execution failed",
            task_name=task_name,
            task_id=task_id,
            duration_seconds=duration,
            error=str(exc),
            exc_info=True,
        )
        raise
