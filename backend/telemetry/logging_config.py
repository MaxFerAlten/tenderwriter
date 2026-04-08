"""Structured logging configuration with OpenTelemetry trace correlation."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from backend.telemetry.tracing import get_current_trace_id, get_current_span_id


def setup_logging_with_tracing(
    level: str = "INFO",
    structured: bool = True,
) -> None:
    """Configure logging with trace correlation for OpenTelemetry."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if structured:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                _add_trace_context,
                structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        root_logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                _add_trace_context,
            ],
        ))
        root_logger.addHandler(handler)
        root_logger.propagate = False
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root = logging.getLogger("tenderclaw")
        root.setLevel(numeric_level)
        root.handlers.clear()
        root.addHandler(handler)
        root.propagate = False


def _add_trace_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add trace context to log entries."""
    trace_id = get_current_trace_id()
    span_id = get_current_span_id()

    if trace_id:
        event_dict["trace_id"] = trace_id
    if span_id:
        event_dict["span_id"] = span_id

    return event_dict


def get_logger(name: str = "tenderclaw") -> structlog.stdlib.BoundLogger:
    """Get a structured logger with trace correlation."""
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding structured context to logs."""

    def __init__(self, **kwargs: Any):
        self.context = kwargs
        self._token: structlog.contextvars.token = None

    def __enter__(self) -> LogContext:
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._token:
            structlog.contextvars.unbind_contextvars(*self.context.keys())


def add_log_context(**kwargs: Any) -> None:
    """Add context variables to all subsequent log entries."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_log_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


def log_with_trace(
    level: str,
    msg: str,
    **kwargs: Any,
) -> None:
    """Log a message with current trace context attached."""
    logger = get_logger()
    trace_id = get_current_trace_id()
    span_id = get_current_span_id()

    extra = {"trace_id": trace_id, "span_id": span_id, **kwargs}

    log_level = getattr(logger, level.lower(), logger.info)
    log_level(msg, **extra)
