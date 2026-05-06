"""Tool registry for the TenderWriter intelligence layer.

The registry holds *read-only* tools that answer questions about a tender.
Tools must never mutate workflow, review, rework, or compliance gate state —
they produce structured JSON from existing state and the KPI reason engine.

MiroFish's ReportAgent demonstrated the value of a small, stable set of
tools (InsightForge, PanoramaSearch, QuickSearch, InterviewSubAgent) that
can be introspected and composed. We keep the same pattern but specialise
the tools to procurement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class IntelligenceTool(Protocol):
    """Protocol every registered tool must implement.

    ``name`` is the stable slug used for dispatch (``coverage_analyzer`` …).
    ``description`` is a one-line English blurb shown to the orchestrator and
    the UI. ``run`` must return a plain JSON-serializable dict and must not
    write to the database.
    """

    name: str
    description: str

    async def run(
        self,
        db: AsyncSession,
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    input_keys: tuple[str, ...] = field(default_factory=tuple)


class TenderToolRegistry:
    """In-process registry of read-only intelligence tools.

    The registry is intentionally minimal. It is process-local, not thread
    safe across concurrent writes, and meant to be populated once at import
    time. Duplicate registrations raise, so startup ordering bugs surface
    immediately instead of silently overwriting behaviour.
    """

    def __init__(self) -> None:
        self._tools: dict[str, IntelligenceTool] = {}

    def register(self, tool: IntelligenceTool) -> IntelligenceTool:
        name = getattr(tool, "name", None)
        if not name or not isinstance(name, str):
            raise ValueError("Intelligence tool must expose a non-empty string 'name'")
        if name in self._tools:
            raise ValueError(f"Intelligence tool '{name}' is already registered")
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> IntelligenceTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"No intelligence tool registered under '{name}'") from exc

    def contains(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[ToolDescriptor]:
        descriptors: list[ToolDescriptor] = []
        for name in sorted(self._tools):
            tool = self._tools[name]
            input_keys = tuple(getattr(tool, "input_keys", ()) or ())
            descriptors.append(
                ToolDescriptor(
                    name=name,
                    description=getattr(tool, "description", "") or "",
                    input_keys=input_keys,
                )
            )
        return descriptors

    async def run(
        self,
        name: str,
        db: AsyncSession,
        inputs: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool = self.get(name)
        return await tool.run(db, dict(inputs or {}))
