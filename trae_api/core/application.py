from importlib import metadata

from fastapi import FastAPI
from fastapi.responses import UJSONResponse

from trae_api.api.router import api_router
from trae_api.core.lifespan import lifespan_setup
from trae_api.core.logging.structlog import configure_structlog
from trae_api.core.middleware.advanced_metrics import setup_advanced_metrics_middleware
from trae_api.core.middleware.observability import setup_unified_observability_middleware


def get_app() -> FastAPI:
    """
    Get FastAPI application.

    This is the main constructor of an application.

    :return: application.
    """
    try:
        version = metadata.version("trae-agent")
    except metadata.PackageNotFoundError:
        version = "0.1.0"

    # Configure structured logging before app creation
    configure_structlog()

    app = FastAPI(
        title="trae_api",
        version=version,
        lifespan=lifespan_setup,
        docs_url="/docs",
        redoc_url="/",
        openapi_url="/openapi.json",
        default_response_class=UJSONResponse,
    )

    # Setup optimized middleware stack (reduces 4-5 middleware to 2)
    # 1. Unified observability (correlation ID + structured logging + basic metrics)
    setup_unified_observability_middleware(app)

    # 2. Advanced metrics (OpenTelemetry + Prometheus + circuit breaker)
    setup_advanced_metrics_middleware(app)

    # Main router for the API.
    app.include_router(router=api_router, prefix="/api")

    return app


# Create the app instance for direct usage
app = get_app()
