import logging
import sys

from opentelemetry.trace import INVALID_SPAN, INVALID_SPAN_CONTEXT, get_current_span

from trae_api.core.config import settings


class InterceptHandler(logging.Handler):
    """
    Default handler from examples in loguru documentation.

    This handler intercepts all log requests and
    passes them to loguru.

    For more info see:
    https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        """
        Propagates logs to loguru.

        :param record: record to log.
        """
        # Use standard logging instead of loguru for better compatibility
        level = record.levelno
        message = record.getMessage()

        # Create a new logger and emit the record
        target_logger = logging.getLogger(record.name)
        target_logger.log(level, message, exc_info=record.exc_info)


def get_trace_info() -> dict[str, str]:  # pragma: no cover
    """
    Get current trace and span information from OpenTelemetry.

    :return: dictionary with trace_id and span_id
    """
    span = get_current_span()
    trace_info = {"trace_id": "0", "span_id": "0"}

    if span != INVALID_SPAN:
        span_context = span.get_span_context()
        if span_context != INVALID_SPAN_CONTEXT:
            trace_info["span_id"] = format(span_context.span_id, "016x")
            trace_info["trace_id"] = format(span_context.trace_id, "032x")

    return trace_info


def configure_logging() -> None:  # pragma: no cover
    """Configures logging."""
    # Configure the root logger with standard logging (single basicConfig call)
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    logging.basicConfig(
        level=getattr(logging, settings.log_level.value.upper()),
        format=log_format,
        stream=sys.stdout,
        force=True,
    )

    # Clear handlers for uvicorn and taskiq loggers and enable propagation
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith("uvicorn."):
            logger = logging.getLogger(logger_name)
            logger.handlers = []
            logger.propagate = True
        if logger_name.startswith("taskiq."):
            logger = logging.getLogger(logger_name)
            logger.handlers = []
            logger.propagate = True

    # Clear handlers for specific uvicorn loggers
    logging.getLogger("uvicorn").handlers = []
    logging.getLogger("uvicorn").propagate = True
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = True
