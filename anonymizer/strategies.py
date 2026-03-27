from __future__ import annotations

from enum import Enum


class AnonymizationStrategy(str, Enum):
    REDACTION = "redaction"
    FAKING = "faking"


ENTITY_LABELS: dict[str, str] = {
    "PERSON": "PERSONA",
    "PER": "PERSONA",
    "PERSONA": "PERSONA",
    "CODICE_FISCALE": "CF",
    "PARTITA_IVA": "PIVA",
    "IBAN": "IBAN",
    "CIG": "CIG",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "TEL",
    "ORGANIZATION": "ORGANIZZAZIONE",
    "LOCATION": "LUOGO",
}


class FakingOperator:
    def replace(self, entity_type: str, original_value: str, replacement: str) -> str:
        return replacement
