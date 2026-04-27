"""Load retrieval-specialization assets from internal Markdown prompts."""

from __future__ import annotations

from pathlib import Path


def _candidate_internal_prompting_roots() -> tuple[Path, ...]:
    module_path = Path(__file__).resolve()
    return (
        module_path.parents[3] / "internalprompting",
        module_path.parents[2] / "internalprompting",
        Path("/internalprompting"),
    )


def _internal_prompting_root() -> Path:
    for candidate in _candidate_internal_prompting_roots():
        if candidate.exists():
            return candidate
    return _candidate_internal_prompting_roots()[0]


INTERNAL_PROMPTING_ROOT = _internal_prompting_root()


def load_retrieval_query_variants(
    asset_name: str,
    *,
    language: str = "it",
) -> tuple[str, ...]:
    if language not in {"it", "en"}:
        raise ValueError("language must be 'it' or 'en'")

    path = INTERNAL_PROMPTING_ROOT / language / f"{asset_name}.md"
    text = path.read_text(encoding="utf-8")
    variants: list[str] = []
    inside_variants = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "## Query Variants":
            inside_variants = True
            continue
        if inside_variants and line.startswith("## "):
            break
        if inside_variants and line.startswith("- "):
            value = line[2:].strip()
            if value:
                variants.append(value)

    if not variants:
        raise ValueError(f"No query variants found in {path}")
    return tuple(variants)
