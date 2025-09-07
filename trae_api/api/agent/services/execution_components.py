"""Production-grade execution components for agent service.

Following Meta/PyTorch patterns for clean architecture and separation of concerns.
"""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import structlog
from trae_agent.schemas.requests import RunRequest
from trae_api.core.metrics import get_metrics

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionContext:
    """Encapsulates execution state and metadata.
    
    This class manages the lifecycle of a single agent execution,
    tracking status, metrics, and metadata throughout the process.
    """
    
    execution_id: str
    request: RunRequest
    status: str = "initializing"
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None
    correlation_id: Optional[str] = None
    task_hash: Optional[str] = None
    
    def update_status(self, status: str) -> None:
        """Update execution status with timestamp."""
        self.status = status
        if status in ("completed", "failed", "timeout"):
            self.end_time = datetime.now(timezone.utc)
    
    def record_metric(self, metric_name: str, value: Any) -> None:
        """Record a metric for this execution."""
        self.metrics[metric_name] = value
    
    @property
    def duration_seconds(self) -> float:
        """Calculate execution duration in seconds."""
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for logging/serialization."""
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "provider": self.request.provider,
            "model": self.request.model,
            "task_length": len(self.request.task) if self.request.task else 0,
            "metrics": self.metrics,
            "correlation_id": self.correlation_id,
            "task_hash": self.task_hash,
        }


class ResourceCoordinator:
    """Manages temp directories, cleanup, and resource lifecycle.
    
    Centralized resource management following Meta's production patterns
    for resource acquisition, tracking, and cleanup.
    """
    
    def __init__(self, temp_dir_manager, cleanup_scheduler):
        self.temp_dir_manager = temp_dir_manager
        self.cleanup_scheduler = cleanup_scheduler
        self.active_resources: Dict[str, Any] = {}
        self.metrics = get_metrics()
    
    @asynccontextmanager
    async def acquire_resources(self, execution_id: str, working_dir: Optional[str] = None):
        """Acquire resources for execution with automatic cleanup.
        
        Args:
            execution_id: Unique execution identifier
            working_dir: Optional working directory override
            
        Yields:
            Tuple of (temp_dir, working_dir) paths
        """
        temp_dir = None
        try:
            # Create temp directory
            temp_dir = self.temp_dir_manager.create_temp_dir()
            
            # Determine working directory
            if working_dir and Path(working_dir).exists():
                work_dir = Path(working_dir)
            else:
                work_dir = temp_dir / "workspace"
                work_dir.mkdir(exist_ok=True)
            
            # Track resources
            self.active_resources[execution_id] = {
                "temp_dir": temp_dir,
                "working_dir": work_dir,
                "acquired_at": datetime.now(timezone.utc)
            }
            
            yield temp_dir, work_dir
            
        finally:
            # Schedule cleanup
            if temp_dir:
                await self.cleanup_scheduler.schedule_cleanup(
                    f"temp_dir_{execution_id}",
                    lambda: self._cleanup_temp_dir(temp_dir, execution_id),
                    delay_seconds=300.0
                )
            
            # Remove from active tracking
            self.active_resources.pop(execution_id, None)
    
    async def _cleanup_temp_dir(self, temp_dir: Path, execution_id: str) -> None:
        """Clean up temporary directory with safety checks."""
        try:
            if temp_dir.exists() and str(temp_dir).startswith("/tmp"):
                self.temp_dir_manager.cleanup_temp_dir(temp_dir)
                logger.debug(
                    "Cleaned up temp directory",
                    execution_id=execution_id,
                    temp_dir=str(temp_dir)
                )
        except Exception as e:
            logger.warning(
                "Failed to cleanup temp directory",
                execution_id=execution_id,
                error=str(e)
            )
    
    async def emergency_cleanup(self, execution_id: str) -> None:
        """Perform emergency cleanup for an execution."""
        resources = self.active_resources.get(execution_id)
        if resources and resources.get("temp_dir"):
            await self._cleanup_temp_dir(resources["temp_dir"], execution_id)


class TelemetryRecorder:
    """Unified telemetry recording with OpenTelemetry integration.
    
    Consolidates all telemetry operations to reduce duplication
    and ensure consistent monitoring across the service.
    """
    
    def __init__(self, tracer=None):
        self.metrics = get_metrics()
        self.tracer = tracer
        self.logger = structlog.get_logger(__name__)
    
    def record_phase(self, phase: str, context: ExecutionContext) -> None:
        """Record phase transition with telemetry."""
        # Update metrics
        self.metrics.record_execution_phase(
            execution_id=context.execution_id,
            phase=phase,
            provider=context.request.provider,
            model=context.request.model
        )
        
        # Log phase transition (essential telemetry only)
        self.logger.info(
            f"Execution phase: {phase}",
            execution_id=context.execution_id,
            phase=phase,
            status=context.status,
            duration_seconds=context.duration_seconds,
            provider=context.request.provider,
            model=context.request.model,
            task_length=len(context.request.task) if context.request.task else 0,
            correlation_id=context.correlation_id,
            task_hash=context.task_hash
        )
    
    def record_error(self, error: Exception, context: ExecutionContext, 
                    error_type: str = "execution_error") -> None:
        """Record error with full context preservation."""
        # Update metrics
        self.metrics.record_execution_error(
            execution_id=context.execution_id,
            error_type=error_type,
            error_code=getattr(error, 'status_code', 500),
            provider=context.request.provider,
            model=context.request.model
        )
        
        # Log with full error context
        self.logger.error(
            "Execution error",
            execution_id=context.execution_id,
            error_type=error_type,
            error_message=str(error),
            status=context.status,
            duration_seconds=context.duration_seconds,
            provider=context.request.provider,
            model=context.request.model,
            task_length=len(context.request.task) if context.request.task else 0,
            correlation_id=context.correlation_id,
            task_hash=context.task_hash,
            exc_info=True
        )
    
    def record_completion(self, result: Any, context: ExecutionContext) -> None:
        """Record successful completion with metrics."""
        # Update metrics
        self.metrics.record_execution_complete(
            execution_id=context.execution_id,
            provider=context.request.provider,
            model=context.request.model,
            success=True
        )
        
        # Log completion
        self.logger.info(
            "Execution completed",
            execution_id=context.execution_id,
            duration_seconds=context.duration_seconds,
            success=True,
            status=context.status,
            provider=context.request.provider,
            model=context.request.model,
            task_length=len(context.request.task) if context.request.task else 0,
            correlation_id=context.correlation_id,
            task_hash=context.task_hash
        )


@contextmanager
def preserve_error_context(operation_name: str, execution_id: str):
    """Context manager that preserves detailed error information.
    
    Following Meta's pattern for comprehensive error handling
    while maintaining all debugging context.
    """
    from trae_api.api.agent.services.executor import AgentExecutionError
    
    try:
        yield
    except AgentExecutionError:
        # Already handled with full context, re-raise as-is
        raise
    except asyncio.TimeoutError as e:
        # Preserve timeout details for debugging
        raise AgentExecutionError(
            f"{operation_name} timeout",
            error_type="timeout",
            details={
                "execution_id": execution_id,
                "operation": operation_name,
                "error_class": type(e).__name__
            }
        ) from e
    except asyncio.CancelledError as e:
        # Preserve cancellation context
        raise AgentExecutionError(
            f"{operation_name} cancelled",
            error_type="cancelled",
            details={
                "execution_id": execution_id,
                "operation": operation_name
            }
        ) from e
    except Exception as e:
        # Preserve full exception chain and context
        raise AgentExecutionError(
            f"{operation_name} failed: {str(e)}",
            error_type="internal_error",
            details={
                "execution_id": execution_id,
                "operation": operation_name,
                "original_error": str(e),
                "error_class": type(e).__name__
            }
        ) from e