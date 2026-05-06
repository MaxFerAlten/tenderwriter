"""
TenderWriter — Document Ingestion Pipeline

Processes uploaded documents (PDF, DOCX, PPTX) through:
1. Parsing (extract text, tables, metadata)
2. Chunking (semantic or fixed-size)
3. Embedding + vector indexing (Qdrant)
4. BM25 indexing (sparse retriever)
5. Entity extraction + knowledge graph building (Neo4j)
"""

from __future__ import annotations

import hashlib
import inspect
import os
import re
import unicodedata

import structlog

from app.config import settings
from app.ingestion.document_quality import document_quality_metadata
from app.services.tender_document_requirement_extractor import (
    extract_tender_participation_requirements,
)

logger = structlog.get_logger()


def _extract_first_json_object(text: str) -> dict | None:
    """Extract the first valid JSON object from text containing mixed content.

    Tries each '{' position from first to last, returning the first
    successfully parsed dict. This prefers the outermost/largest object
    and naturally skips incomplete fragments.
    """
    import json

    starts = [i for i, c in enumerate(text) if c == "{"]
    if not starts:
        return None

    decoder = json.JSONDecoder()
    for start in starts:
        try:
            obj, _ = decoder.raw_decode(text, start)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    return None


_REQUIREMENT_SECTION_KEYWORDS = (
    "requirements",
    "requirement",
    "mandatory",
    "eligibility",
    "compliance",
    "technical specification",
    "technical requirements",
    "requisiti",
    "requisito",
    "obblighi",
    "conformita",
    "conformita'",
)
_REQUIREMENT_LINE_KEYWORDS = (
    " must ",
    " shall ",
    " mandatory",
    " required",
    " requirement",
    " provide",
    " include",
    " comply",
    " certification",
    "deve",
    "dovra",
    "dovranno",
    "obbligatorio",
    "richiesto",
    "fornire",
    "includere",
    "conforme",
)
_STRONG_REQUIREMENT_ACTION_KEYWORDS = (
    " provide",
    " submit",
    " include",
    " attach",
    " comply",
    " ensure",
    " maintain",
    " certify",
    " demonstrate",
    " describe",
    " deliver",
    " present",
    " possess",
    " guarantee",
    " implement",
    " deploy",
    " integrate",
    " support",
    " furnish",
    "fornire",
    "presentare",
    "includere",
    "allegare",
    "rispettare",
    "garantire",
    "mantenere",
    "dimostrare",
    "possedere",
    "consegnare",
    "assicurare",
    "certificare",
    "indicare",
    "descrivere",
    "implementare",
    "integrare",
    "supportare",
)
_REQUIREMENT_OBJECT_KEYWORDS = (
    " certification",
    " certificate",
    " iso ",
    " insurance",
    " annex",
    " declaration",
    " statement",
    " evidence",
    " experience",
    " reference",
    " references",
    " plan",
    " timeline",
    " milestone",
    " sla",
    " service level",
    " support",
    " maintenance",
    " security",
    " continuity",
    " privacy",
    " gdpr",
    " deliverable",
    " contract",
    " tender",
    " proposal",
    " bid ",
    " staffing",
    " personnel",
    " qualification",
    " licensing",
    " license",
    " licence",
    " audit",
    " policy",
    " certificazione",
    " certificato",
    " assicurazione",
    " polizza",
    " allegato",
    " dichiarazione",
    " evidenza",
    " esperienza",
    " referenza",
    " referenze",
    " piano",
    " cronoprogramma",
    " supporto",
    " manutenzione",
    " sicurezza",
    " continuita",
    " continuita'",
    " privacy",
    " conformita",
    " conformita'",
    " offerta",
    " gara",
    " contratto",
    " personale",
    " qualifica",
)
_ACADEMIC_CONTEXT_KEYWORDS = (
    " theorem",
    " proof",
    " lemma",
    " corollary",
    " proposition",
    " graph",
    " vertex",
    " vertices",
    " edge",
    " edges",
    " path",
    " cycle",
    " matrix",
    " vector",
    " variable",
    " objective function",
    " optimization",
    " algoritmo",
    " teorema",
    " dimostrazione",
    " lemma",
    " corollario",
    " proposizione",
    " grafo",
    " vertice",
    " vertici",
    " arco",
    " archi",
    " cammino",
    " ciclo",
    " matrice",
    " vettore",
    " variabile",
    " funzione obiettivo",
    " ottimizzazione",
)
_HIGH_PRIORITY_KEYWORDS = (
    "must",
    "shall",
    "mandatory",
    "required",
    "deve",
    "dovra",
    "obbligatorio",
)
_PROCEDURE_HEADING_RE = re.compile(
    r"\b(?:gara|procedura|appalto|tender)\b.*\b\d{5,}/\d{4}\b",
    re.IGNORECASE,
)
_PROCEDURE_CODE_RE = re.compile(r"\b\d{5,}/\d{4}\b")


class IngestionPipeline:
    """
    Orchestrates the full document ingestion pipeline.

    Takes a raw document file, extracts text, chunks it,
    indexes embeddings, and builds knowledge graph entities.
    """

    def __init__(self, rag_engine):
        """
        Args:
            rag_engine: Reference to the HybridRAGEngine for accessing
                        chunker, embedder, retrievers, etc.
        """
        self.rag_engine = rag_engine

    async def ingest_file(
        self,
        file_path: str,
        document_id: int,
        doc_type: str = "general",
        metadata: dict | None = None,
        progress_callback=None,
    ) -> dict:
        """
        Process a single file through the full ingestion pipeline.

        Args:
            file_path: Path to the file on disk (or MinIO temp path).
            document_id: Database ID of the Document record.
            doc_type: Type of document (tender, proposal, reference, cv).
            metadata: Additional metadata to attach to chunks.

        Returns:
            dict with ingestion statistics.
        """
        metadata = metadata or {}
        metadata["document_id"] = document_id
        metadata["doc_type"] = doc_type

        logger.info("Ingesting document", file_path=file_path, doc_type=doc_type)

        # Step 1: Parse document
        await self._emit_progress(
            progress_callback,
            stage="parse",
            status="started",
            detail="Parsing structured content from the source document.",
        )
        elements = self._parse_document(file_path)
        full_text, section_texts = self._structure_elements(elements)
        await self._emit_progress(
            progress_callback,
            stage="parse",
            status="completed",
            detail="Document parsing completed.",
            stats={
                "elements_detected": len(elements),
                "sections_detected": len(section_texts),
            },
        )
        if not elements:
            logger.warning("No content extracted from document", file_path=file_path)
            await self._emit_progress(
                progress_callback,
                stage="requirement_extraction",
                status="skipped",
                detail="Skipping requirement extraction because no parsed content is available.",
            )
            await self._emit_progress(
                progress_callback,
                stage="chunking",
                status="skipped",
                detail="Skipping chunking because no parsed content is available.",
            )
            await self._emit_progress(
                progress_callback,
                stage="index_qdrant",
                status="skipped",
                detail="Skipping vector indexing because no chunks were produced.",
            )
            return {
                "status": "empty",
                "chunks": 0,
                "entities": 0,
                "requirements_detected": 0,
                "warnings": [],
            }

        # Step 2: Build structured text from elements
        requirement_candidates: list[dict] = []
        requirement_extraction_method = "none"
        ingestion_warnings: list[dict[str, object]] = []
        requirement_scope = "general"
        requirement_extractor_pipeline = "none"
        if doc_type == "tender":
            await self._emit_progress(
                progress_callback,
                stage="requirement_extraction",
                status="started",
                detail="Extracting tender participation requirements.",
            )
            heuristic_candidates = self.extract_requirement_candidates(elements, section_texts)
            extraction_result = await extract_tender_participation_requirements(
                generator=getattr(self.rag_engine, "generator", None),
                document_text=full_text,
                section_texts=section_texts,
                source_document_ref=file_path,
                tender_id=metadata.get("tender_id") or document_id,
                fallback_candidates=heuristic_candidates,
                settings=settings,
            )
            requirement_candidates = extraction_result.candidates
            requirement_extraction_method = extraction_result.extraction_method
            ingestion_warnings = list(extraction_result.warnings)
            requirement_scope = extraction_result.requirement_scope
            requirement_extractor_pipeline = extraction_result.extractor_pipeline
            await self._emit_progress(
                progress_callback,
                stage="requirement_extraction",
                status="completed",
                detail=f"Requirement extraction completed via {requirement_extraction_method}.",
                stats={
                    "requirements_detected": len(requirement_candidates),
                    "warnings_count": len(ingestion_warnings),
                    "extraction_method": requirement_extraction_method,
                    "requirement_scope": requirement_scope,
                    "extractor_pipeline": requirement_extractor_pipeline,
                },
            )
        else:
            await self._emit_progress(
                progress_callback,
                stage="requirement_extraction",
                status="skipped",
                detail="Requirement extraction only runs for tender documents.",
            )

        # Step 3: Chunk the text
        from fastapi.concurrency import run_in_threadpool

        await self._emit_progress(
            progress_callback,
            stage="chunking",
            status="started",
            detail="Chunking parsed content for retrieval and indexing.",
        )
        chunk_inputs = self._build_chunk_inputs(
            elements,
            file_path=file_path,
            document_id=document_id,
            doc_type=doc_type,
            metadata=metadata,
            fallback_text=full_text,
        )
        chunks = []
        for chunk_text, chunk_meta in chunk_inputs:
            chunk_batch = await run_in_threadpool(
                self.rag_engine.chunk_and_embed,
                chunk_text,
                chunk_meta,
            )
            chunks.extend(chunk_batch)

        for chunk_index, chunk in enumerate(chunks):
            chunk.metadata.chunk_index = chunk_index
        await self._emit_progress(
            progress_callback,
            stage="chunking",
            status="completed",
            detail="Chunk generation completed.",
            stats={
                "chunk_inputs": len(chunk_inputs),
                "chunks_created": len(chunks),
            },
        )

        # Step 4: Index chunks (dense + sparse)
        point_ids = []
        if chunks:
            await self._emit_progress(
                progress_callback,
                stage="index_qdrant",
                status="started",
                detail="Indexing chunks into dense and sparse retrieval stores.",
            )
            point_ids = await run_in_threadpool(self.rag_engine.index_chunks, chunks)
            await self._emit_progress(
                progress_callback,
                stage="index_qdrant",
                status="completed",
                detail="Vector and sparse indexing completed.",
                stats={
                    "chunks_indexed": len(chunks),
                    "points_indexed": len(point_ids),
                },
            )
        else:
            await self._emit_progress(
                progress_callback,
                stage="index_qdrant",
                status="skipped",
                detail="Skipping vector indexing because no chunks were created.",
            )

        # Step 5: Extract entities and build knowledge graph
        entity_count = 0
        if doc_type in ("proposal", "reference", "cv"):
            entity_count = await self._extract_and_graph(full_text, doc_type, metadata)

        stats = {
            "status": "completed",
            "chunks": len(chunks),
            "entities": entity_count,
            "point_ids": point_ids,
            "requirements_detected": len(requirement_candidates),
            "requirement_candidates": requirement_candidates,
            "requirement_extraction_method": requirement_extraction_method,
            "requirement_scope": requirement_scope,
            "requirement_extractor_pipeline": requirement_extractor_pipeline,
            "sections_detected": len(section_texts),
            "warnings": ingestion_warnings,
        }

        logger.info("Document ingestion complete", **stats)
        return stats

    async def _emit_progress(
        self,
        progress_callback,
        *,
        stage: str,
        status: str,
        detail: str | None = None,
        stats: dict | None = None,
    ) -> None:
        if progress_callback is None:
            return

        payload = {
            "stage": stage,
            "status": status,
        }
        if detail is not None:
            payload["detail"] = detail
        if stats:
            payload["stats"] = stats

        result = progress_callback(payload)
        if inspect.isawaitable(result):
            await result

    def extract_requirement_candidates(
        self,
        elements: list[dict],
        section_texts: dict[str, str] | None = None,
        *,
        limit: int = 25,
    ) -> list[dict]:
        """Heuristically extract requirement candidates from a tender document."""

        section_texts = section_texts or {}
        candidates: list[dict] = []
        seen: set[str] = set()

        def add_candidate(text: str, reference: str | None = None) -> None:
            cleaned = self._normalize_requirement_text(text)
            if not cleaned or cleaned in seen:
                return
            seen.add(cleaned)
            candidates.append(
                {
                    "summary": cleaned,
                    "reference": reference,
                    "priority": self._infer_requirement_priority(cleaned),
                }
            )

        for section_title, section_text in section_texts.items():
            if not self._looks_like_requirement_section(section_title):
                continue
            for line in self._candidate_lines(section_text):
                if self._looks_like_requirement_line(line, force=True):
                    add_candidate(line, section_title)
                    if len(candidates) >= limit:
                        return candidates

        for element in elements:
            text = str(element.get("text") or "").strip()
            if not text:
                continue
            metadata = element.get("metadata") or {}
            reference = metadata.get("section") or metadata.get("page_number")
            for line in self._candidate_lines(text):
                if self._looks_like_requirement_line(line):
                    add_candidate(line, str(reference) if reference is not None else None)
                    if len(candidates) >= limit:
                        return candidates

        return candidates

    def _candidate_lines(self, text: str) -> list[str]:
        cleaned_text = text.replace("\r", "\n")
        fragments = re.split(r"\n+|(?<=[.;:])\s{2,}", cleaned_text)
        return [fragment.strip() for fragment in fragments if fragment and fragment.strip()]

    def _looks_like_requirement_section(self, title: str | None) -> bool:
        normalized = str(title or "").strip().casefold()
        return any(keyword in normalized for keyword in _REQUIREMENT_SECTION_KEYWORDS)

    def _looks_like_requirement_line(self, text: str, *, force: bool = False) -> bool:
        raw = str(text or "").strip()
        cleaned = self._normalize_requirement_text(text)
        if len(cleaned) < 18 or len(cleaned) > 280:
            return False

        normalized = f" {cleaned.casefold()} "
        keyword_hit = any(keyword in normalized for keyword in _REQUIREMENT_LINE_KEYWORDS)
        strong_action_hit = any(
            keyword in normalized for keyword in _STRONG_REQUIREMENT_ACTION_KEYWORDS
        )
        object_hit = any(keyword in normalized for keyword in _REQUIREMENT_OBJECT_KEYWORDS)
        academic_hit = any(keyword in normalized for keyword in _ACADEMIC_CONTEXT_KEYWORDS)
        explicit_list_hit = bool(
            re.match(r"^(?:[-•*\u2022]\s+|\(?\d+[\).]\s+|[A-Za-z][\).]\s+)", raw)
        )
        procurement_hit = strong_action_hit or object_hit

        if force:
            if academic_hit and not procurement_hit:
                return False
            return len(cleaned.split()) >= 4 and (
                procurement_hit or keyword_hit or explicit_list_hit
            )

        if academic_hit and not procurement_hit:
            return False

        if procurement_hit and (keyword_hit or explicit_list_hit):
            return True

        return bool(strong_action_hit and object_hit)

    def _infer_requirement_priority(self, text: str) -> str:
        normalized = str(text or "").casefold()
        if any(keyword in normalized for keyword in _HIGH_PRIORITY_KEYWORDS):
            return "high"
        if "should" in normalized or "preferable" in normalized:
            return "low"
        return "medium"

    def _normalize_requirement_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "").strip())
        cleaned = re.sub(r"^[-•*\u2022\s]+", "", cleaned)
        cleaned = re.sub(r"^(?:\d+|[A-Za-z])[\.)]\s+", "", cleaned)
        return cleaned.strip(" .;")

    def _parse_document(self, file_path: str) -> list[dict]:
        """
        Parse a document file and extract structured elements.

        Uses the `unstructured` library for robust parsing of
        PDFs, DOCX, PPTX, and other formats.
        """
        try:
            from unstructured.partition.auto import partition

            elements = None
            if os.path.splitext(file_path)[1].casefold() == ".pdf":
                try:
                    from unstructured.partition.pdf import partition_pdf

                    elements = partition_pdf(
                        filename=file_path,
                        strategy="hi_res",
                        infer_table_structure=True,
                    )
                except Exception as exc:
                    logger.warning(
                        "Structured PDF parsing failed, falling back to auto partition",
                        error=str(exc),
                    )

            if elements is None:
                elements = partition(filename=file_path)

            parsed = []
            for elem in elements:
                elem_type = type(elem).__name__
                elem_metadata = getattr(elem, "metadata", None)
                is_table = (
                    elem_type.casefold() == "table" or getattr(elem, "category", None) == "Table"
                )
                metadata = {
                    "page_number": getattr(elem_metadata, "page_number", None),
                    "section": getattr(elem_metadata, "section", None),
                    "filename": getattr(elem_metadata, "filename", None),
                }
                if is_table:
                    metadata["is_table"] = True
                    text_as_html = getattr(elem_metadata, "text_as_html", None)
                    if text_as_html:
                        metadata["text_as_html"] = text_as_html
                parsed.append(
                    {
                        "type": elem_type,
                        "text": str(elem),
                        "metadata": metadata,
                    }
                )

            logger.debug("Document parsed", elements=len(parsed))
            return parsed

        except ImportError:
            logger.warning("unstructured not available, falling back to basic parsing")
            return self._fallback_parse(file_path)

        except Exception as e:
            logger.error("Document parsing failed", error=str(e))
            return []

    def _fallback_parse(self, file_path: str) -> list[dict]:
        """Fallback parser for when unstructured is not available."""
        import os

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return self._parse_pdf_fallback(file_path)
        elif ext in (".docx", ".doc"):
            return self._parse_docx_fallback(file_path)
        elif ext == ".txt":
            return self._parse_text(file_path)
        elif ext in (".md", ".markdown"):
            return self._parse_markdown_fallback(file_path)
        else:
            logger.warning("Unsupported file type", extension=ext)
            return []

    def _parse_pdf_fallback(self, file_path: str) -> list[dict]:
        """Parse PDF using PyMuPDF as fallback."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)
            elements = []
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text")
                if text.strip():
                    elements.append(
                        {
                            "type": "Text",
                            "text": text.strip(),
                            "metadata": {"page_number": page_num},
                        }
                    )
            doc.close()
            return elements

        except Exception as e:
            logger.error("PDF parsing failed", error=str(e))
            return []

    def _parse_docx_fallback(self, file_path: str) -> list[dict]:
        """Parse DOCX using python-docx as fallback."""
        try:
            from docx import Document

            doc = Document(file_path)
            elements = []
            for para in doc.paragraphs:
                if para.text.strip():
                    elements.append(
                        {
                            "type": "Title" if para.style.name.startswith("Heading") else "Text",
                            "text": para.text.strip(),
                            "metadata": {"style": para.style.name},
                        }
                    )
            return elements

        except Exception as e:
            logger.error("DOCX parsing failed", error=str(e))
            return []

    def _parse_text(self, file_path: str) -> list[dict]:
        """Parse plain text file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                text = f.read()
            return [{"type": "Text", "text": text, "metadata": {}}]
        except Exception as e:
            logger.error("Text parsing failed", error=str(e))
            return []

    def _parse_markdown_fallback(self, file_path: str) -> list[dict]:
        """Parse Markdown preserving heading structure for section grouping."""
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error("Markdown parsing failed", error=str(e))
            return []

        elements: list[dict] = []
        in_code_block = False
        buffer: list[str] = []

        def flush_buffer() -> None:
            if not buffer:
                return
            block = "\n".join(buffer).strip()
            if block:
                elements.append({"type": "Text", "text": block, "metadata": {}})
            buffer.clear()

        heading_re = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
        fence_re = re.compile(r"^\s*```")

        for raw in lines:
            line = raw.rstrip("\n")
            if fence_re.match(line):
                in_code_block = not in_code_block
                buffer.append(line)
                continue
            if in_code_block:
                buffer.append(line)
                continue
            m = heading_re.match(line)
            if m:
                flush_buffer()
                level = len(m.group(1))
                title = m.group(2).strip()
                elements.append(
                    {
                        "type": "Title",
                        "text": title,
                        "metadata": {"heading_level": level},
                    }
                )
                continue
            if line.strip() == "" and buffer:
                flush_buffer()
                continue
            buffer.append(line)

        flush_buffer()
        return elements

    def _structure_elements(self, elements: list[dict]) -> tuple[str, dict[str, str]]:
        """
        Build a structured full text and section map from parsed elements.

        Returns:
            Tuple of (full_text, section_texts_dict)
        """
        full_parts: list[str] = []
        sections: dict[str, str] = {}
        current_section = "Introduction"
        current_section_parts: list[str] = []

        for elem in elements:
            text = elem.get("text", "")
            elem_type = elem.get("type", "Text")

            if elem_type in ("Title", "Header") and text:
                # Save previous section
                if current_section_parts:
                    sections[current_section] = "\n".join(current_section_parts)
                current_section = text
                current_section_parts = []

            if text:
                full_parts.append(text)
                current_section_parts.append(text)

        # Save last section
        if current_section_parts:
            sections[current_section] = "\n".join(current_section_parts)

        full_text = "\n\n".join(full_parts)
        return full_text, sections

    async def _extract_and_graph(
        self,
        text: str,
        doc_type: str,
        metadata: dict,
    ) -> int:
        """
        Extract entities from text and add to the knowledge graph.

        Uses the LLM to extract structured entities (projects, team members,
        clients, certifications) from document text.
        """
        entity_count = 0

        try:
            # Use LLM to extract entities
            extraction_prompt = """Extract structured entities from the following document text.

## Document Text
{text}

## Instructions
Identify and extract:
- Projects (name, description, category, client, year, value)
- Team Members (name, title, role, years_experience, certifications, skills)
- Clients (name)
- Certifications (name)

Return as JSON:
{{
  "projects": [...],
  "team_members": [...],
  "clients": [...],
  "certifications": [...]
}}

## Extracted Entities
"""
            # Use a truncated version of the text for extraction
            truncated_text = text[:4000] if len(text) > 4000 else text

            result = await self.rag_engine.generator.generate(
                template=extraction_prompt,
                variables={"text": truncated_text},
                temperature=0.1,
            )

            entities = _extract_first_json_object(result.text)
            if entities is None:
                logger.warning("Failed to parse entity extraction response")
                entities = {}

            # Add entities to the knowledge graph
            graph = self.rag_engine.graph_retriever

            for project in entities.get("projects", []):
                project.setdefault("id", f"proj_{hash(project.get('name', ''))}")
                await graph.add_project(project)
                entity_count += 1

            for member in entities.get("team_members", []):
                member.setdefault("id", f"member_{hash(member.get('name', ''))}")
                await graph.add_team_member(member)
                entity_count += 1

            logger.info("Entity extraction complete", entities=entity_count)

        except Exception as e:
            logger.warning("Entity extraction failed", error=str(e))

        return entity_count

    async def ingest_text(
        self,
        text: str,
        document_id: int,
        doc_type: str = "general",
        metadata: dict | None = None,
    ) -> dict:
        """
        Ingest raw text (e.g., pasted content or content blocks).

        Simpler pipeline: chunk → embed → index. No file parsing needed.
        """
        metadata = metadata or {}
        metadata["document_id"] = document_id
        metadata["doc_type"] = doc_type

        from fastapi.concurrency import run_in_threadpool

        chunk_meta = self._build_chunk_metadata(
            document_id=document_id,
            doc_type=doc_type,
            file_path=str(metadata.get("source_file") or ""),
            metadata=metadata,
        )

        chunks = await run_in_threadpool(self.rag_engine.chunk_and_embed, text, chunk_meta)
        for chunk_index, chunk in enumerate(chunks):
            chunk.metadata.chunk_index = chunk_index
        point_ids = await run_in_threadpool(self.rag_engine.index_chunks, chunks) if chunks else []

        return {
            "status": "completed",
            "chunks": len(chunks),
            "entities": 0,
            "point_ids": point_ids,
        }

    def _build_chunk_metadata(
        self,
        *,
        document_id: int,
        doc_type: str,
        file_path: str,
        metadata: dict,
        section_title: str = "",
        page_number: int | None = None,
        extra: dict | None = None,
    ):
        from app.rag.chunker import ChunkMetadata

        original_filename = str(metadata.get("original_filename") or "").strip()
        source_document_ref = str(
            metadata.get("source_document_ref")
            or metadata.get("storage_object_name")
            or original_filename
            or file_path
        ).strip()

        chunk_metadata = ChunkMetadata(
            document_id=document_id,
            tender_id=metadata.get("tender_id"),
            source_file=file_path,
            source_document_ref=source_document_ref,
            filename=original_filename or os.path.basename(file_path),
            section_title=section_title,
            page_number=page_number,
            doc_type=doc_type,
        )
        if extra:
            chunk_metadata.extra.update(extra)
        return chunk_metadata

    def _detect_procedure_label(self, heading: str | None) -> str | None:
        text = re.sub(r"\s+", " ", str(heading or "").strip())
        if not text:
            return None
        if _PROCEDURE_HEADING_RE.search(text):
            return text
        if _PROCEDURE_CODE_RE.search(text) and any(
            token in text.casefold() for token in ("gara", "procedura", "appalto", "tender")
        ):
            return text
        return None

    def _procedure_key(self, label: str, index: int) -> str:
        normalized = "".join(
            ch
            for ch in unicodedata.normalize("NFKD", label.casefold())
            if not unicodedata.combining(ch)
        )
        slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:80] or f"procedure-{index}"
        digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
        return f"{index}-{slug}-{digest}"

    def _build_chunk_inputs(
        self,
        elements: list[dict],
        *,
        file_path: str,
        document_id: int,
        doc_type: str,
        metadata: dict,
        fallback_text: str,
    ) -> list[tuple[str, object]]:
        chunk_inputs: list[tuple[str, object]] = []
        current_section = "Introduction"
        current_page: int | None = None
        current_parts: list[str] = []
        current_procedure_label: str | None = None
        current_procedure_key: str | None = None
        current_procedure_index = 0

        def current_extra() -> dict:
            if not current_procedure_label or not current_procedure_key:
                return {}
            return {
                "procedure_label": current_procedure_label,
                "procedure_key": current_procedure_key,
                "procedure_index": current_procedure_index,
            }

        def quality_extra(chunk_text: str, extra: dict | None = None) -> dict:
            merged = dict(extra or {})
            merged.update(document_quality_metadata(chunk_text))
            return merged

        def flush_current_group() -> None:
            chunk_text = "\n\n".join(
                part for part in current_parts if part and part.strip()
            ).strip()
            if not chunk_text:
                return
            chunk_inputs.append(
                (
                    chunk_text,
                    self._build_chunk_metadata(
                        document_id=document_id,
                        doc_type=doc_type,
                        file_path=file_path,
                        metadata=metadata,
                        section_title=current_section,
                        page_number=current_page,
                        extra=quality_extra(chunk_text, current_extra()),
                    ),
                )
            )

        for element in elements:
            text = str(element.get("text") or "").strip()
            if not text:
                continue

            elem_type = str(element.get("type") or "Text")
            elem_metadata = element.get("metadata") or {}
            page_number = elem_metadata.get("page_number") or current_page

            if elem_type in ("Title", "Header"):
                if current_parts:
                    flush_current_group()
                    current_parts = []
                detected_procedure = self._detect_procedure_label(text)
                if detected_procedure:
                    current_procedure_index += 1
                    current_procedure_label = detected_procedure
                    current_procedure_key = self._procedure_key(
                        detected_procedure,
                        current_procedure_index,
                    )
                current_section = text
                current_page = page_number
                current_parts.append(text)
                continue

            if elem_metadata.get("is_table") or elem_type.casefold() == "table":
                if current_parts:
                    flush_current_group()
                    current_parts = []
                table_extra = current_extra()
                table_extra.update(
                    {
                        "is_table": True,
                        "table_html": elem_metadata.get("text_as_html"),
                    }
                )
                chunk_inputs.append(
                    (
                        text,
                        self._build_chunk_metadata(
                            document_id=document_id,
                            doc_type=doc_type,
                            file_path=file_path,
                            metadata=metadata,
                            section_title=current_section,
                            page_number=page_number,
                            extra=quality_extra(
                                text,
                                {
                                    key: value
                                    for key, value in table_extra.items()
                                    if value is not None
                                },
                            ),
                        ),
                    )
                )
                current_page = page_number
                continue

            if current_parts and page_number != current_page:
                flush_current_group()
                current_parts = []

            current_page = page_number
            current_parts.append(text)

        if current_parts:
            flush_current_group()

        if chunk_inputs:
            return chunk_inputs

        fallback = str(fallback_text or "").strip()
        if not fallback:
            return []

        return [
            (
                fallback,
                self._build_chunk_metadata(
                    document_id=document_id,
                    doc_type=doc_type,
                    file_path=file_path,
                    metadata=metadata,
                    extra=quality_extra(fallback),
                ),
            )
        ]
