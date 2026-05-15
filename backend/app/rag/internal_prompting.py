"""Load retrieval-specialization assets from internal Markdown prompts."""

from __future__ import annotations

import os
from pathlib import Path

_SUPPORTED_LANGUAGES = frozenset({"it", "en"})


def _candidate_internal_prompting_roots() -> tuple[Path, ...]:
    module_path = Path(__file__).resolve()
    return (
        module_path.parent / "internalprompting",
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


def _read_asset(
    asset_name: str,
    *,
    language: str,
    root: Path | None = None,
) -> str:
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError("language must be 'it' or 'en'")
    base = root or INTERNAL_PROMPTING_ROOT
    path = base / language / f"{asset_name}.md"
    return path.read_text(encoding="utf-8")


def load_retrieval_query_variants(
    asset_name: str,
    *,
    language: str = "it",
    root: Path | None = None,
) -> tuple[str, ...]:
    return load_keyword_group(
        asset_name,
        "Query Variants",
        language=language,
        root=root,
    )


def load_prompt_template(
    asset_name: str,
    *,
    language: str = "it",
    root: Path | None = None,
) -> str:
    """Return the prompt body delimited by ``<!-- prompt:start -->`` markers.

    Whitespace inside the markers is preserved verbatim except for a single
    leading/trailing newline that the markers themselves introduce.
    """

    text = _read_asset(asset_name, language=language, root=root)
    start_marker = "<!-- prompt:start -->"
    end_marker = "<!-- prompt:end -->"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            f"prompt block not found in asset '{asset_name}' (language={language})"
        )
    body = text[start + len(start_marker) : end]
    return body.strip("\n")


def load_localized_messages(
    asset_name: str,
    *,
    language: str = "it",
    root: Path | None = None,
) -> dict[str, str]:
    """Parse a ``## Messages`` section into a ``key: value`` mapping.

    Lines outside the section are ignored. Lines without a colon are skipped.
    """

    text = _read_asset(asset_name, language=language, root=root)
    messages: dict[str, str] = {}
    inside = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped == "## Messages":
            inside = True
            continue
        if inside and stripped.startswith("## "):
            break
        if not inside or not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip().lstrip("- ").strip()
        value = value.strip()
        if key:
            messages[key] = value
    if not messages:
        raise ValueError(
            f"No messages found in asset '{asset_name}' (language={language})"
        )
    return messages


def load_keyword_group(
    asset_name: str,
    group_name: str,
    *,
    language: str = "it",
    root: Path | None = None,
) -> tuple[str, ...]:
    """Parse a ``## <group_name>`` section as a bullet list of strings."""

    text = _read_asset(asset_name, language=language, root=root)
    target_heading = f"## {group_name}"
    items: list[str] = []
    inside = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == target_heading:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.startswith("- "):
            value = line[2:].strip()
            if value:
                items.append(value)
    if not items:
        raise ValueError(
            f"No items found in group '{group_name}' of asset "
            f"'{asset_name}' (language={language})"
        )
    return tuple(items)


def default_language() -> str:
    """Resolve the default localization language for engine assets.

    Resolution order:
      1. ``TENDERWRITER_LOCALE`` environment variable (lets runtime overrides
         and tests re-route without re-instantiating ``Settings``).
      2. ``settings.default_locale`` (whatever ``Settings`` captured at startup).
      3. ``"it"`` as the final fallback. Unknown values collapse back to it.
    """

    candidate: str | None = os.environ.get("TENDERWRITER_LOCALE")
    if not candidate:
        try:
            from app.config import settings

            candidate = getattr(settings, "default_locale", None)
        except Exception:  # pragma: no cover - settings import is defensive
            candidate = None
    if not candidate:
        return "it"
    normalized = str(candidate).lower().strip()
    return normalized if normalized in _SUPPORTED_LANGUAGES else "it"
