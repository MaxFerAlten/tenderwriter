from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from config import Settings
from recognizers import (
    StructuredRecognizerResult,
    get_presidio_recognizers,
    get_structured_recognizers,
)
from strategies import AnonymizationStrategy, ENTITY_LABELS, FakingOperator
from vault import RedisVault

try:
    import spacy
except ImportError:  # pragma: no cover
    spacy = None

try:
    from presidio_analyzer import (
        AnalyzerEngine as PresidioAnalyzerEngine,
        RecognizerRegistry,
        RecognizerResult,
    )
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import SpacyRecognizer
except ImportError:  # pragma: no cover
    NlpEngineProvider = None
    PresidioAnalyzerEngine = None
    RecognizerRegistry = None
    RecognizerResult = None
    SpacyRecognizer = None


@dataclass(slots=True)
class Detection:
    entity_type: str
    start: int
    end: int
    text: str
    score: float
    source: str


@dataclass(slots=True)
class AnonymizedChunk:
    text: str
    anonymized_text: str
    detections: list[Detection]
    replacements: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "anonymized_text": self.anonymized_text,
            "detections": [asdict(item) for item in self.detections],
            "replacements": dict(self.replacements),
        }


class AnonymizerEngine:
    def __init__(self, settings: Settings, vault: RedisVault):
        self.settings = settings
        self.vault = vault
        self.faker = FakingOperator()
        self._spacy_model_name = self._resolve_spacy_model_name()
        self._analyzer = self._load_presidio_analyzer()
        self._nlp = self._load_spacy_model() if self._analyzer is None else None

    def _resolve_spacy_model_name(self) -> str | None:
        if spacy is None:
            return None
        for model_name in ("it_core_news_lg", "it_core_news_md", "it_core_news_sm"):
            try:
                spacy.load(model_name)
                return model_name
            except OSError:
                continue
        return None

    def _load_presidio_analyzer(self):
        if self.settings.ner_backend != "presidio_spacy":
            return None
        if (
            PresidioAnalyzerEngine is None
            or NlpEngineProvider is None
            or RecognizerRegistry is None
            or SpacyRecognizer is None
            or self._spacy_model_name is None
        ):
            return None

        nlp_configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "it", "model_name": self._spacy_model_name}],
        }
        try:
            provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
            nlp_engine = provider.create_engine()
            registry = RecognizerRegistry(supported_languages=["it"])
            registry.add_recognizer(
                SpacyRecognizer(
                    supported_language="it",
                    supported_entities=["PERSON", "ORGANIZATION", "LOCATION"],
                )
            )
            for recognizer in get_presidio_recognizers(mask_cig=True, supported_language="it"):
                registry.add_recognizer(recognizer)
            return PresidioAnalyzerEngine(
                registry=registry,
                nlp_engine=nlp_engine,
                supported_languages=["it"],
            )
        except Exception:  # pragma: no cover - graceful fallback when runtime deps are partial
            return None

    def _load_spacy_model(self):
        if spacy is None or self._spacy_model_name is None:
            return None
        try:
            return spacy.load(self._spacy_model_name)
        except OSError:
            return None

    def _supported_entities(self, mask_cig: bool) -> list[str]:
        entities = [
            "PERSON",
            "ORGANIZATION",
            "LOCATION",
            "CODICE_FISCALE",
            "PARTITA_IVA",
            "IBAN",
        ]
        if mask_cig:
            entities.append("CIG")
        return entities

    def _analysis_entities(self, entities: list[str] | None, mask_cig: bool) -> list[str]:
        supported = self._supported_entities(mask_cig=mask_cig)
        if not entities:
            return supported
        supported_set = set(supported)
        return [entity for entity in entities if entity in supported_set]

    def _detect_entities(
        self,
        text: str,
        min_confidence: float,
        entities: list[str] | None,
        mask_cig: bool,
    ) -> list[Detection]:
        analysis_entities = self._analysis_entities(entities=entities, mask_cig=mask_cig)
        if not analysis_entities:
            return []

        detections = self._detect_with_presidio(
            text=text,
            min_confidence=min_confidence,
            entities=analysis_entities,
        )
        if not detections:
            detections = self._detect_with_fallback(
                text=text,
                min_confidence=min_confidence,
                entities=analysis_entities,
                mask_cig=mask_cig,
            )
        return self._deduplicate(text, detections)

    def _detect_with_presidio(
        self,
        text: str,
        min_confidence: float,
        entities: list[str],
    ) -> list[Detection]:
        if self._analyzer is None:
            return []

        results = self._analyzer.analyze(
            text=text,
            language="it",
            entities=entities,
            score_threshold=min_confidence,
        )
        detections: list[Detection] = []
        for result in results:
            detection = self._presidio_to_detection(text=text, result=result)
            if detection is None:
                continue
            if not self._is_reasonable_spacy_entity(detection.entity_type, detection.text):
                continue
            detections.append(detection)
        return detections

    def _detect_with_fallback(
        self,
        text: str,
        min_confidence: float,
        entities: list[str],
        mask_cig: bool,
    ) -> list[Detection]:
        detections: list[Detection] = []
        allowed_entities = set(entities)

        for recognizer in get_structured_recognizers(mask_cig=mask_cig):
            if recognizer.entity_type not in allowed_entities:
                continue
            for result in recognizer.analyze(text):
                if result.score < min_confidence:
                    continue
                detections.append(self._to_detection(result))

        if self._nlp is not None:
            doc = self._nlp(text)
            for ent in doc.ents:
                entity_type = self._map_spacy_label(ent.label_)
                if entity_type is None or entity_type not in allowed_entities:
                    continue
                if not self._is_reasonable_spacy_entity(entity_type, ent.text):
                    continue
                detections.append(
                    Detection(
                        entity_type=entity_type,
                        start=ent.start_char,
                        end=ent.end_char,
                        text=ent.text,
                        score=0.85,
                        source=f"spacy:{ent.label_}",
                    )
                )
        return detections

    def _map_spacy_label(self, label: str) -> str | None:
        mapping = {
            "PER": "PERSON",
            "PERSON": "PERSON",
            "ORG": "ORGANIZATION",
            "LOC": "LOCATION",
            "GPE": "LOCATION",
        }
        return mapping.get(label)

    def _to_detection(self, result: StructuredRecognizerResult) -> Detection:
        return Detection(
            entity_type=result.entity_type,
            start=result.start,
            end=result.end,
            text=result.text,
            score=result.score,
            source=result.source,
        )

    def _presidio_to_detection(
        self, text: str, result: RecognizerResult | Any
    ) -> Detection | None:
        snippet = text[result.start : result.end]
        if not snippet.strip():
            return None
        metadata = getattr(result, "recognition_metadata", {}) or {}
        recognizer_name = metadata.get("recognizer_name") or result.entity_type
        return Detection(
            entity_type=result.entity_type,
            start=result.start,
            end=result.end,
            text=snippet,
            score=result.score,
            source=f"presidio:{recognizer_name}",
        )

    def _is_reasonable_spacy_entity(self, entity_type: str, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return False
        if entity_type == "PERSON":
            if any(char.isdigit() for char in cleaned):
                return False
            token_count = len(cleaned.split())
            return 1 <= token_count <= 4
        return True

    def _deduplicate(self, text: str, detections: list[Detection]) -> list[Detection]:
        ordered = sorted(
            detections,
            key=lambda item: (
                self._source_priority(item.source),
                -(item.end - item.start),
                -item.score,
                item.start,
            ),
        )
        chosen: list[Detection] = []
        for detection in ordered:
            if not detection.text.strip():
                continue
            overlap = False
            for existing in chosen:
                if detection.start < existing.end and detection.end > existing.start:
                    overlap = True
                    break
            if not overlap:
                chosen.append(detection)
        return sorted(chosen, key=lambda item: item.start)

    def _source_priority(self, source: str) -> int:
        return 1 if "SpacyRecognizer" in source or source.startswith("spacy:") else 0

    def _build_placeholder(
        self,
        entity_type: str,
        original_value: str,
        reverse_mapping: dict[str, str],
        counters: dict[str, int],
    ) -> str:
        for placeholder, value in reverse_mapping.items():
            if value == original_value:
                return placeholder

        label = ENTITY_LABELS.get(entity_type, entity_type.upper())
        counters[label] += 1
        return f"[{label}_{counters[label]}]"

    async def anonymize_text(
        self,
        text: str,
        session_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime_config = self.settings.default_config()
        runtime_config.update(await self.vault.load_config())
        if config:
            runtime_config.update(config)

        strategy = AnonymizationStrategy(runtime_config["strategy"])
        configured_entities = list(runtime_config.get("entities") or [])
        detections = self._detect_entities(
            text=text,
            min_confidence=float(runtime_config["min_confidence"]),
            entities=configured_entities,
            mask_cig=bool(runtime_config.get("mask_cig", False)),
        )
        allowed_entities = set(configured_entities)
        if allowed_entities:
            detections = [item for item in detections if item.entity_type in allowed_entities]

        if session_id is None:
            session_id = await self.vault.create_session_id()

        stored_session = await self.vault.get_session(session_id)
        reverse_mapping = dict((stored_session or {}).get("mapping") or {})
        alias_mapping = dict((((stored_session or {}).get("metadata") or {}).get("aliases") or {}))
        counters: dict[str, int] = defaultdict(int)
        for placeholder in reverse_mapping:
            inside = placeholder.strip("[]").rsplit("_", 1)
            if len(inside) == 2 and inside[1].isdigit():
                counters[inside[0]] = max(counters[inside[0]], int(inside[1]))

        replacements: dict[str, str] = {}
        output_parts: list[str] = []
        cursor = 0

        for detection in detections:
            placeholder = self._build_placeholder(
                detection.entity_type, detection.text, reverse_mapping, counters
            )
            reverse_mapping[placeholder] = detection.text
            replacement = placeholder
            if strategy == AnonymizationStrategy.FAKING:
                replacement = self.faker.replace(detection.entity_type, detection.text, placeholder)
                alias_mapping[replacement] = detection.text
            replacements[detection.text] = replacement
            output_parts.append(text[cursor : detection.start])
            output_parts.append(replacement)
            cursor = detection.end

        output_parts.append(text[cursor:])
        anonymized_text = "".join(output_parts)
        chunk = AnonymizedChunk(
            text=text,
            anonymized_text=anonymized_text,
            detections=detections,
            replacements=replacements,
        )

        ttl_seconds = int(runtime_config["ttl_seconds"])
        await self.vault.store_session(
            session_id=session_id,
            mapping=reverse_mapping,
            metadata={"config": runtime_config, "aliases": alias_mapping},
            ttl_seconds=ttl_seconds,
        )
        await self.vault.update_stats(
            requests=1,
            sessions=1 if stored_session is None else 0,
            entities_detected=len(detections),
            faking_requests=1 if strategy == AnonymizationStrategy.FAKING else 0,
        )

        return {
            "session_id": session_id,
            "config": runtime_config,
            "chunk": chunk.as_dict(),
            "mapping": reverse_mapping,
        }

    async def anonymize_chunks(
        self,
        chunks: list[str],
        session_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_session_id = session_id or await self.vault.create_session_id()
        chunk_results = []
        for chunk in chunks:
            result = await self.anonymize_text(
                text=chunk, session_id=active_session_id, config=config
            )
            chunk_results.append(result["chunk"])
        session = await self.vault.get_session(active_session_id)
        runtime_config = self.settings.default_config()
        runtime_config.update(await self.vault.load_config())
        if config:
            runtime_config.update(config)
        return {
            "session_id": active_session_id,
            "config": runtime_config,
            "chunks": chunk_results,
            "mapping": dict((session or {}).get("mapping") or {}),
        }

    async def deanonymize_text(self, text: str, session_id: str) -> dict[str, Any]:
        session = await self.vault.get_session(session_id)
        if session is None:
            raise KeyError("session not found")

        restored = text
        mapping = dict(session.get("mapping") or {})
        aliases = dict(((session.get("metadata") or {}).get("aliases") or {}))
        for placeholder, original_value in sorted(
            {**mapping, **aliases}.items(),
            key=lambda item: -len(item[0]),
        ):
            restored = restored.replace(placeholder, original_value)

        await self.vault.update_stats(deanonymize_requests=1)
        return {
            "session_id": session_id,
            "text": restored,
            "mapping_size": len(mapping),
        }
