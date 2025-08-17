"""
Middleware health check endpoints for monitoring dependencies.

Provides health status for all middleware components following
Meta/Apache standards for observability.
"""

from typing import Any, Callable, Dict

from fastapi import APIRouter
from pydantic import BaseModel

# This will be populated at runtime by middleware instances
_middleware_health_registry = {}

router = APIRouter(tags=["monitoring"])


class MiddlewareHealthStatus(BaseModel):
    """Health status schema for middleware components."""

    name: str
    healthy: bool
    circuit_state: str | None = None
    failure_count: int = 0
    total_requests: int = 0
    avg_response_time_ms: float = 0.0
    details: dict = {}


class MiddlewareHealthResponse(BaseModel):
    """Overall middleware health response."""

    status: str
    middleware_count: int
    healthy_count: int
    unhealthy_count: int
    middleware: list[MiddlewareHealthStatus]


def register_middleware_health(name: str, health_check_func: Callable[[], Dict[str, Any]]) -> None:
    """Register a middleware health check function."""
    _middleware_health_registry[name] = health_check_func


@router.get(
    "/middleware/health",
    response_model=MiddlewareHealthResponse,
    summary="Get middleware health status",
    description="Returns health status for all registered middleware components",
)
async def get_middleware_health() -> MiddlewareHealthResponse:
    """Get comprehensive middleware health status."""
    middleware_status = []
    healthy_count = 0

    for name, health_check in _middleware_health_registry.items():
        try:
            health_data = health_check() if callable(health_check) else health_check

            middleware_health = MiddlewareHealthStatus(
                name=name,
                healthy=health_data.get("healthy", True),
                circuit_state=health_data.get("circuit_state"),
                failure_count=health_data.get("failure_count", 0),
                total_requests=health_data.get("total_requests", 0),
                # Map avg_metrics_time_ms to avg_response_time_ms for consistency
                # Also support the canonical field name directly
                avg_response_time_ms=health_data.get("avg_response_time_ms", 
                                                     health_data.get("avg_metrics_time_ms", 0.0)),
                details=health_data,
            )

            if middleware_health.healthy:
                healthy_count += 1

            middleware_status.append(middleware_health)

        except Exception as exc:
            # Handle health check failures
            middleware_status.append(
                MiddlewareHealthStatus(
                    name=name,
                    healthy=False,
                    details={"error": str(exc)},
                ),
            )

    overall_status = "healthy" if healthy_count == len(middleware_status) else "degraded"
    if healthy_count == 0:
        overall_status = "unhealthy"

    return MiddlewareHealthResponse(
        status=overall_status,
        middleware_count=len(middleware_status),
        healthy_count=healthy_count,
        unhealthy_count=len(middleware_status) - healthy_count,
        middleware=middleware_status,
    )


@router.get(
    "/middleware/health/summary",
    summary="Get middleware health summary",
    description="Returns simplified health status",
)
async def get_middleware_health_summary() -> Dict[str, Any]:
    """Get simplified middleware health status."""
    try:
        health_response = await get_middleware_health()
        return {
            "status": health_response.status,
            "healthy": health_response.status == "healthy",
            "middleware_count": health_response.middleware_count,
            "healthy_count": health_response.healthy_count,
        }
    except Exception:
        return {
            "status": "error",
            "healthy": False,
            "middleware_count": 0,
            "healthy_count": 0,
        }
