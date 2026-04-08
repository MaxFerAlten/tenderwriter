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

import re

import structlog

from app.config import settings

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
        elements = self._parse_document(file_path)
        if not elements:
            logger.warning("No content extracted from document", file_path=file_path)
            return {"status": "empty", "chunks": 0, "entities": 0, "requirements_detected": 0}

        # Step 2: Build structured text from elements
        full_text, section_texts = self._structure_elements(elements)
        requirement_candidates: list[dict] = []
        if doc_type == "tender":
            requirement_candidates = self.extract_requirement_candidates(elements, section_texts)

        # Step 3: Chunk the text
        from app.rag.chunker import ChunkMetadata
        from fastapi.concurrency import run_in_threadpool
        chunk_meta = ChunkMetadata(
            document_id=document_id,
            source_file=file_path,
            doc_type=doc_type,
        )
        chunks = await run_in_threadpool(
            self.rag_engine.chunk_and_embed, full_text, chunk_meta
        )

        # Step 4: Index chunks (dense + sparse)
        point_ids = []
        if chunks:
            point_ids = await run_in_threadpool(
                self.rag_engine.index_chunks, chunks
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
            "sections_detected": len(section_texts),
        }

        logger.info("Document ingestion complete", **stats)
        return stats

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
        strong_action_hit = any(keyword in normalized for keyword in _STRONG_REQUIREMENT_ACTION_KEYWORDS)
        object_hit = any(keyword in normalized for keyword in _REQUIREMENT_OBJECT_KEYWORDS)
        academic_hit = any(keyword in normalized for keyword in _ACADEMIC_CONTEXT_KEYWORDS)
        explicit_list_hit = bool(re.match(r"^(?:[-•*\u2022]\s+|\(?\d+[\).]\s+|[A-Za-z][\).]\s+)", raw))
        procurement_hit = strong_action_hit or object_hit

        if force:
            if academic_hit and not procurement_hit:
                return False
            return len(cleaned.split()) >= 4 and (procurement_hit or keyword_hit or explicit_list_hit)

        if academic_hit and not procurement_hit:
            return False

        if procurement_hit and (keyword_hit or explicit_list_hit):
            return True

        if strong_action_hit and object_hit:
            return True

        return False

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

            elements = partition(filename=file_path)

            parsed = []
            for elem in elements:
                parsed.append({
                    "type": type(elem).__name__,
                    "text": str(elem),
                    "metadata": {
                        "page_number": getattr(elem.metadata, "page_number", None),
                        "section": getattr(elem.metadata, "section", None),
                        "filename": getattr(elem.metadata, "filename", None),
                    },
                })

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
                    elements.append({
                        "type": "Text",
                        "text": text.strip(),
                        "metadata": {"page_number": page_num},
                    })
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
                    elements.append({
                        "type": "Title" if para.style.name.startswith("Heading") else "Text",
                        "text": para.text.strip(),
                        "metadata": {"style": para.style.name},
                    })
            return elements

        except Exception as e:
            logger.error("DOCX parsing failed", error=str(e))
            return []

    def _parse_text(self, file_path: str) -> list[dict]:
        """Parse plain text file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            return [{"type": "Text", "text": text, "metadata": {}}]
        except Exception as e:
            logger.error("Text parsing failed", error=str(e))
            return []

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

            # Parse the extracted entities
            import json
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

        from app.rag.chunker import ChunkMetadata
        from fastapi.concurrency import run_in_threadpool
        chunk_meta = ChunkMetadata(
            document_id=document_id,
            doc_type=doc_type,
        )

        chunks = await run_in_threadpool(
            self.rag_engine.chunk_and_embed, text, chunk_meta
        )
        point_ids = await run_in_threadpool(
            self.rag_engine.index_chunks, chunks
        ) if chunks else []

        return {
            "status": "completed",
            "chunks": len(chunks),
            "entities": 0,
            "point_ids": point_ids,
        }
