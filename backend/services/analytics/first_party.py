"""First-party event logger for TenderClaw."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any
from pathlib import Path
import json
import uuid


@dataclass
class Event:
    id: str
    name: str
    timestamp: datetime
    properties: dict[str, Any]
    user_id: str | None
    session_id: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "properties": self.properties,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }


class FirstPartyEventLogger:
    """Log events to local storage for privacy-first analytics."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or Path(".tenderclaw/analytics")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        event_name: str,
        properties: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> Event:
        """Log an event."""
        event = Event(
            id=str(uuid.uuid4()),
            name=event_name,
            timestamp=datetime.utcnow(),
            properties=properties or {},
            user_id=user_id,
            session_id=session_id,
        )

        date_str = event.timestamp.strftime("%Y-%m-%d")
        file_path = self.storage_dir / f"events_{date_str}.jsonl"

        with open(file_path, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        return event

    def get_events(
        self,
        date: str | None = None,
        event_name: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Retrieve logged events."""
        if date:
            file_path = self.storage_dir / f"events_{date}.jsonl"
            if not file_path.exists():
                return []
            files = [file_path]
        else:
            files = sorted(self.storage_dir.glob("events_*.jsonl"), reverse=True)

        events = []
        for f in files:
            with open(f) as fp:
                for line in fp:
                    try:
                        data = json.loads(line)
                        if event_name and data["name"] != event_name:
                            continue
                        events.append(Event(**data))
                        if len(events) >= limit:
                            return events
                    except json.JSONDecodeError:
                        continue

        return events


event_logger = FirstPartyEventLogger()