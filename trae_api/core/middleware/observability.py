"""
Unified observability middleware following Meta/Apache engineering standards.

This middleware consolidates correlation ID management, structured logging,
and basic request metrics into a single high-performance component.

Performance optimization: Reduces 3 middleware calls to 1 per request.
"""

import time
from typing import Awaitable, Callable
from uuid import uuid4

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from trae_api.api.monitoring.middleware_health import register_middleware_health
from trae_api.core.logging.schema import ErrorLogEntry, LogLevel, RequestLogEntry


class UnifiedObservabilityMiddleware(BaseHTTPMiddleware):
    """
    High-performance unified middleware for observability.

    Consolidates:
    - Correlation ID generation and propagation
    - Structured request/response logging
    - Basic request metrics collection
    - Async context management

    Design principles:
    - Single responsibility: All observability concerns
    - Fail-safe: Never breaks application flow
    - Performance: Minimal per-request overhead
    - Maintainable: Clean, readable implementation
    """

    def __init__(self, app: ASGIApp, exclude_paths: list[str] | None = None) -> None:
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/api/health", "/api/metrics"]
        self.logger = structlog.get_logger()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[..., Awaitable[Response]],
    ) -> Response:
        """Process request with unified observability."""
        # Always generate correlation ID for traceability
        correlation_id = self._get_or_create_correlation_id(request)

        # Skip full observability for excluded paths, but still add correlation ID
        if request.url.path in self.exclude_paths:
            response = await call_next(request)
            response.headers["x-correlation-id"] = correlation_id
            return response

        # Initialize observability context
        start_time = time.time()
        request_id = str(uuid4())

        # Bind context for structured logging (async-safe)
        bind_contextvars(
            correlation_id=correlation_id,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=self._safe_get_client_ip(request),
            user_agent=request.headers.get("user-agent", "unknown"),
        )

        # Log request start (structured)
        self._log_request_start(request, correlation_id, request_id)

        try:
            # Process request
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # Add response context
            bind_contextvars(
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Log successful completion
            self._log_request_completion(
                request,
                response,
                duration_ms,
                correlation_id,
                request_id,
            )

            # Add correlation ID to response headers
            response.headers["x-correlation-id"] = correlation_id
            return response

        except Exception as exc:
            # Handle errors without breaking the application
            duration_ms = (time.time() - start_time) * 1000
            self._log_request_error(request, exc, duration_ms, correlation_id, request_id)
            raise

        finally:
            # Clean up context (prevents memory leaks)
            clear_contextvars()

    def _get_or_create_correlation_id(self, request: Request) -> str:
        """Get existing correlation ID or create new one."""
        # Check multiple header variations for compatibility
        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("X-Correlation-ID")
            or request.headers.get("correlation-id")
        )
        return correlation_id or str(uuid4())

    def _safe_get_client_ip(self, request: Request) -> str | None:
        """Safely extract client IP address."""
        try:
            return request.client.host if request.client else None
        except Exception:
            # Fail-safe: Never break on IP extraction
            return None

    def _log_request_start(
        self,
        request: Request,
        correlation_id: str,
        request_id: str,
    ) -> None:
        """Log request start with structured data."""
        try:
            # Use Pydantic schema for validation and structure
            log_entry = RequestLogEntry(
                level=LogLevel.INFO,
                message=f"Request started: {request.method} {request.url.path}",
                correlation_id=correlation_id,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client_ip=self._safe_get_client_ip(request),
                user_agent=request.headers.get("user-agent", "unknown"),
            )

            self.logger.info(
                log_entry.message,
                **log_entry.model_dump(exclude={"message", "timestamp"}),
            )
        except Exception:
            # Fail-safe: Log basic message if schema fails
            self.logger.info(
                f"Request started: {request.method} {request.url.path}",
                correlation_id=correlation_id,
                request_id=request_id,
            )

    def _log_request_completion(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
        correlation_id: str,
        request_id: str,
    ) -> None:
        """Log successful request completion."""
        try:
            log_entry = RequestLogEntry(
                level=LogLevel.INFO,
                message=f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                correlation_id=correlation_id,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client_ip=self._safe_get_client_ip(request),
                user_agent=request.headers.get("user-agent", "unknown"),
                duration_ms=round(duration_ms, 2),
                status_code=response.status_code,
                response_size_bytes=self._safe_get_response_size(response),
            )

            self.logger.info(
                log_entry.message,
                **log_entry.model_dump(exclude={"message", "timestamp"}),
            )
        except Exception:
            # Fail-safe logging
            self.logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                correlation_id=correlation_id,
                duration_ms=round(duration_ms, 2),
            )

    def _log_request_error(
        self,
        request: Request,
        exception: Exception,
        duration_ms: float,
        correlation_id: str,
        request_id: str,
    ) -> None:
        """Log request errors with full context."""
        try:
            log_entry = ErrorLogEntry(
                level=LogLevel.ERROR,
                message=f"Request failed: {request.method} {request.url.path} - {type(exception).__name__}",
                correlation_id=correlation_id,
                trace_id="0",  # Will be populated by trace processor
                span_id="0",  # Will be populated by trace processor
                exception_type=type(exception).__name__,
                exception_message=str(exception),
                context={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": self._safe_get_client_ip(request),
                    "duration_ms": round(duration_ms, 2),
                    "user_agent": request.headers.get("user-agent", "unknown"),
                },
            )

            self.logger.error(
                log_entry.message,
                **log_entry.model_dump(exclude={"message", "timestamp"}),
                exc_info=True,  # Include stack trace
            )
        except Exception:
            # Ultimate fail-safe
            self.logger.error(
                f"Request failed: {request.method} {request.url.path}",
                correlation_id=correlation_id,
                exception_type=type(exception).__name__,
                exception_message=str(exception),
                exc_info=True,
            )

    def _safe_get_response_size(self, response: Response) -> int | None:
        """Safely get response size."""
        try:
            if hasattr(response, "body") and response.body:
                return len(response.body)
            return None
        except Exception:
            return None


def setup_unified_observability_middleware(app: ASGIApp, exclude_paths: list = None) -> None:
    """
    Setup unified observability middleware.

    Replaces multiple middleware with single high-performance component.
    """
    if exclude_paths is None:
        exclude_paths = []
    
    # Pass configuration to Starlette middleware system
    app.add_middleware(UnifiedObservabilityMiddleware, exclude_paths=exclude_paths)

    # Register health check with configuration-level details only
    register_middleware_health(
        "UnifiedObservabilityMiddleware",
        lambda: {
            "healthy": True,
            "details": {
                "exclude_paths": exclude_paths,
            },
        },
    )
