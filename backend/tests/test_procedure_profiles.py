from app.rag.procedure_profiles import (
    BASE_PROCUREMENT_PROFILE,
    OSCAT_SCT_TOSCANA_PROFILE,
    active_critical_coverage_queries,
    active_procedure_anchors,
    resolve_active_profiles,
)


def test_base_profile_is_always_active_and_oscat_is_not_default() -> None:
    profiles = resolve_active_profiles("Analizza questa gara", chunk_texts=(), explicit_profile_ids=())
    ids = {p.profile_id for p in profiles}
    assert "base_procurement_it" in ids
    assert "oscat_sct_toscana" not in ids


def test_explicit_profile_id_activates_oscat() -> None:
    profiles = resolve_active_profiles(
        "Analizza questa gara", chunk_texts=(), explicit_profile_ids=("oscat_sct_toscana",)
    )
    assert any(p.profile_id == "oscat_sct_toscana" for p in profiles)


def test_query_text_anchor_activates_oscat() -> None:
    profiles = resolve_active_profiles(
        "Descrivi la gara OSCAT", chunk_texts=(), explicit_profile_ids=()
    )
    assert any(p.profile_id == "oscat_sct_toscana" for p in profiles)


def test_chunk_anchor_activates_oscat() -> None:
    profiles = resolve_active_profiles(
        "Descrivi questa gara",
        chunk_texts=("Servizi GitLab, Sonar, Nexus, Vulnerability Assessment per OSCAT",),
        explicit_profile_ids=(),
    )
    assert any(p.profile_id == "oscat_sct_toscana" for p in profiles)


def test_base_anchors_have_no_toscana_terms() -> None:
    anchors = active_procedure_anchors(())  # empty profile tuple (base has no anchors)
    flat = " ".join(t for v in anchors.values() for t in v).casefold()
    for forbidden in ("oscat", "sct", "cctt", "rtpc", "toscana", "san piero", "co-lo-kw"):
        assert forbidden not in flat


def test_oscat_profile_exposes_expected_labels_and_queries() -> None:
    assert OSCAT_SCT_TOSCANA_PROFILE.main_label == "OSCAT"
    assert OSCAT_SCT_TOSCANA_PROFILE.referenced_label == "SCT"
    anchors = active_procedure_anchors((OSCAT_SCT_TOSCANA_PROFILE,))
    assert "oscat" in {a.casefold() for a in anchors["OSCAT"]}
    assert "cctt" in {a.casefold() for a in anchors["SCT"]}
    it_q = active_critical_coverage_queries((OSCAT_SCT_TOSCANA_PROFILE,), language="it")
    assert any("OSCAT CIG" in q for q in it_q)
    en_q = active_critical_coverage_queries((OSCAT_SCT_TOSCANA_PROFILE,), language="en")
    assert any("OSCAT CIG" in q for q in en_q)


def test_base_profile_default_flag() -> None:
    assert BASE_PROCUREMENT_PROFILE.enabled_by_default is True
    assert OSCAT_SCT_TOSCANA_PROFILE.enabled_by_default is False
