"""Plugin Base — definition for TenderClaw extensions.

Plugins can add:
- New Tools
- New Agents
- Custom Hook (pre/post Turn)
- New Channel listeners
"""

from __future__ import annotations

import abc
from typing import Any

from backend.agents.registry import AgentRegistry
from backend.tools.registry import ToolRegistry


class BasePlugin(abc.ABC):
    """Abstract base for all TenderClaw plugins."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique plugin identifier."""

    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"

    def on_register_tools(self, registry: ToolRegistry) -> None:
        """Callback to register new tools."""
        pass

    def on_register_agents(self, registry: AgentRegistry) -> None:
        """Callback to register new specialized agents."""
        pass

    def on_register_skills(self, skills_path: str) -> None:
        """Callback to register skills directories."""
        pass

    def on_init(self, config: dict[str, Any]) -> None:
        """Generic initialization callback."""
        pass


class PluginLoader:
    """Loads and manages loaded plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, BasePlugin] = {}

    def load_plugin(self, plugin: BasePlugin, config: dict[str, Any] = None) -> None:
        """Initialize and register a single plugin."""
        plugin.on_init(config or {})
        self._plugins[plugin.name] = plugin
        logger.info("Loaded plugin: %s (%s)", plugin.name, plugin.version)

    def register_all(self, tool_registry: ToolRegistry, agent_registry: AgentRegistry) -> None:
        """Notify all plugins to register their tools/agents."""
        for plugin in self._plugins.values():
            plugin.on_register_tools(tool_registry)
            plugin.on_register_agents(agent_registry)


import logging
logger = logging.getLogger("tenderclaw.plugins")

# Module-level instance
plugin_loader = PluginLoader()
