"""
Example Taskiq tasks with proper dependency injection.

Following best practices:
- Use TaskiqDepends for dependency injection
- Use Annotated for better type hinting
- Provide meaningful task examples
- Integrated metrics and logging
"""

import asyncio
from typing import Annotated, Any, Dict, List

from fastapi import Request
from taskiq import TaskiqDepends

from trae_api.core.dependencies import AppState, Settings
from trae_api.core.logging import get_task_logger
from trae_api.tasks.broker import broker
from trae_api.tasks.metrics import task_metrics_context


@broker.task
async def hello_world_task(name: str) -> str:
    """
    Simple task without dependencies.

    Args:
        name: Name to greet

    Returns:
        str: Greeting message
    """
    logger = get_task_logger("hello_world_task")
    logger.info("Starting hello world task", name=name)

    await asyncio.sleep(0.1)  # Simulate some work
    result = f"Hello, {name}!"

    logger.info("Hello world task completed", name=name, result=result)
    return result


@broker.task
async def task_with_app_state(
    message: str,
    app_state: AppState,
) -> Dict[str, Any]:
    """
    Task that uses application state dependency.

    Args:
        message: Message to process
        app_state: Application state (injected)

    Returns:
        dict: Result with app state info
    """
    return {
        "message": message,
        "processed": True,
        "app_state_keys": list(app_state.keys()),
    }


@broker.task
async def task_with_settings(
    data: Dict[str, Any],
    settings: Settings,
) -> Dict[str, Any]:
    """
    Task that uses application settings dependency.

    Args:
        data: Data to process
        settings: Application settings (injected)

    Returns:
        dict: Processed data with environment info
    """
    return {
        "data": data,
        "environment": getattr(settings, "environment", "unknown"),
        "processed_at": "task_worker",
    }


@broker.task
async def task_with_request(
    task_id: str,
    request: Annotated[Request, TaskiqDepends()],
) -> Dict[str, Any]:
    """
    Task that directly uses FastAPI request dependency.

    Note: The request object in tasks is NOT the actual HTTP request,
    but a worker-wide singleton that provides access to the app instance.

    Args:
        task_id: Task identifier
        request: FastAPI request object (injected)

    Returns:
        dict: Task result with app info
    """
    app_title = getattr(request.app, "title", "Unknown App")
    app_version = getattr(request.app, "version", "Unknown Version")

    return {
        "task_id": task_id,
        "app_title": app_title,
        "app_version": app_version,
        "status": "completed",
    }


@broker.task
async def background_processing_task(
    items: List[Dict[str, Any]],
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Example of a more complex background processing task with integrated metrics.

    Args:
        items: List of items to process
        batch_size: Number of items to process in each batch

    Returns:
        dict: Processing results
    """
    # Use the metrics context manager for automatic metrics collection and logging
    with task_metrics_context("background_processing_task") as logger:
        logger.info("Processing started", total_items=len(items), batch_size=batch_size)

        processed_count = 0
        failed_count = 0

        # Process items in batches
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            batch_number = (i // batch_size) + 1

            logger.info("Processing batch", batch_number=batch_number, batch_size=len(batch))

            for item_idx, _item in enumerate(batch):
                try:
                    # Simulate processing
                    await asyncio.sleep(0.01)
                    processed_count += 1
                except Exception as exc:
                    failed_count += 1
                    logger.warning(
                        "Item processing failed",
                        batch_number=batch_number,
                        item_index=item_idx,
                        error=str(exc),
                    )

        result = {
            "total_items": len(items),
            "processed": processed_count,
            "failed": failed_count,
            "batch_size": batch_size,
        }

        logger.info("Processing completed", **result)
        return result
