"""
Advanced metrics middleware with circuit breaker and error handling.

This middleware provides comprehensive metrics collection with production-grade
reliability features following Meta/Apache engineering standards.
"""

import time
from enum import Enum
from typing import Awaitable, Callable, Optional

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from trae_api.api.monitoring.endpoints.views import (
    active_connections,
    http_request_duration,
    http_requests_total,
    prom_http_duration,
    prom_http_requests,
    taskiq_task_duration,
    taskiq_tasks_total,
)
from trae_api.api.monitoring.middleware_health import register_middleware_health
from trae_api.core.config import settings
from trae_api.core.logging.schema import ErrorLogEntry, LogLevel


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Metrics disabled due to failures
    HALF_OPEN = "half_open"  # Testing if metrics are recovered


class AdvancedMetricsMiddleware(BaseHTTPMiddleware):
    """
    Production-grade metrics collection with reliability features.

    Features:
    - Dual instrumentation (OpenTelemetry + Prometheus)
    - Circuit breaker for metrics collection failures
    - Structured error logging
    - Self-monitoring and health checks
    - Performance optimization

    Design principles:
    - Fail-safe: Never breaks application on metrics failure
    - Observable: Logs its own health and performance
    - Resilient: Circuit breaker prevents cascading failures
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = structlog.get_logger()

        # Circuit breaker state
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = 5
        self.recovery_timeout = 60  # seconds
        self.last_failure_time = 0

        # Performance tracking
        self.metrics_collection_time = 0
        self.total_requests = 0

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process request with advanced metrics collection."""
        # Skip metrics for metrics endpoints (prevent recursion)
        if request.url.path in ["/api/metrics", "/metrics"]:
            return await call_next(request)

        # Check circuit breaker
        if not self._should_collect_metrics():
            # Metrics collection disabled, just process request
            return await call_next(request)

        start_time = time.time()
        method = request.method
        path = request.url.path

        # Increment active connections (fail-safe)
        self._safe_increment_active_connections()

        try:
            # Process request
            response = await call_next(request)
            status_code = response.status_code

        except Exception as exc:
            # Capture exception for metrics
            status_code = 500
            self._log_application_error(request, exc)
            
            # Re-raise the exception so global error handlers can process it
            raise

        finally:
            # Always record metrics and decrement connections
            duration = time.time() - start_time
            self._record_metrics(method, path, status_code, duration)
            self._safe_decrement_active_connections()
            self.total_requests += 1

        return response

    def _should_collect_metrics(self) -> bool:
        """Check if metrics collection should proceed based on circuit breaker."""
        current_time = time.time()

        if self.circuit_state == CircuitState.CLOSED:
            return True

        if self.circuit_state == CircuitState.OPEN:
            # Check if enough time has passed to try again
            if current_time - self.last_failure_time > self.recovery_timeout:
                self.circuit_state = CircuitState.HALF_OPEN
                return True
            return False

        # HALF_OPEN
        return True

    def _record_metrics(self, method: str, path: str, status_code: int, duration: float) -> None:
        """Record metrics with circuit breaker protection."""
        metrics_start = time.time()

        try:
            # Record OpenTelemetry metrics
            http_requests_total.add(
                1,
                {
                    "method": method,
                    "endpoint": path,
                    "status_code": str(status_code),
                },
            )

            http_request_duration.record(
                duration,
                {
                    "method": method,
                    "endpoint": path,
                },
            )

            # Record Prometheus metrics
            prom_http_requests.labels(
                method=method,
                endpoint=path,
                status_code=status_code,
            ).inc()

            prom_http_duration.labels(
                method=method,
                endpoint=path,
            ).observe(duration)

            # Reset circuit breaker on success
            if self.circuit_state == CircuitState.HALF_OPEN:
                self.circuit_state = CircuitState.CLOSED
                self.failure_count = 0
                self.logger.info(
                    "Metrics collection recovered",
                    circuit_state=self.circuit_state.value,
                    failure_count=self.failure_count,
                )

        except Exception as exc:
            # Handle metrics collection failures
            self._handle_metrics_failure(exc)

        finally:
            # Track metrics collection performance
            self.metrics_collection_time += time.time() - metrics_start

    def _handle_metrics_failure(self, exc: Exception) -> None:
        """Handle metrics collection failures with circuit breaker."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.circuit_state = CircuitState.OPEN

        # Log structured error
        try:
            error_entry = ErrorLogEntry(
                level=LogLevel.ERROR,
                message=f"Metrics collection failure: {type(exc).__name__}",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                context={
                    "circuit_state": self.circuit_state.value,
                    "failure_count": self.failure_count,
                    "failure_threshold": self.failure_threshold,
                },
            )

            self.logger.error(
                error_entry.message,
                **error_entry.model_dump(exclude={"message", "timestamp"}),
            )
        except Exception:
            # Ultimate fail-safe
            self.logger.error(
                "Metrics collection failure",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                failure_count=self.failure_count,
            )

    def _safe_increment_active_connections(self) -> None:
        """Safely increment active connections counter."""
        try:
            active_connections.add(1)
        except Exception as exc:
            # Don't let connection counting break the application
            self.logger.debug(
                "Failed to increment active connections",
                exception=str(exc),
            )

    def _safe_decrement_active_connections(self) -> None:
        """Safely decrement active connections counter."""
        try:
            active_connections.add(-1)
        except Exception as exc:
            # Don't let connection counting break the application
            self.logger.debug(
                "Failed to decrement active connections",
                exception=str(exc),
            )

    def _log_application_error(self, request: Request, exc: Exception) -> None:
        """Log application errors with context."""
        try:
            error_entry = ErrorLogEntry(
                level=LogLevel.ERROR,
                message=f"Application error in {request.method} {request.url.path}",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                context={
                    "method": request.method,
                    "path": str(request.url.path),
                    "client_ip": request.client.host if request.client else None,
                },
            )

            self.logger.error(
                error_entry.message,
                **error_entry.model_dump(exclude={"message", "timestamp"}),
                exc_info=True,
            )
        except Exception:
            # Fail-safe logging
            self.logger.error(
                f"Application error in {request.method} {request.url.path}",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                exc_info=True,
            )

    def record_taskiq_metrics(
        self,
        task_name: str,
        duration: float,
        status: str = "success",
    ) -> None:
        """
        Record TaskIQ task metrics with circuit breaker protection.

        Args:
            task_name: Name of the executed task
            duration: Task execution duration in seconds
            status: Task status ("success" or "error")
        """
        # Check if TaskIQ metrics are enabled
        if not settings.enable_taskiq_metrics:
            return

        # Check circuit breaker
        if not self._should_collect_metrics():
            return

        metrics_start = time.time()

        try:
            # Record TaskIQ OpenTelemetry metrics
            taskiq_tasks_total.add(
                1,
                {
                    "task_name": task_name,
                    "status": status,
                },
            )

            taskiq_task_duration.record(
                duration,
                {
                    "task_name": task_name,
                    "status": status,
                },
            )

            # Reset circuit breaker on success
            if self.circuit_state == CircuitState.HALF_OPEN:
                self.circuit_state = CircuitState.CLOSED
                self.failure_count = 0
                self.logger.info(
                    "TaskIQ metrics collection recovered",
                    circuit_state=self.circuit_state.value,
                    failure_count=self.failure_count,
                )

        except Exception as exc:
            # Handle TaskIQ metrics collection failures
            self._handle_metrics_failure(exc)

        finally:
            # Track metrics collection performance
            self.metrics_collection_time += time.time() - metrics_start

    def get_health_status(self) -> dict:
        """Get middleware health status for monitoring."""
        return {
            "circuit_state": self.circuit_state.value,
            "failure_count": self.failure_count,
            "total_requests": self.total_requests,
            "avg_metrics_time_ms": ((self.metrics_collection_time * 1000) / max(self.total_requests, 1)),
            "healthy": self.circuit_state != CircuitState.OPEN,
            "taskiq_metrics_enabled": settings.enable_taskiq_metrics,
        }


class GlobalMiddlewareManager:
    """Manages the global middleware instance."""

    _instance: Optional["AdvancedMetricsMiddleware"] = None

    @classmethod
    def get_instance(cls) -> Optional["AdvancedMetricsMiddleware"]:
        """Get the global middleware instance."""
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "AdvancedMetricsMiddleware") -> None:
        """Set the global middleware instance."""
        cls._instance = instance


def get_metrics_middleware() -> Optional["AdvancedMetricsMiddleware"]:
    """Get the global metrics middleware instance for TaskIQ metrics collection."""
    return GlobalMiddlewareManager.get_instance()


def setup_advanced_metrics_middleware(app: ASGIApp) -> None:
    """Setup advanced metrics middleware with reliability features."""
    middleware_instance = AdvancedMetricsMiddleware(app)
    GlobalMiddlewareManager.set_instance(middleware_instance)
    app.add_middleware(AdvancedMetricsMiddleware)

    # Register health check
    register_middleware_health(
        "AdvancedMetricsMiddleware",
        middleware_instance.get_health_status,
    )
