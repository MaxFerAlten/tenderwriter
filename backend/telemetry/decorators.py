"""Decorators for OpenTelemetry instrumentation."""

from __future__ import annotations

import functools
import time
import logging
from typing import Any, Callable, TypeVar, ParamSpec
from typing import Awaitable

from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode

from backend.telemetry.tracing import get_tracer, add_span_attributes, record_exception
from backend.telemetry.metrics import metrics as metrics_instance

P = ParamSpec("P")
T = TypeVar("T")

_logger = logging.getLogger("tenderclaw.telemetry.decorators")


def traced(
    name: str | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to add OpenTelemetry tracing to functions.

    Usage:
        @traced()
        async def my_function():
            ...

        @traced(name="custom.span.name", kind=SpanKind.CLIENT)
        def sync_function():
            ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
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

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
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

        if hasattr(func, "__code__") and func.__code__.co_flags & 0x80:
            return async_wrapper
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def timed(
    histogram_name: str = "tenderclaw.response_time",
    description: str = "Execution time",
    unit: str = "ms",
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to record execution time metrics.

    Usage:
        @timed()
        async def slow_function():
            ...

        @timed(histogram_name="my.custom.histogram", attributes={"operation": "test"})
        def sync_function():
            ...
    """
    _meter = metrics.get_meter("tenderclaw.timed")
    _histogram = _meter.create_histogram(histogram_name, description, unit)

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                attrs = {"function": f"{func.__module__}.{func.__qualname__}"}
                if attributes:
                    attrs.update(attributes)
                _histogram.record(duration_ms, attrs)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                attrs = {"function": f"{func.__module__}.{func.__qualname__}"}
                if attributes:
                    attrs.update(attributes)
                _histogram.record(duration_ms, attrs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def logged(
    logger: logging.Logger | None = None,
    level: str = "info",
    attributes: dict[str, Any] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to add structured logging to functions.

    Usage:
        @logged()
        async def my_function():
            ...

        @logged(level="debug", attributes={"component": "processor"})
        def sync_function():
            ...
    """
    _log = logger or _logger

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        func_name = f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            attrs = {"function": func_name}
            if attributes:
                attrs.update(attributes)
            log_method = getattr(_log, level.lower(), _log.info)
            log_method(f"Entering {func_name}", extra=attrs)
            try:
                result = await func(*args, **kwargs)
                _log.debug(f"Exiting {func_name}", extra=attrs)
                return result
            except Exception as exc:
                _log.exception(f"Error in {func_name}", extra={**attrs, "error": str(exc)})
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            attrs = {"function": func_name}
            if attributes:
                attrs.update(attributes)
            log_method = getattr(_log, level.lower(), _log.info)
            log_method(f"Entering {func_name}", extra=attrs)
            try:
                result = func(*args, **kwargs)
                _log.debug(f"Exiting {func_name}", extra=attrs)
                return result
            except Exception as exc:
                _log.exception(f"Error in {func_name}", extra={**attrs, "error": str(exc)})
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class TraceContext:
    """Context manager for creating a traced block with custom attributes."""

    def __init__(
        self,
        name: str,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ):
        self.name = name
        self.kind = kind
        self.attributes = attributes or {}
        self._span: trace.Span | None = None

    def __enter__(self) -> trace.Span:
        tracer = get_tracer()
        self._span = tracer.start_span(self.name, kind=self.kind, attributes=self.attributes)
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._span:
            if exc_val:
                self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self._span.record_exception(exc_val)
            else:
                self._span.set_status(Status(StatusCode.OK))
            self._span.end()

    async def __aenter__(self) -> trace.Span:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


def trace_function(
    func: Callable[P, T],
    name: str | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Callable[P, T]:
    """Apply tracing to a function (explicit alternative to decorator).

    Usage:
        traced_func = trace_function(my_function, name="custom.name")
    """
    return traced(name=name, kind=kind, attributes=attributes)(func)
