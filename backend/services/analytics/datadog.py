"""Datadog integration for TenderClaw analytics."""

import logging
from typing import Any
import json
import time

logger = logging.getLogger("tenderclaw.analytics")


class DatadogLogger:
    """Send logs/events to Datadog HTTP intake."""

    def __init__(
        self,
        api_key: str | None = None,
        service_name: str = "tenderclaw",
        intake_url: str = "https://http-intake.logs.datadoghq.com/v1/input",
    ):
        self.api_key = api_key
        self.service_name = service_name
        self.intake_url = intake_url
        self._enabled = bool(api_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _post(self, payload: dict[str, Any]) -> bool:
        """Send payload to Datadog."""
        if not self._enabled:
            return False

        try:
            import urllib.request

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.intake_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "DD-API-KEY": self.api_key or "",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.warning("Failed to send to Datadog: %s", exc)
            return False

    def log(
        self,
        message: str,
        level: str = "info",
        tags: list[str] | None = None,
        **extra: Any,
    ) -> bool:
        """Send a log message to Datadog."""
        payload = {
            "message": message,
            "service": self.service_name,
            "ddsource": "tenderclaw",
            "status": level,
            "tags": tags or [],
            "timestamp": int(time.time() * 1000),
            **extra,
        }
        return self._post(payload)

    def log_event(
        self,
        event_name: str,
        properties: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Log a custom event."""
        return self.log(
            message=f"Event: {event_name}",
            tags=["event", f"event_name:{event_name}"] + (tags or []),
            event_name=event_name,
            properties=properties or {},
        )


dd_logger = DatadogLogger()