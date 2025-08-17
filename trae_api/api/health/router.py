"""Health check endpoints with local storage monitoring."""

import time
from typing import Any, Dict

import psutil
from fastapi import APIRouter

from trae_api.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint with local storage monitoring for desktop deployment."""

    # Check SQLite database file
    sqlite_status = "unknown"
    sqlite_size = 0

    try:
        if settings.taskiq_db_path.exists():
            sqlite_size = settings.taskiq_db_path.stat().st_size
            sqlite_status = "available"
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


# Removed /ready endpoint to avoid duplication with /readiness
# Use /api/readiness instead (Kubernetes standard)
