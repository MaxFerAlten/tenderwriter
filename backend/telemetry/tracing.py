"""OpenTelemetry tracing setup and utilities."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator
from functools import wraps

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logger = logging.getLogger("tenderclaw.telemetry")

_tracer: Tracer | None = None
_provider: TracerProvider | None = None


class SpanKind:
    """Span kind constants matching OpenTelemetry spec."""
    INTERNAL = trace.SpanKind.INTERNAL
    SERVER = trace.SpanKind.SERVER
    CLIENT = trace.SpanKind.CLIENT
    PRODUCER = trace.SpanKind.PRODUCER
    CONSUMER = trace.SpanKind.CONSUMER


def setup_tracing(
    service_name: str = "tenderclaw",
    service_version: str = "0.1.0",
    otlp_endpoint: str | None = None,
    console_export: bool = False,
) -> TracerProvider:
    """Initialize OpenTelemetry tracing with OTLP export."""
    global _tracer, _provider

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })

    _provider = TracerProvider(resource=resource)

    if console_export or otlp_endpoint is None:
        _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            _provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("OTLP tracing enabled, endpoint: %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("Failed to setup OTLP exporter: %s, falling back to console", exc)
            _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(_provider)
    _tracer = _provider.get_tracer(service_name, service_version)

    logger.info("Tracing initialized for service: %s", service_name)
    return _provider


def get_tracer(name: str = "tenderclaw") -> Tracer:
    """Get the configured tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(name)
    return _tracer


def instrument_fastapi(app: Any) -> None:
    """Instrument FastAPI application with OpenTelemetry."""
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumentation enabled")


def get_current_span() -> Span | None:
    """Get the current active span."""
    return trace.get_current_span()


def get_current_trace_id() -> str | None:
    """Get the current trace ID as hex string."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return None


def get_current_span_id() -> str | None:
    """Get the current span ID as hex string."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, "016x")
    return None


def traced(
    name: str | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
):
    """Decorator to add tracing to async/sync functions."""
    def decorator(func):
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name, kind=kind, attributes=attributes) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name, kind=kind, attributes=attributes) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        if hasattr(func, "__wrapped__"):
            return async_wrapper if hasattr(func, "__code__") and func.__code__.co_flags & 0x80 else sync_wrapper
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def create_span(
    name: str,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Generator[Span, None, None]:
    """Context manager for creating spans."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind, attributes=attributes) as span:
        yield span


def add_span_attributes(attributes: dict[str, Any]) -> None:
    """Add attributes to the current span."""
    span = trace.get_current_span()
    if span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)


def record_exception(exc: Exception, attributes: dict[str, Any] | None = None) -> None:
    """Record an exception on the current span."""
    span = trace.get_current_span()
    if span:
        span.record_exception(exc)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)


def inject_trace_context(carrier: dict[str, str]) -> dict[str, str]:
    """Inject trace context into a carrier dict for propagation."""
    propagator = TraceContextTextMapPropagator()
    propagator.inject(carrier)
    return carrier


def shutdown_tracing() -> None:
    """Shutdown the tracer provider."""
    global _provider
    if _provider:
        _provider.shutdown()
        logger.info("Tracing shutdown complete")
