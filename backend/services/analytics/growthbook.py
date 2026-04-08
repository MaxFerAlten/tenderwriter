"""Feature flags using GrowthBook patterns (simplified, local)."""

from dataclasses import dataclass
from typing import Callable, Any
import json
from pathlib import Path


@dataclass
class FeatureFlag:
    name: str
    enabled: bool
    value: Any = None


class FeatureFlagSystem:
    """Simple feature flag system."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or Path(".tenderclaw/feature_flags.json")
        self._flags: dict[str, FeatureFlag] = {}
        self._listeners: list[Callable[[str, bool], None]] = []
        self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                    for name, flag in data.items():
                        self._flags[name] = FeatureFlag(
                            name=name,
                            enabled=flag.get("enabled", False),
                            value=flag.get("value"),
                        )
            except json.JSONDecodeError:
                pass

    def _save(self):
        data = {
            name: {"enabled": f.enabled, "value": f.value}
            for name, f in self._flags.items()
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, name: str, default: bool = False) -> bool:
        """Get feature flag value."""
        flag = self._flags.get(name)
        return flag.enabled if flag else default

    def set(self, name: str, enabled: bool, value: Any = None):
        """Set feature flag."""
        self._flags[name] = FeatureFlag(name=name, enabled=enabled, value=value)
        self._save()
        for listener in self._listeners:
            listener(name, enabled)

    def on_change(self, listener: Callable[[str, bool], None]):
        """Register listener for flag changes."""
        self._listeners.append(listener)

    def is_enabled(self, feature: str) -> bool:
        """Check if feature is enabled (alias for get)."""
        return self.get(feature)


feature_flags = FeatureFlagSystem()

FEATURE_VOICE_MODE = "voice_mode"
FEATURE_BUDDY_COMPANION = "buddy_companion"
FEATURE_REMOTE_BRIDGE = "remote_bridge"
FEATURE_VIM_MODE = "vim_mode"
FEATURE_ADVANCED_ANALYTICS = "advanced_analytics"