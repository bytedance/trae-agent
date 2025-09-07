import logging
import time
from typing import Any, Dict

import psutil
from fastapi import APIRouter, Response
from opentelemetry import metrics
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from trae_api.core.config import settings

router = APIRouter()

# Create OpenTelemetry meter
meter = metrics.get_meter("trae_api.monitoring")

# OpenTelemetry metrics
http_requests_total = meter.create_counter(
    "http_requests_total",
    description="Total number of HTTP requests",
    unit="1",
)

http_request_duration = meter.create_histogram(
    "http_request_duration_seconds",
    description="HTTP request duration in seconds",
    unit="s",
)

taskiq_tasks_total = meter.create_counter(
    "taskiq_tasks_total",
    description="Total number of TaskIQ tasks processed",
    unit="1",
)

taskiq_task_duration = meter.create_histogram(
    "taskiq_task_duration_seconds",
    description="TaskIQ task duration in seconds",
    unit="s",
)

active_connections = meter.create_up_down_counter(
    "active_connections",
    description="Number of active connections",
    unit="1",
)

# Local storage metrics for desktop deployment
sqlite_db_size = meter.create_gauge(
    "sqlite_db_size_bytes",
    description="SQLite database file size in bytes",
    unit="bytes",
)

sqlite_operations_total = meter.create_counter(
    "sqlite_operations_total",
    description="Total SQLite operations performed",
    unit="1",
)

# Prometheus metrics registry for /metrics endpoint
prometheus_registry = CollectorRegistry()

# Prometheus metrics
prom_http_requests = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=prometheus_registry,
)

prom_http_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    registry=prometheus_registry,
)

prom_system_cpu = Gauge(
    "system_cpu_usage_percent",
    "System CPU usage percentage",
    registry=prometheus_registry,
)

prom_system_memory = Gauge(
    "system_memory_usage_bytes",
    "System memory usage in bytes",
    ["type"],
    registry=prometheus_registry,
)

prom_system_disk = Gauge(
    "system_disk_usage_bytes",
    "System disk usage in bytes",
    ["device", "type"],
    registry=prometheus_registry,
)

prom_process_memory = Gauge(
    "process_memory_bytes",
    "Process memory usage in bytes",
    ["type"],
    registry=prometheus_registry,
)


def update_system_metrics() -> None:
    """Update system metrics for Prometheus."""
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=None)
    prom_system_cpu.set(cpu_percent)

    # Memory usage
    memory = psutil.virtual_memory()
    prom_system_memory.labels(type="used").set(memory.used)
    prom_system_memory.labels(type="available").set(memory.available)
    prom_system_memory.labels(type="total").set(memory.total)

    # Disk usage for root partition
    try:
        disk = psutil.disk_usage("/")
        prom_system_disk.labels(device="root", type="used").set(disk.used)
        prom_system_disk.labels(device="root", type="free").set(disk.free)
        prom_system_disk.labels(device="root", type="total").set(disk.total)
    except Exception as e:
        logging.warning("Failed to get disk usage for root partition: %s", e)

    # Process memory
    process = psutil.Process()
    memory_info = process.memory_info()
    prom_process_memory.labels(type="rss").set(memory_info.rss)
    prom_process_memory.labels(type="vms").set(memory_info.vms)


@router.get("/metrics")
async def get_metrics() -> Response:
    """Prometheus metrics endpoint."""
    # Update system metrics before returning
    update_system_metrics()

    # Generate Prometheus metrics
    metrics_data = generate_latest(prometheus_registry)

    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint with basic system info and local storage status."""
    # Import moved to top of file to avoid PLC0415

    # Check SQLite database file
    sqlite_status = "unknown"
    sqlite_size = 0

    try:
        if settings.taskiq_db_path.exists():
            sqlite_size = settings.taskiq_db_path.stat().st_size
            sqlite_status = "available"

            # Update metrics
            sqlite_db_size.set(sqlite_size)
        else:
            sqlite_status = "not_created"
    except Exception as e:
        sqlite_status = f"error: {e!s}"

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": (psutil.disk_usage("/").percent if psutil.disk_usage("/") else None),
        },
        "process": {
            "pid": psutil.Process().pid,
            "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024,
            "cpu_percent": psutil.Process().cpu_percent(),
        },
        "storage": {
            "data_dir": str(settings.data_dir),
            "data_dir_exists": settings.data_dir.exists(),
            "sqlite_db": {
                "path": str(settings.taskiq_db_path),
                "status": sqlite_status,
                "size_bytes": sqlite_size,
            },
        },
    }


@router.get("/readiness")
async def readiness_check() -> Dict[str, str]:
    """Readiness check for Kubernetes."""
    # Add checks for external dependencies here (database, redis, etc.)
    return {"status": "ready"}


@router.get("/liveness")
async def liveness_check() -> Dict[str, str]:
    """Liveness check for Kubernetes."""
    return {"status": "alive"}
