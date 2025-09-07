# initialize_local_storage is defined in this file
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor

# from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    TELEMETRY_SDK_LANGUAGE,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider

from trae_api.core.config import settings
from trae_api.core.logging import get_logger
from trae_api.tasks.broker import broker

logger = get_logger(__name__)


def setup_opentelemetry(app: FastAPI) -> None:  # pragma: no cover
    """
    Enables opentelemetry instrumentation with traces and metrics.

    :param app: current application.
    """
    if not settings.opentelemetry_endpoint:
        return

    # Create resource for both traces and metrics
    resource = Resource(
        attributes={
            SERVICE_NAME: "trae_api",
            TELEMETRY_SDK_LANGUAGE: "python",
            DEPLOYMENT_ENVIRONMENT: settings.environment,
        },
    )

    # Setup Tracing
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.opentelemetry_endpoint,
                insecure=True,
            ),
        ),
    )
    set_tracer_provider(tracer_provider=tracer_provider)

    # Setup Metrics
    metric_reader = PeriodicExportingMetricReader(
        exporter=OTLPMetricExporter(
            endpoint=settings.opentelemetry_endpoint,
            insecure=True,
        ),
        export_interval_millis=5000,  # Export every 5 seconds
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    set_meter_provider(meter_provider)

    # Instrument FastAPI
    excluded_endpoints = []
    
    # Try to get each route safely
    for route_name in ["health_check", "openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"]:
        try:
            excluded_endpoints.append(app.url_path_for(route_name))
        except Exception:
            # Route doesn't exist or is disabled, skip it
            pass
    
    # Always exclude metrics endpoint
    excluded_endpoints.append("/metrics")

    FastAPIInstrumentor().instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        excluded_urls=",".join(excluded_endpoints),
    )

    # Instrument system metrics (CPU, Memory, Disk, Network)
    SystemMetricsInstrumentor().instrument(
        meter_provider=meter_provider,
        config={
            "system.cpu.time": ["idle", "user", "system", "irq"],
            "system.cpu.utilization": ["idle", "user", "system", "irq"],
            "system.memory.usage": ["used", "free", "cached"],
            "system.memory.utilization": ["used", "free", "cached"],
            "system.disk.io": ["read", "write"],
            "system.disk.operations": ["read", "write"],
            "system.disk.time": ["read", "write"],
            "system.network.dropped.packets": ["tx", "rx"],
            "system.network.packets": ["tx", "rx"],
            "system.network.errors": ["tx", "rx"],
            "system.network.io": ["tx", "rx"],
            "process.runtime.memory": ["rss", "vms"],
            "process.runtime.cpu.time": ["user", "system"],
            "process.runtime.gc_count": [],
        },
    )

    # LoggingInstrumentor().instrument(
    #     tracer_provider=tracer_provider,
    #     set_logging_format=True,
    #     log_level=logging.getLevelName(settings.log_level.value),
    # )


def stop_opentelemetry(app: FastAPI) -> None:  # pragma: no cover
    """
    Disables opentelemetry instrumentation.

    :param app: current application.
    """
    if not settings.opentelemetry_endpoint:
        return

    FastAPIInstrumentor().uninstrument_app(app)
    SystemMetricsInstrumentor().uninstrument()


"""TaskIQ startup utilities for local desktop applications.

Handles initialization of local data directories, database setup,
and other startup tasks required for desktop deployment.
"""


def ensure_local_directories() -> None:
    """Create necessary local directories for desktop operation.

    Creates:
    - Data directory for SQLite databases
    - Any other required directories for local operation
    """
    try:
        # Create data directory
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Data directory ensured: {settings.data_dir}")

        # Create subdirectories if needed
        (settings.data_dir / "logs").mkdir(exist_ok=True)
        (settings.data_dir / "temp").mkdir(exist_ok=True)

    except Exception as e:
        logger.error(f"Failed to create local directories: {e}")
        raise


def initialize_local_storage() -> None:
    """Initialize local storage systems.

    Prepares SQLite databases and other local storage
    components for desktop operation.
    """
    try:
        # Ensure directories exist
        ensure_local_directories()

        # Log configuration for debugging
        logger.info(f"TaskIQ database path: {settings.taskiq_db_path}")
        logger.info(f"Data directory: {settings.data_dir}")

    except Exception as e:
        logger.error(f"Failed to initialize local storage: {e}")
        raise


async def cleanup_old_data(days: int = 30) -> None:
    """Clean up old data files to prevent disk bloat.

    Args:
        days: Number of days to retain data
    """
    try:
        # Cleanup old task results if result backend supports cleanup
        if (
            hasattr(broker, "result_backend")
            and broker.result_backend
            and hasattr(broker.result_backend, "cleanup_old_results")
            and callable(broker.result_backend.cleanup_old_results)
        ):
            deleted_count = await broker.result_backend.cleanup_old_results(days)
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old task results")

    except Exception as e:
        logger.warning(f"Failed to cleanup old data: {e}")


@asynccontextmanager
async def lifespan_setup(
    app: FastAPI,
) -> AsyncGenerator[None, None]:  # pragma: no cover
    """
    Actions to run on application startup.

    This function uses fastAPI app to store data
    in the state, such as db_engine.

    :param app: the fastAPI application.
    :return: function that actually performs actions.
    """

    app.middleware_stack = None

    # Initialize local storage for desktop deployment
    initialize_local_storage()

    # Initialize TaskIQ broker following best practices
    # Guard broker start-up/shutdown with broker.is_worker_process to avoid recursion inside workers
    if not broker.is_worker_process:
        # Manually initialize result backend if needed
        if hasattr(broker, "result_backend") and broker.result_backend:
            await broker.result_backend.startup()
        await broker.startup()

    setup_opentelemetry(app)
    app.middleware_stack = app.build_middleware_stack()

    yield

    # Shutdown TaskIQ broker following best practices
    # Guard broker start-up/shutdown with broker.is_worker_process to avoid recursion inside workers
    if not broker.is_worker_process:
        await broker.shutdown()

    stop_opentelemetry(app)
