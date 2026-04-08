"""Parity matrix generator (file-oriented) for TenderClaw port.

This utility is intentionally lightweight: it provides a skeleton to emit
a parity matrix mapping between source (Claw Code / OMX / OmO / Superpowers)
and TenderClaw target files. The real port requires careful file-by-file mapping
and testing contracts; this module helps keep the plan concrete during development.
"""

from __future__ import annotations


def generate_parity_matrix() -> list[dict[str, str]]:
    """Return a minimal parity matrix skeleton as a list of rows.

    Each row maps a functional area to a pair: (source, target).
    This is a scaffold and not a complete mapping.
    """
    # Minimal, illustrative skeleton to get momentum rolling
    return [
        {
            "area": "Runtime kernel",
            "source": "Claw Code",
            "target": "backend/runtime/session_state.py",
        },
        {
            "area": "Hook engine",
            "source": "oh-my-openagent + oh-my-codex",
            "target": "backend/hooks/engine.py",
        },
        {
            "area": "Skills native",
            "source": "oh-my-openagent",
            "target": "backend/skills/discovery.py",
        },
        {
            "area": "Planning/orchestration",
            "source": "oh-my-openagent",
            "target": "backend/planning/interviewer.py",
        },
    ]


def render_markdown(matrix: list[dict[str, str]]) -> str:
    """Render a Markdown table for the given matrix."""
    if not matrix:
        return ""
    lines = ["| Area | Source | Target |", "|---|---|---|"]
    for row in matrix:
        lines.append(f"| {row.get('area','')} | {row.get('source','')} | {row.get('target','')} |")
    return "\n".join(lines)


if __name__ == "__main__":
    m = generate_parity_matrix()
    print(render_markdown(m))
