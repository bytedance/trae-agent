import importlib.util
from typing import Dict
from unittest.mock import patch
from uuid import uuid4

import pytest
from opentelemetry.trace import INVALID_SPAN, INVALID_SPAN_CONTEXT

from trae_api.core.logging.schema import (
    BaseLogEntry,
    ErrorLogEntry,
    LogLevel,
    PerformanceLogEntry,
    RequestLogEntry,
    TraceLogEntry,
)
from trae_api.core.logging.structlog import (
    add_service_context,
    add_trace_context,
    configure_structlog,
    get_trace_context,
)


class TestLoggingSchemas:
    """Tests for the logging schema models."""

    @pytest.mark.parametrize(
        "log_level,expected_level",
        [
            (LogLevel.DEBUG, "DEBUG"),
            (LogLevel.INFO, "INFO"),
            (LogLevel.ERROR, "ERROR"),
            (LogLevel.CRITICAL, "CRITICAL"),
        ],
    )
    def test_log_level_enum(self, log_level: LogLevel, expected_level: str) -> None:
        """Test that LogLevel enum values are correct."""
        assert log_level.value == expected_level

    @pytest.mark.parametrize(
        "message,service",
        [
            ("Test message", "trae_api"),
            ("Error occurred", "custom_service"),
        ],
    )
    def test_base_log_entry_validation(self, message: str, service: str) -> None:
        """Test validation for the BaseLogEntry model."""
        entry = BaseLogEntry(
            level=LogLevel.INFO,
            message=message,
            service=service,
        )
        assert entry.level == LogLevel.INFO
        assert entry.message == message
        assert entry.service == service
        assert entry.timestamp is not None

    @pytest.mark.parametrize(
        "method,path,status_code",
        [
            ("GET", "/api/health", 200),
            ("POST", "/api/tasks/hello", 422),
            ("DELETE", "/api/unknown", 404),
        ],
    )
    def test_request_log_entry_validation(self, method: str, path: str, status_code: int) -> None:
        """Test validation for the RequestLogEntry model."""
        correlation_id = uuid4()
        request_id = uuid4()

        entry = RequestLogEntry(
            level=LogLevel.INFO,
            message="Request processed",
            correlation_id=correlation_id,
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
        )

        assert entry.method == method
        assert entry.path == path
        assert entry.status_code == status_code
        assert entry.correlation_id == correlation_id
        assert entry.request_id == request_id

    @pytest.mark.parametrize(
        "trace_id,span_id",
        [
            ("032x_formatted_trace", "016x_formatted_span"),
            ("0", "0"),
            ("invalid_trace", "invalid_span"),
        ],
    )
    def test_trace_log_entry_validation(self, trace_id: str, span_id: str) -> None:
        """Test validation for the TraceLogEntry model."""
        entry = TraceLogEntry(
            level=LogLevel.DEBUG,
            message="Trace message",
            trace_id=trace_id,
            span_id=span_id,
        )

        assert entry.trace_id == trace_id
        assert entry.span_id == span_id

    @pytest.mark.parametrize(
        "exception_type,exception_message",
        [
            ("ValueError", "Invalid input provided"),
            ("ConnectionError", "Database connection failed"),
            ("TimeoutError", "Request timeout exceeded"),
        ],
    )
    def test_error_log_entry_validation(self, exception_type: str, exception_message: str) -> None:
        """Test validation for the ErrorLogEntry model."""
        entry = ErrorLogEntry(
            level=LogLevel.ERROR,
            message="Error occurred",
            exception_type=exception_type,
            exception_message=exception_message,
            context={"user_id": "123", "request_path": "/api/test"},
        )

        assert entry.exception_type == exception_type
        assert entry.exception_message == exception_message
        assert entry.context is not None

    @pytest.mark.parametrize(
        "operation,duration_ms,cpu_percent",
        [
            ("database_query", 150.5, 25.3),
            ("api_call", 89.2, 15.1),
            ("file_processing", 2500.0, 45.8),
        ],
    )
    def test_performance_log_entry_validation(
        self,
        operation: str,
        duration_ms: float,
        cpu_percent: float,
    ) -> None:
        """Test validation for the PerformanceLogEntry model."""
        entry = PerformanceLogEntry(
            level=LogLevel.INFO,
            message="Performance metric",
            operation=operation,
            duration_ms=duration_ms,
            cpu_percent=cpu_percent,
        )

        assert entry.operation == operation
        assert entry.duration_ms == duration_ms
        assert entry.cpu_percent == cpu_percent


class TestStructuredLogging:
    """Tests for the structured logging configuration and processors."""

    @pytest.mark.parametrize(
        "trace_context,expected_ids",
        [
            ("valid_trace", {"trace_id": "12345678901234567890123456789012", "span_id": "1234567890123456"}),
            ("no_trace", {"trace_id": "0", "span_id": "0"}),
            ("invalid_context", {"trace_id": "0", "span_id": "0"}),
        ],
    )
    def test_trace_context_extraction(self, trace_context: str, expected_ids: Dict[str, str]) -> None:
        """Test the extraction of OpenTelemetry trace context."""
        with patch("trae_api.core.logging.structlog.get_current_span") as mock_span:
            if trace_context == "no_trace":
                mock_span.return_value = INVALID_SPAN
            elif trace_context == "invalid_context":
                mock_span_obj = mock_span.return_value
                mock_span_obj.get_span_context.return_value = INVALID_SPAN_CONTEXT
            else:
                # valid_trace case
                mock_span_obj = mock_span.return_value
                mock_context = mock_span_obj.get_span_context.return_value
                mock_context.trace_id = int("12345678901234567890123456789012", 16)
                mock_context.span_id = int("1234567890123456", 16)

            result = get_trace_context()

            # Check the trace context matches expected values exactly
            assert result["trace_id"] == expected_ids["trace_id"]
            assert result["span_id"] == expected_ids["span_id"]

    @pytest.mark.parametrize(
        "environment,expect_json_renderer",
        [
            ("development", False),
            ("production", True),
            ("testing", True),
        ],
    )
    def test_structlog_configuration(self, environment: str, expect_json_renderer: bool) -> None:
        """Test structlog configuration selects renderer and core processors by environment."""
        # Patch the exact settings object used in configure_structlog
        with patch("trae_api.core.logging.structlog.settings") as mock_settings:
            mock_settings.environment = environment
            mock_settings.log_level.value = "INFO"

            with patch("structlog.configure") as mock_configure:
                configure_structlog()

                call_args = mock_configure.call_args
                processors = call_args[1]["processors"]

                # Core processors should be present
                import structlog as _structlog  # local import to avoid top-level dependency in test imports
                from structlog.dev import ConsoleRenderer
                from structlog.processors import JSONRenderer, TimeStamper

                assert _structlog.contextvars.merge_contextvars in processors
                assert _structlog.processors.add_log_level in processors
                assert any(isinstance(p, TimeStamper) for p in processors)

                # Service and trace context processors present
                assert add_service_context in processors
                assert add_trace_context in processors
                # Correlation context function presence by name (avoid direct import to keep test imports minimal)
                assert any(getattr(p, "__name__", "") == "add_correlation_context" for p in processors)

                if expect_json_renderer:
                    assert any(isinstance(p, JSONRenderer) for p in processors)
                else:
                    assert any(isinstance(p, ConsoleRenderer) for p in processors)

    def test_service_context_processor(self) -> None:
        """Test that the service context processor adds the correct data."""
        logger = None
        method_name = "info"
        event_dict = {"message": "test"}

        result = add_service_context(logger, method_name, event_dict)

        assert result["service"] == "trae_api"
        assert result["version"] == "0.1.0"
        assert "environment" in result

    def test_trace_context_processor(self) -> None:
        """Test that the trace context processor adds the correct data."""
        logger = None
        method_name = "info"
        event_dict = {"message": "test"}

        with patch("trae_api.core.logging.structlog.get_trace_context") as mock_trace:
            mock_trace.return_value = {"trace_id": "test_trace", "span_id": "test_span"}

            result = add_trace_context(logger, method_name, event_dict)

            assert result["trace_id"] == "test_trace"
            assert result["span_id"] == "test_span"


class TestDependencyAvailability:
    """Tests for the availability of optional logging dependencies."""

    @pytest.mark.parametrize(
        "package,expected_available",
        [
            ("structlog", True),
            ("pythonjsonlogger", True),
            ("asgi_correlation_id", True),
        ],
    )
    def test_logging_dependencies_available(self, package: str, expected_available: bool) -> None:
        """Test that optional logging dependencies are available (skip if missing)."""
        spec = importlib.util.find_spec(package)
        if spec is None:
            pytest.skip(f"{package} not installed in test environment")
        assert spec is not None
