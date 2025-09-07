"""
Centralized logging factory for consistent structured logging.

This module provides a unified interface for logging across the entire application,
ensuring consistent structured logging with proper context propagation.

Following Meta/Apache engineering standards:
- Single source of truth for logger creation
- Consistent structured logging format
- Context propagation support
- OpenTelemetry integration
"""

import uuid
from typing import Optional

import structlog
from structlog.stdlib import BoundLogger
from .structlog import (
    correlation_id_var, 
    execution_id_var, 
    request_id_var, 
    execution_phase_var
)


def get_logger(name: Optional[str] = None) -> BoundLogger:
    """
    Central logger factory - always returns structured logger with context.

    This factory ensures all loggers across the application use the same
    structured logging configuration with consistent context fields.

    Args:
        name: Logger name, typically __name__ or module-specific identifier

    Returns:
        BoundLogger: Configured structured logger with context

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Task started", task_id="abc123", operation="process")
    """
    # Get the base structured logger
    logger = structlog.get_logger()

    # Bind additional context if name provided
    if name:
        logger = logger.bind(logger_name=name)

    return logger


def get_task_logger(task_name: str, task_id: Optional[str] = None) -> BoundLogger:
    """
    Specialized logger factory for TaskIQ tasks with task-specific context.

    Args:
        task_name: Name of the task (e.g., "background_processing_task")
        task_id: Unique task identifier

    Returns:
        BoundLogger: Logger with task context pre-bound

    Example:
        >>> logger = get_task_logger("process_items", "task-123")
        >>> logger.info("Processing started", items_count=100)
    """
    logger = get_logger(f"tasks.{task_name}")

    # Bind task-specific context
    context = {"task_name": task_name}
    if task_id:
        context["task_id"] = task_id

    return logger.bind(**context)


def get_api_logger(endpoint: str) -> BoundLogger:
    """
    Specialized logger factory for API endpoints.

    Args:
        endpoint: API endpoint identifier (e.g., "tasks.submit")

    Returns:
        structlog.BoundLogger: Logger with API context pre-bound

    Example:
        >>> logger = get_api_logger("tasks.status")
        >>> logger.info("Status check requested", task_id="abc123")
    """
    return get_logger(f"api.{endpoint}").bind(component="api")


def generate_correlation_id() -> str:
    """Generate a unique correlation ID."""
    return str(uuid.uuid4())[:8]  # Short ID for readability


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())[:12]  # Medium length for request tracking


def set_correlation_context(
    correlation_id: Optional[str] = None,
    execution_id: Optional[str] = None,
    request_id: Optional[str] = None,
    execution_phase: Optional[str] = None
):
    """Set correlation context for the current task."""
    
    if correlation_id:
        correlation_id_var.set(correlation_id)
    
    if execution_id:
        execution_id_var.set(execution_id)
        
    if request_id:
        request_id_var.set(request_id)
        
    if execution_phase:
        execution_phase_var.set(execution_phase)


def get_correlation_context() -> dict[str, Optional[str]]:
    """Get current correlation context."""
    return {
        'correlation_id': correlation_id_var.get(),
        'execution_id': execution_id_var.get(),
        'request_id': request_id_var.get(),
        'execution_phase': execution_phase_var.get()
    }


def get_execution_logger(execution_id: str) -> BoundLogger:
    """
    Specialized logger factory for agent execution with execution-specific context.

    Args:
        execution_id: Unique execution identifier

    Returns:
        BoundLogger: Logger with execution context pre-bound

    Example:
        >>> logger = get_execution_logger("exec-123")
        >>> logger.info("Starting execution phase", phase="initialization")
    """
    # Set execution context
    execution_id_var.set(execution_id)
    
    return get_logger(f"execution.{execution_id}").bind(
        component="executor",
        execution_id=execution_id
    )
