"""OpenTelemetry instrumentation for TenderClaw."""

from backend.telemetry.tracing import setup_tracing, get_tracer, traced, SpanKind
from backend.telemetry.metrics import (
    setup_metrics,
    get_meter,
    Metrics,
    metrics_instance,
    request_counter,
    tool_call_counter,
    error_counter,
    response_time_histogram,
    token_count_histogram,
    cost_histogram,
    active_sessions_gauge,
    queue_depth_gauge,
)
from backend.telemetry.logging_config import setup_logging_with_tracing
from backend.telemetry.decorators import traced, timed, logged

__all__ = [
    "setup_tracing",
    "get_tracer",
    "setup_metrics",
    "get_meter",
    "setup_logging_with_tracing",
    "SpanKind",
    "traced",
    "timed",
    "logged",
    "Metrics",
    "metrics_instance",
    "request_counter",
    "tool_call_counter",
    "error_counter",
    "response_time_histogram",
    "token_count_histogram",
    "cost_histogram",
    "active_sessions_gauge",
    "queue_depth_gauge",
]
