import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

import structlog
from opentelemetry.trace import INVALID_SPAN, INVALID_SPAN_CONTEXT, get_current_span
from pythonjsonlogger import jsonlogger

from trae_api.core.settings import settings

# Context variables for correlation tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
execution_id_var: ContextVar[Optional[str]] = ContextVar('execution_id', default=None)
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
execution_phase_var: ContextVar[Optional[str]] = ContextVar('execution_phase', default=None)


def get_trace_context() -> Dict[str, str]:
    """Get the current OpenTelemetry trace and span IDs."""
    span = get_current_span()
    if span == INVALID_SPAN:
        return {"trace_id": "0", "span_id": "0"}

    span_context = span.get_span_context()
    if span_context == INVALID_SPAN_CONTEXT:
        return {"trace_id": "0", "span_id": "0"}

    return {
        "trace_id": format(span_context.trace_id, "032x"),
        "span_id": format(span_context.span_id, "016x"),
    }


def add_trace_context(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add OpenTelemetry trace context to the log record."""
    event_dict.update(get_trace_context())
    return event_dict


def add_correlation_context(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add correlation IDs and execution context to log records."""
    
    # Add correlation ID if available
    correlation_id = correlation_id_var.get()
    if correlation_id:
        event_dict['correlation_id'] = correlation_id
    
    # Add execution ID if available
    execution_id = execution_id_var.get()
    if execution_id:
        event_dict['execution_id'] = execution_id
        
    # Add request ID if available
    request_id = request_id_var.get()
    if request_id:
        event_dict['request_id'] = request_id
        
    # Add execution phase if available
    execution_phase = execution_phase_var.get()
    if execution_phase:
        event_dict['execution_phase'] = execution_phase
    
    return event_dict


def add_service_context(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add service context to the log record."""
    event_dict.update(
        {
            "service": "trae_api",
            "version": "0.1.0",
            "environment": settings.environment,
        },
    )
    return event_dict


def configure_structlog() -> None:
    """Configure structlog and standard library logging."""
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    if settings.environment == "development":
        processors = [
            structlog.contextvars.merge_contextvars,
            add_service_context,
            add_trace_context,
            add_correlation_context,
            structlog.processors.add_log_level,
            timestamper,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            add_service_context,
            add_trace_context,
            add_correlation_context,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.value.upper()),
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    handler = logging.StreamHandler(sys.stdout)
    if settings.environment != "development":
        # Use a simpler format for JsonFormatter
        # Trace/span IDs will be added by structlog processors, not here
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
        )
        handler.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.value.upper()),
        handlers=[handler],
        force=True,
    )
