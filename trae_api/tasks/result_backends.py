"""Local SQLite result backend for TaskIQ desktop applications.

Following TaskIQ best practices:
- Implements AsyncResultBackend interface
- Uses aiosqlite for async SQLite operations
- Stores task results in local file database
- Perfect for desktop/local applications without external dependencies
- Automatic database initialization and table creation
"""

import json
import re
from pathlib import Path
from typing import Any, Optional, TypeVar

import aiosqlite
from taskiq import TaskiqResult
from taskiq.abc.result_backend import AsyncResultBackend

from trae_api.core.logging import get_logger

# Monitoring import handled at runtime to avoid circular imports

_ReturnType = TypeVar("_ReturnType")

logger = get_logger(__name__)

# SQL injection prevention: Use constants for table structure
DEFAULT_TABLE_NAME = "taskiq_results"
ALLOWED_TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class SQLiteResultBackend(AsyncResultBackend[_ReturnType]):
    """SQLite-based result backend for local desktop applications.

    Features:
    - File-based storage (no external services required)
    - Async operations using aiosqlite
    - Automatic database initialization
    - JSON serialization for complex data types
    - Configurable result retention
    """

    def __init__(
        self,
        database_path: str = "taskiq_results.db",
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> None:
        """Initialize SQLite result backend.

        Args:
            database_path: Path to SQLite database file
            table_name: Name of the results table (validated for security)

        Raises:
            ValueError: If table_name contains invalid characters
        """
        self.database_path = Path(database_path)

        # SQL injection prevention: Validate table name
        if not ALLOWED_TABLE_NAME_PATTERN.match(table_name):
            msg = f"Invalid table name: {table_name}. Must match pattern [a-zA-Z_][a-zA-Z0-9_]*"
            raise ValueError(msg)
        self.table_name = table_name

        # Ensure parent directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    async def startup(self) -> None:
        """Initialize the SQLite database and create results table."""
        try:
            async with aiosqlite.connect(self.database_path) as db:
                await db.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        task_id TEXT PRIMARY KEY,
                        result TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                )
                await db.commit()
                logger.info(f"SQLite result backend initialized: {self.database_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite backend: {e}")
            raise

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        logger.info("SQLite result backend shutdown")

    async def set_result(
        self,
        task_id: str,
        result: TaskiqResult[_ReturnType],
    ) -> None:
        """Store task result in SQLite database.

        Args:
            task_id: Unique task identifier
            result: TaskIQ result object to store
        """
        try:
            # Serialize result to JSON
            result_data = {
                "is_err": result.is_err,
                "return_value": self._serialize_value(result.return_value),
                "execution_time": result.execution_time,
                "log": result.log,
                "error": str(result.error) if result.error else None,
                "labels": dict(result.labels) if result.labels else {},
            }

            result_json = json.dumps(result_data, default=str)

            async with aiosqlite.connect(self.database_path) as db:
                await db.execute(
                    f"INSERT OR REPLACE INTO {self.table_name} (task_id, result) VALUES (?, ?)",  # noqa: S608
                    (task_id, result_json),
                )
                await db.commit()

            # Track operation for monitoring
            try:
                from trae_api.api.monitoring.endpoints.views import (  # noqa: PLC0415
                    sqlite_operations_total,
                )

                sqlite_operations_total.add(1, {"operation": "set_result"})
            except (ImportError, AttributeError):
                pass  # Monitoring not available

            logger.debug(f"Stored result for task {task_id}")

        except Exception as e:
            logger.error(f"Failed to store result for task {task_id}: {e}")
            raise

    async def get_result(
        self,
        task_id: str,
        with_logs: bool = False,
    ) -> Optional[TaskiqResult[_ReturnType]]:
        """Retrieve task result from SQLite database.

        Args:
            task_id: Unique task identifier
            with_logs: Whether to include execution logs

        Returns:
            TaskiqResult object or None if not found
        """
        try:
            async with (
                aiosqlite.connect(self.database_path) as db,
                db.execute(
                    f"SELECT result FROM {self.table_name} WHERE task_id = ?",  # noqa: S608
                    (task_id,),
                ) as cursor,
            ):
                row = await cursor.fetchone()

            if not row:
                logger.debug(f"No result found for task {task_id}")
                return None

            # Track operation for monitoring
            try:
                from trae_api.api.monitoring.endpoints.views import (  # noqa: PLC0415
                    sqlite_operations_total,
                )

                sqlite_operations_total.add(1, {"operation": "get_result"})
            except (ImportError, AttributeError):
                pass  # Monitoring not available

            result_data = json.loads(row[0])

            # Filter out logs if not requested
            if not with_logs:
                result_data["log"] = None

            # Reconstruct TaskiqResult
            return TaskiqResult(
                is_err=result_data["is_err"],
                return_value=result_data["return_value"],
                execution_time=result_data["execution_time"],
                log=result_data.get("log"),
                error=result_data.get("error"),
                labels=result_data.get("labels", {}),
            )

        except Exception as e:
            logger.error(f"Failed to retrieve result for task {task_id}: {e}")
            return None

    async def is_result_ready(self, task_id: str) -> bool:
        """Check if result exists without fetching full details.

        Args:
            task_id: Unique task identifier

        Returns:
            True if result exists, False otherwise
        """
        try:
            async with (
                aiosqlite.connect(self.database_path) as db,
                db.execute(
                    f"SELECT 1 FROM {self.table_name} WHERE task_id = ? LIMIT 1",  # noqa: S608
                    (task_id,),
                ) as cursor,
            ):
                row = await cursor.fetchone()
                return row is not None

        except Exception as e:
            logger.error(f"Failed to check result status for task {task_id}: {e}")
            return False

    def _serialize_value(self, value: Any) -> Any:
        """Serialize complex values for JSON storage.

        Args:
            value: Value to serialize

        Returns:
            JSON-serializable value
        """
        try:
            # Test if value is already JSON serializable
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            # Fall back to string representation for complex objects
            return str(value)

    async def cleanup_old_results(self, days: int = 30) -> int:
        """Remove old results to prevent database bloat.

        Args:
            days: Number of days to retain results

        Returns:
            Number of deleted records
        """
        try:
            # Validate days parameter
            days_int = int(days)
            if days_int < 0:
                raise ValueError("Days must be non-negative")
            
            # Use parameterized query to prevent SQL injection
            modifier = f"-{days_int} days"
            
            async with aiosqlite.connect(self.database_path) as db:
                # Note: table_name is still interpolated as it's controlled internally
                # Parameters can't be used for table names in SQLite
                async with db.execute(
                    f"DELETE FROM {self.table_name} WHERE created_at < datetime('now', ?)",  # noqa: S608
                    (modifier,)
                ) as cursor:
                    deleted_count = cursor.rowcount

                await db.commit()

                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old task results")

                return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old results: {e}")
            return 0
