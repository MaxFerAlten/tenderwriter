"""Unit tests for the deterministic tender ontology service."""

from __future__ import annotations

import os
import unittest

from test_module_loaders import load_service_test_module

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


_ONTOLOGY = load_service_test_module("app.intelligence.ontology")
_SCHEMAS = load_service_test_module("app.intelligence.schemas")


class OntologyTaggingTests(unittest.TestCase):
    def test_tags_iso_certification_as_compliance_high(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "Il concorrente deve possedere la certificazione ISO 27001.",
            category="compliance",
            priority="must",
        )
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.COMPLIANCE)
        self.assertEqual(tag.ontology_subdomain, "certificazioni")
        self.assertEqual(tag.criticality, "high")
        self.assertEqual(tag.evidence_type, "certification")
        self.assertEqual(tag.owner_role, "legal")
        self.assertEqual(tag.evaluation_axis, "mandatory")
        self.assertGreaterEqual(tag.mapping_confidence, 0.6)

    def test_tags_fatturato_as_economic_finance(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "Il fatturato minimo degli ultimi tre esercizi deve essere pari a 2 milioni di euro.",
            priority="high",
        )
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.ECONOMICO_FINANZIARIO)
        self.assertEqual(tag.ontology_subdomain, "capacita_economica")
        self.assertEqual(tag.owner_role, "finance")
        self.assertEqual(tag.evidence_type, "financial_statement")

    def test_tags_sla_continuity_as_technical(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "Il fornitore deve garantire SLA di disponibilità del 99,9% e un piano di disaster recovery.",
            priority="must-have",
        )
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.TECNICO)
        self.assertEqual(tag.ontology_subdomain, "sla_continuita")
        self.assertEqual(tag.owner_role, "technical")

    def test_matches_diacritic_insensitive(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "E' richiesta continuità operativa costante con tempi di intervento entro 4 ore.",
        )
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.TECNICO)
        self.assertEqual(tag.ontology_subdomain, "sla_continuita")

    def test_maps_priority_to_criticality(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        high = service.tag_text("La certificazione ISO è obbligatoria.", priority="mandatory")
        medium = service.tag_text("La certificazione ISO è obbligatoria.", priority="should")
        low = service.tag_text("La certificazione ISO è obbligatoria.", priority="optional")
        self.assertEqual(high.criticality, "high")
        self.assertEqual(medium.criticality, "medium")
        self.assertEqual(low.criticality, "low")

    def test_returns_altro_fallback_when_no_rule_matches(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "This is a harmless descriptive sentence without procurement keywords.",
            priority="medium",
        )
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.ALTRO)
        self.assertEqual(tag.ontology_subdomain, "non_classificato")
        self.assertEqual(tag.owner_role, "unknown")
        self.assertLessEqual(tag.mapping_confidence, 0.2)
        self.assertEqual(tag.matched_rules, [])

    def test_premiale_category_promotes_scored_axis(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "Il concorrente ottiene punteggio aggiuntivo per proposte di innovazione.",
            category="premiale",
            priority="medium",
        )
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.PREMIALE)
        self.assertEqual(tag.evaluation_axis, "scored")

    def test_low_priority_non_premiale_maps_to_supporting(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        tag = service.tag_text(
            "E' gradito allegato descrittivo del modulo aggiuntivo.",
            priority="optional",
        )
        self.assertEqual(tag.evaluation_axis, "supporting")

    def test_tag_candidate_reads_summary_and_category(self) -> None:
        service = _ONTOLOGY.TenderOntologyService()
        candidate = {
            "summary": "Presentare garanzia provvisoria pari al 2% del valore a base d'asta.",
            "category": "economic",
            "priority": "high",
        }
        tag = service.tag_candidate(candidate)
        self.assertEqual(tag.ontology_domain, _SCHEMAS.OntologyDomain.ECONOMICO_FINANZIARIO)
        self.assertEqual(tag.ontology_subdomain, "capacita_economica")


class AttachOntologyToCandidatesTests(unittest.TestCase):
    def test_adds_ontology_block_without_mutating_input(self) -> None:
        candidates = [
            {
                "summary": "Il fornitore deve disporre di un piano di disaster recovery.",
                "priority": "high",
                "category": "technical",
            },
        ]
        snapshot = [dict(candidate) for candidate in candidates]

        enriched = _ONTOLOGY.attach_ontology_to_candidates(candidates)

        self.assertEqual(candidates, snapshot, "input candidates must not be mutated")
        self.assertEqual(len(enriched), 1)
        ontology = enriched[0]["ontology"]
        self.assertEqual(ontology["ontology_domain"], "tecnico")
        self.assertEqual(ontology["ontology_subdomain"], "sla_continuita")
        self.assertEqual(ontology["ontology_version"], _SCHEMAS.ONTOLOGY_VERSION)

    def test_preserves_candidates_without_requirement_text(self) -> None:
        candidates = [{"summary": "   ", "priority": "medium"}]
        enriched = _ONTOLOGY.attach_ontology_to_candidates(candidates)
        self.assertEqual(len(enriched), 1)
        self.assertNotIn("ontology", enriched[0])

    def test_is_idempotent(self) -> None:
        candidate = {
            "summary": "Il concorrente deve possedere certificazione ISO 9001.",
            "priority": "must",
        }
        first = _ONTOLOGY.attach_ontology_to_candidates([candidate])
        second = _ONTOLOGY.attach_ontology_to_candidates(first)
        self.assertEqual(first[0]["ontology"], second[0]["ontology"])


if __name__ == "__main__":
    unittest.main()
