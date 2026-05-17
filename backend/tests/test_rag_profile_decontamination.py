from app.rag.internal_prompting import INTERNAL_PROMPTING_ROOT

FORBIDDEN_BASE_TERMS = (
    "OSCAT",
    "SCT",
    "CCTT",
    "RTPC",
    "Sistema Cloud Toscana",
    "San Piero a Quaracchi",
    "CO-LO-KW",
    "B33988ECF2",
    "Regione Toscana",
)
BASE_ASSETS = (
    "tender-overview",
    "tender-longform-synthesis",
    "retrieval-critical-coverage",
    "guardrail-lexicon",
    "guardrail-patterns",
    "engine-cleanup-patterns",
    "graph-retriever-messages",
    "context-quality",
)


def test_base_rag_assets_are_free_of_tender_specific_terms() -> None:
    violations = []
    for language in ("it", "en"):
        for asset in BASE_ASSETS:
            text = (INTERNAL_PROMPTING_ROOT / language / f"{asset}.md").read_text(
                encoding="utf-8"
            )
            low = text.casefold()
            for term in FORBIDDEN_BASE_TERMS:
                if term.casefold() in low:
                    violations.append(f"{language}/{asset}.md :: {term}")
    assert not violations, "Toscana leakage in base assets:\n" + "\n".join(violations)


def test_oscat_profile_carries_the_toscana_knowledge() -> None:
    from app.rag.procedure_profiles import OSCAT_SCT_TOSCANA_PROFILE as P

    flat = " ".join(
        [*P.procedure_anchors["OSCAT"], *P.procedure_anchors["SCT"], *P.contamination_markers]
    ).casefold()
    for term in ("oscat", "sct", "cctt", "rtpc"):
        assert term in flat


def test_no_oscat_sct_string_literals_in_core_engine_paths() -> None:
    import pathlib

    root = pathlib.Path("app/rag")
    offenders = []
    for path in (root / "engine.py", root / "procedure_guardrails.py", root / "localization.py"):
        src = path.read_text(encoding="utf-8")
        for token in ('"OSCAT"', "'OSCAT'", '"SCT"', "'SCT'"):
            if token in src:
                offenders.append(f"{path} :: {token}")
    assert not offenders, "Hard-coded procedure label literals remain:\n" + "\n".join(offenders)
