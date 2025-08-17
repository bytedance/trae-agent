from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from trae_api.core.config import LogLevel


class BaseLogEntry(BaseModel):
    """Base model for all log entries."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: LogLevel
    message: str
    service: str = "trae_api"
    version: str = "0.1.0"
    environment: str = Field(default="development")


class RequestLogEntry(BaseLogEntry):
    """Log entry for HTTP requests."""

    correlation_id: Union[UUID, str]
    request_id: Union[UUID, str]
    method: str
    path: str
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    duration_ms: Optional[float] = None
    status_code: Optional[int] = None
    response_size_bytes: Optional[int] = None


class TraceLogEntry(BaseLogEntry):
    """Log entry with OpenTelemetry trace context."""

    trace_id: str = "0"
    span_id: str = "0"
    correlation_id: Optional[Union[UUID, str]] = None


class ErrorLogEntry(TraceLogEntry):
    """Log entry for application errors."""

    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class PerformanceLogEntry(BaseLogEntry):
    """Log entry for performance metrics."""

    correlation_id: Optional[Union[UUID, str]] = None
    operation: str
    duration_ms: float
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    context: Optional[Dict[str, Any]] = None
