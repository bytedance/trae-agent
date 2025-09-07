"""Task management endpoints."""

from typing import Any, Dict, List, Literal, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from trae_api.core.logging import get_api_logger
from trae_api.tasks.broker import broker
from trae_api.tasks.examples import background_processing_task

router = APIRouter(tags=["tasks"])


class TaskSubmissionResponse(BaseModel):
    """Task submission response."""

    task_id: str
    status: Literal["submitted"]
    message: str = "Task submitted successfully"


class TaskStatusResponse(BaseModel):
    """Task status response."""

    task_id: str
    status: Literal["pending", "running", "completed", "failed"]
    result: Dict[str, Any] | str | None = None
    error: str | None = None


class ProcessingTaskRequest(BaseModel):
    """Background processing task request."""

    items: List[Dict[str, Any]]
    batch_size: int = 10


@router.post("/process", response_model=TaskSubmissionResponse)
async def submit_background_processing(
    request: ProcessingTaskRequest,
) -> TaskSubmissionResponse:
    """
    Submit a background processing task.

    Args:
        request: Processing task request

    Returns:
        TaskSubmissionResponse: Task submission confirmation
    """
    logger = get_api_logger("tasks.submit")

    logger.info(
        "Task submission started",
        task_name="background_processing_task",
        items_count=len(request.items),
        batch_size=request.batch_size,
    )

    try:
        task = await background_processing_task.kiq(
            request.items,
            request.batch_size,
        )

        logger.info(
            "Task submitted successfully",
            task_id=task.task_id,
            task_name="background_processing_task",
            items_count=len(request.items),
        )

        return TaskSubmissionResponse(
            task_id=task.task_id,
            status="submitted",
            message=f"Processing task submitted with {len(request.items)} items",
        )
    except Exception as e:
        logger.error(
            "Task submission failed",
            task_name="background_processing_task",
            items_count=len(request.items),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit task: {e!s}",
        ) from e


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get the status of a background processing task.

    Args:
        task_id: Task identifier

    Returns:
        TaskStatusResponse: Current task status and result if completed
    """
    logger = get_api_logger("tasks.status")
    logger.info("Task status check requested", task_id=task_id)

    try:
        # Check if broker has result backend configured
        if not hasattr(broker, "result_backend") or not broker.result_backend:
            return TaskStatusResponse(
                task_id=task_id,
                status="pending",
                result=None,
                error="Task status tracking requires result backend configuration",
            )

        # Get result from SQLite backend
        try:
            task_result = await broker.result_backend.get_result(task_id)

            if task_result is None:
                return TaskStatusResponse(
                    task_id=task_id,
                    status="pending",
                    result=None,
                    error=None,
                )

            # Determine status based on result
            if task_result.is_err:
                status: Literal["pending", "running", "completed", "failed"] = "failed"
                error = str(task_result.error) if task_result.error else "Task failed with unknown error"
                result = None
            else:
                status = "completed"
                error = None
                result = cast(Dict[str, Any], task_result.return_value)

            return TaskStatusResponse(
                task_id=task_id,
                status=status,
                result=result,
                error=error,
            )

        except Exception:
            # Task not found or backend error - return pending status
            return TaskStatusResponse(
                task_id=task_id,
                status="pending",
                result=None,
                error=None,
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task status: {e!s}",
        ) from e
