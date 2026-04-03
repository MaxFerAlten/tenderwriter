from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from presidio_analyzer import Pattern, PatternRecognizer
except ImportError:  # pragma: no cover
    Pattern = None
    PatternRecognizer = None


@dataclass(slots=True)
class StructuredRecognizerResult:
    entity_type: str
    start: int
    end: int
    score: float
    text: str
    source: str


class RegexRecognizer:
    entity_type: str = ""
    score: float = 0.9
    source: str = "regex"
    pattern: re.Pattern[str]

    def analyze(self, text: str) -> list[StructuredRecognizerResult]:
        matches: list[StructuredRecognizerResult] = []
        for match in self.pattern.finditer(text):
            value = match.group(0)
            if not self.is_valid(value):
                continue
            matches.append(
                StructuredRecognizerResult(
                    entity_type=self.entity_type,
                    start=match.start(),
                    end=match.end(),
                    score=self.score,
                    text=value,
                    source=self.source,
                )
            )
        return matches

    def is_valid(self, value: str) -> bool:
        return bool(value)

    def build_presidio_recognizer(self, supported_language: str = "it"):
        if Pattern is None or PatternRecognizer is None:
            return None
        return PatternRecognizer(
            supported_entity=self.entity_type,
            name=type(self).__name__,
            supported_language=supported_language,
            patterns=[
                Pattern(
                    name=self.source.replace("regex:", ""),
                    regex=self.pattern.pattern,
                    score=self.score,
                )
            ],
        )


class CodiceFiscaleRecognizer(RegexRecognizer):
    entity_type = "CODICE_FISCALE"
    source = "regex:cf"
    pattern = re.compile(
        r"\b[A-Z]{6}[0-9]{2}[A-EHLMPRST][0-9]{2}[A-Z][0-9]{3}[A-Z]\b",
        re.IGNORECASE,
    )

    def is_valid(self, value: str) -> bool:
        return len(value) == 16 and value.isalnum()


class PartitaIvaRecognizer(RegexRecognizer):
    entity_type = "PARTITA_IVA"
    source = "regex:piva"
    pattern = re.compile(r"\b(?:IT)?([0-9]{11})\b", re.IGNORECASE)

    def is_valid(self, value: str) -> bool:
        digits = value[-11:]
        return len(digits) == 11 and digits.isdigit()


class IBANRecognizer(RegexRecognizer):
    entity_type = "IBAN"
    source = "regex:iban"
    pattern = re.compile(
        r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b",
        re.IGNORECASE,
    )

    def is_valid(self, value: str) -> bool:
        compact = value.replace(" ", "").upper()
        return compact.startswith("IT") and len(compact) == 27


class CIGRecognizer(RegexRecognizer):
    entity_type = "CIG"
    source = "regex:cig"
    pattern = re.compile(r"\b[0-9A-F]{10}\b", re.IGNORECASE)


class PersonNameRecognizer(RegexRecognizer):
    entity_type = "PERSON"
    source = "regex:person_name"
    score = 0.55
    pattern = re.compile(
        r"\b[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ']{1,30}(?:\s+[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ']{1,30}){1,3}\b"
    )
    _blocked_tokens = {
        "Cf",
        "Piva",
        "Iban",
        "Cig",
        "Spa",
        "Srl",
        "Via",
        "Viale",
        "Piazza",
        "Corso",
    }

    def is_valid(self, value: str) -> bool:
        tokens = [token.strip() for token in value.split() if token.strip()]
        if len(tokens) < 2 or len(tokens) > 4:
            return False
        if any(any(char.isdigit() for char in token) for token in tokens):
            return False
        if any(token in self._blocked_tokens for token in tokens):
            return False
        return True


def get_structured_recognizers(mask_cig: bool = False) -> list[RegexRecognizer]:
    recognizers: list[RegexRecognizer] = [
        PersonNameRecognizer(),
        CodiceFiscaleRecognizer(),
        PartitaIvaRecognizer(),
        IBANRecognizer(),
    ]
    if mask_cig:
        recognizers.append(CIGRecognizer())
    return recognizers


def get_presidio_recognizers(
    mask_cig: bool = False, supported_language: str = "it"
) -> list[PatternRecognizer]:
    recognizers = []
    for recognizer in get_structured_recognizers(mask_cig=mask_cig):
        presidio_recognizer = recognizer.build_presidio_recognizer(
            supported_language=supported_language
        )
        if presidio_recognizer is not None:
            recognizers.append(presidio_recognizer)
    return recognizers
