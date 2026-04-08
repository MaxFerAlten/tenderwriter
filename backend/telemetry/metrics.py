"""OpenTelemetry metrics setup and utilities."""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
    ConsoleMetricExporter,
    AggregationTemporality,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Meter, Counter, Histogram, ObservableGauge, Observation, CallbackOptions
from opentelemetry.metrics import MeterProvider as OTelMeterProvider

from backend.services.session_store import session_store

logger = logging.getLogger("tenderclaw.telemetry")

_meter: Meter | None = None
_meter_provider: MeterProvider | None = None

request_counter: Counter | None = None
tool_call_counter: Counter | None = None
error_counter: Counter | None = None

response_time_histogram: Histogram | None = None
token_count_histogram: Histogram | None = None
cost_histogram: Histogram | None = None

active_sessions_gauge: ObservableGauge | None = None
queue_depth_gauge: ObservableGauge | None = None

_active_sessions_callback_count = 0
_queue_depth_callback_count = 0


def setup_metrics(
    service_name: str = "tenderclaw",
    otlp_endpoint: str | None = None,
    console_export: bool = False,
    export_interval_ms: int = 60000,
) -> MeterProvider:
    """Initialize OpenTelemetry metrics with OTLP export."""
    global _meter, _meter_provider
    global request_counter, tool_call_counter, error_counter
    global response_time_histogram, token_count_histogram, cost_histogram
    global active_sessions_gauge, queue_depth_gauge

    resource = Resource.create({SERVICE_NAME: service_name})

    if console_export or otlp_endpoint is None:
        reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(),
            export_interval_millis=export_interval_ms,
        )
    else:
        try:
            otlp_exporter = OTLPMetricExporter(
                endpoint=otlp_endpoint,
                insecure=True,
            )
            reader = PeriodicExportingMetricReader(
                otlp_exporter,
                export_interval_millis=export_interval_ms,
            )
            logger.info("OTLP metrics enabled, endpoint: %s", otlp_endpoint)
        except Exception as exc:
            logger.warning("Failed to setup OTLP exporter: %s, falling back to console", exc)
            reader = PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=export_interval_ms,
            )

    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)
    _meter = _meter_provider.get_meter(service_name, "0.1.0")

    request_counter = _meter.create_counter(
        name="tenderclaw.requests",
        description="Total number of requests",
        unit="1",
    )

    tool_call_counter = _meter.create_counter(
        name="tenderclaw.tool_calls",
        description="Total number of tool calls",
        unit="1",
    )

    error_counter = _meter.create_counter(
        name="tenderclaw.errors",
        description="Total number of errors",
        unit="1",
    )

    response_time_histogram = _meter.create_histogram(
        name="tenderclaw.response_time",
        description="Response time in milliseconds",
        unit="ms",
    )

    token_count_histogram = _meter.create_histogram(
        name="tenderclaw.token_count",
        description="Number of tokens processed",
        unit="1",
    )

    cost_histogram = _meter.create_histogram(
        name="tenderclaw.cost",
        description="Cost in USD",
        unit="USD",
    )

    def _get_active_sessions() -> int:
        try:
            return len(session_store.list_sessions())
        except Exception:
            return 0

    def _active_sessions_callback(options: CallbackOptions) -> list[Observation]:
        return [Observation(_get_active_sessions())]

    def _get_queue_depth() -> int:
        try:
            return sum(
                1 for s in session_store.list_sessions()
                if getattr(s, "status", None) and "busy" in str(s.status).lower()
            )
        except Exception:
            return 0

    def _queue_depth_callback(options: CallbackOptions) -> list[Observation]:
        return [Observation(_get_queue_depth())]

    active_sessions_gauge = _meter.create_observable_gauge(
        name="tenderclaw.active_sessions",
        description="Number of active sessions",
        unit="1",
        callbacks=[_active_sessions_callback],
    )

    queue_depth_gauge = _meter.create_observable_gauge(
        name="tenderclaw.queue_depth",
        description="Number of busy sessions",
        unit="1",
        callbacks=[_queue_depth_callback],
    )

    logger.info("Metrics initialized for service: %s", service_name)
    return _meter_provider


def get_meter(name: str = "tenderclaw") -> Meter:
    """Get the configured meter instance."""
    global _meter
    if _meter is None:
        _meter = metrics.get_meter(name)
    return _meter


class Metrics:
    """Metrics helper class for easy access to instruments."""

    @staticmethod
    def increment_request(attributes: dict[str, Any] | None = None) -> None:
        """Increment request counter."""
        if request_counter:
            request_counter.add(1, attributes or {})

    @staticmethod
    def increment_tool_call(tool_name: str, success: bool = True) -> None:
        """Increment tool call counter."""
        if tool_call_counter:
            tool_call_counter.add(1, {
                "tool_name": tool_name,
                "success": str(success),
            })

    @staticmethod
    def increment_error(error_type: str, attributes: dict[str, Any] | None = None) -> None:
        """Increment error counter."""
        if error_counter:
            attrs = {"error_type": error_type}
            if attributes:
                attrs.update(attributes)
            error_counter.add(1, attrs)

    @staticmethod
    def record_response_time(duration_ms: float, attributes: dict[str, Any] | None = None) -> None:
        """Record response time histogram."""
        if response_time_histogram:
            attrs = attributes or {}
            response_time_histogram.record(duration_ms, attrs)

    @staticmethod
    def record_tokens(input_tokens: int, output_tokens: int, attributes: dict[str, Any] | None = None) -> None:
        """Record token count histogram."""
        if token_count_histogram:
            attrs = attributes or {}
            attrs["token_type"] = "input"
            token_count_histogram.record(input_tokens, attrs)
            attrs["token_type"] = "output"
            token_count_histogram.record(output_tokens, attrs)

    @staticmethod
    def record_cost(cost_usd: float, model: str, attributes: dict[str, Any] | None = None) -> None:
        """Record cost histogram."""
        if cost_histogram:
            attrs = {"model": model}
            if attributes:
                attrs.update(attributes)
            cost_histogram.record(cost_usd, attrs)


metrics_instance = Metrics()


def shutdown_metrics() -> None:
    """Shutdown the meter provider."""
    global _meter_provider
    if _meter_provider:
        _meter_provider.shutdown()
        logger.info("Metrics shutdown complete")
