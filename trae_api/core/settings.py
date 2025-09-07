import enum
from pathlib import Path
from tempfile import gettempdir
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

TEMP_DIR = Path(gettempdir())


class LogLevel(str, enum.Enum):
    """Possible log levels."""

    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class Settings(BaseSettings):
    """
    Application settings.

    These parameters can be configured
    with environment variables.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    # quantity of workers for uvicorn
    workers_count: int = 1
    # Enable uvicorn reloading
    reload: bool = False

    # Current environment
    environment: str = "dev"

    log_level: LogLevel = LogLevel.INFO

    # Grpc endpoint for opentelemetry.
    # E.G. http://localhost:4317
    opentelemetry_endpoint: Optional[str] = None

    # TaskIQ broker configuration
    taskiq_broker: Optional[str] = None  # zmq | inmemory | nats | pika ...
    taskiq_zmq_pub_host: str = "tcp://127.0.0.1:5555"
    taskiq_zmq_sub_host: str = "tcp://127.0.0.1:5556"
    enable_taskiq_metrics: bool = True

    # Local data directory for SQLite and other file-based storage
    data_dir: Path = Path.cwd() / "data"

    @property
    def taskiq_db_path(self) -> Path:
        """Path to TaskIQ SQLite database file."""
        return self.data_dir / "taskiq_results.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRAE_API_",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env vars like GOOGLE_API_KEY
    )


settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings
