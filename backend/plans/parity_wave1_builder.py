"""Wave 1 Parity Builder (expanded).

This module provides a concrete, expanded parity matrix for Wave 1, mapping
key TenderClaw files to source components. It also offers a writer to persist
the matrix as Markdown for documentation and tracking.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict


def generate_parity_matrix() -> List[Dict[str, str]]:
    return [
        {"area": "Runtime Kernel", "source": "Claw Code", "target": "backend/runtime/conversation_runtime.py"},
        {"area": "Runtime Kernel", "source": "Claw Code", "target": "backend/runtime/prompt_builder.py"},
        {"area": "Runtime Kernel", "source": "Claw Code", "target": "backend/runtime/usage_tracker.py"},
        {"area": "Runtime Kernel", "source": "Claw Code", "target": "backend/runtime/context_compactor.py"},
        {"area": "Runtime Kernel", "source": "Claw Code", "target": "backend/runtime/permissions_policy.py"},
        {"area": "Hook Engine", "source": "Hook Engine Core", "target": "backend/hooks/engine.py"},
        {"area": "Hook Dispatcher", "source": "Hook Dispatcher", "target": "backend/hooks/dispatcher.py"},
        {"area": "Skills Loader", "source": "Claw Code", "target": "backend/core/skills.py"},
        {"area": "Skills Loader", "source": "Claw Code", "target": "backend/skills/discovery.py"},
        {"area": "Orchestration", "source": "Claw Code", "target": "backend/orchestration/pipeline.py"},
        {"area": "Orchestration", "source": "Claw Code", "target": "backend/orchestration/intent_gate.py"},
        {"area": "Planning/Execution", "source": "Claw Code", "target": "backend/orchestration/pipeline.py"},
        {"area": "API Gate / HUD", "source": "Claw Code", "target": "backend/api/gateway.py"},
        {"area": "OAuth/Provider", "source": "Claw Code", "target": "backend/runtime/oauth.py"},
        {"area": "Provider Client", "source": "Claw Code", "target": "backend/runtime/provider_client.py"},
        {"area": "Tools/Registry", "source": "Claw Code", "target": "backend/tools/registry.py"},
    ]


def render_markdown(matrix: List[Dict[str, str]]) -> str:
    if not matrix:
        return ""
    lines = ["| Area | Source | Target |", "|---|---|---|"]
    for row in matrix:
        lines.append(f"| {row.get('area','')} | {row.get('source','')} | {row.get('target','')} |")
    return "\n".join(lines)


def write_to_file(path: str = "backend/plans/parity_matrix_wave1.md") -> str:
    matrix = generate_parity_matrix()
    md = render_markdown(matrix)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    return str(p.resolve())


if __name__ == "__main__":
    location = write_to_file()
    print(f"Parity matrix Wave1 written to: {location}")
