from __future__ import annotations

from enum import Enum
import hashlib
import string


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
    _PERSON_FIRST_NAMES = [
        "Luca",
        "Giulia",
        "Marco",
        "Sara",
        "Davide",
        "Elena",
        "Paolo",
        "Chiara",
        "Matteo",
        "Anna",
    ]
    _PERSON_LAST_NAMES = [
        "Bianchi",
        "Esposito",
        "Romano",
        "Ricci",
        "Marini",
        "Conti",
        "Greco",
        "Lombardi",
        "Villa",
        "Ferri",
    ]
    _ORG_PREFIXES = [
        "Aurora",
        "Nexus",
        "Atlas",
        "Vector",
        "Orizzonte",
        "Ponte",
        "Sintesi",
        "Linea",
    ]
    _ORG_SUFFIXES = [
        "Consulting",
        "Solutions",
        "Engineering",
        "Group",
        "Partners",
        "Tech",
        "Advisory",
        "Services",
    ]
    _LOCATIONS = [
        "Torino",
        "Bologna",
        "Bari",
        "Verona",
        "Padova",
        "Parma",
        "Trieste",
        "Perugia",
        "Ravenna",
        "Modena",
    ]

    def _digest(self, entity_type: str, original_value: str, replacement: str) -> str:
        raw = f"{entity_type}|{original_value}|{replacement}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()

    def _index(self, digest: str, pool_size: int, offset: int = 0) -> int:
        return int(digest[offset : offset + 8], 16) % pool_size

    def _digits(self, digest: str, length: int) -> str:
        values = []
        for char in digest:
            values.append(str(int(char, 16) % 10))
            if len(values) == length:
                break
        return "".join(values)

    def _letters(self, digest: str, length: int) -> str:
        alphabet = string.ascii_uppercase
        values = []
        for char in digest:
            values.append(alphabet[int(char, 16) % len(alphabet)])
            if len(values) == length:
                break
        return "".join(values)

    def _alnum(self, digest: str, length: int) -> str:
        alphabet = string.ascii_uppercase + string.digits
        values = []
        for char in digest * ((length // len(digest)) + 1):
            values.append(alphabet[int(char, 16) % len(alphabet)])
            if len(values) == length:
                break
        return "".join(values)

    def _fake_person(self, digest: str) -> str:
        first = self._PERSON_FIRST_NAMES[self._index(digest, len(self._PERSON_FIRST_NAMES), 0)]
        last = self._PERSON_LAST_NAMES[self._index(digest, len(self._PERSON_LAST_NAMES), 8)]
        return f"{first} {last}"

    def _fake_org(self, digest: str) -> str:
        prefix = self._ORG_PREFIXES[self._index(digest, len(self._ORG_PREFIXES), 0)]
        suffix = self._ORG_SUFFIXES[self._index(digest, len(self._ORG_SUFFIXES), 8)]
        return f"{prefix} {suffix}"

    def _fake_location(self, digest: str) -> str:
        return self._LOCATIONS[self._index(digest, len(self._LOCATIONS), 0)]

    def _fake_codice_fiscale(self, digest: str) -> str:
        month_letters = "ABCDEHLMPRST"
        return (
            self._letters(digest, 6)
            + self._digits(digest[6:], 2)
            + month_letters[self._index(digest, len(month_letters), 10)]
            + self._digits(digest[10:], 2)
            + self._letters(digest[12:], 1)
            + self._digits(digest[13:], 3)
            + self._letters(digest[16:], 1)
        )

    def _fake_partita_iva(self, digest: str) -> str:
        return self._digits(digest, 11)

    def _fake_iban(self, digest: str) -> str:
        return f"IT{self._digits(digest, 2)}{self._letters(digest[2:], 1)}{self._alnum(digest[3:], 23)}"

    def _fake_cig(self, digest: str) -> str:
        return digest[:10]

    def replace(self, entity_type: str, original_value: str, replacement: str) -> str:
        digest = self._digest(entity_type, original_value, replacement)

        if entity_type == "PERSON":
            return self._fake_person(digest)
        if entity_type == "ORGANIZATION":
            return self._fake_org(digest)
        if entity_type == "LOCATION":
            return self._fake_location(digest)
        if entity_type == "CODICE_FISCALE":
            return self._fake_codice_fiscale(digest)
        if entity_type == "PARTITA_IVA":
            return self._fake_partita_iva(digest)
        if entity_type == "IBAN":
            return self._fake_iban(digest)
        if entity_type == "CIG":
            return self._fake_cig(digest)
        return replacement
