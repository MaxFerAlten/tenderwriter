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

import structlog

from app.config import settings

logger = structlog.get_logger()


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
            return {"status": "empty", "chunks": 0, "entities": 0}

        # Step 2: Build structured text from elements
        full_text, section_texts = self._structure_elements(elements)

        # Step 3: Chunk the text
        from app.rag.chunker import ChunkMetadata
        chunk_meta = ChunkMetadata(
            document_id=document_id,
            source_file=file_path,
            doc_type=doc_type,
        )
        chunks = self.rag_engine.chunk_and_embed(full_text, chunk_meta)

        # Step 4: Index chunks (dense + sparse)
        point_ids = []
        if chunks:
            point_ids = self.rag_engine.index_chunks(chunks)

        # Step 5: Extract entities and build knowledge graph
        entity_count = 0
        if doc_type in ("proposal", "reference", "cv"):
            entity_count = await self._extract_and_graph(full_text, doc_type, metadata)

        stats = {
            "status": "completed",
            "chunks": len(chunks),
            "entities": entity_count,
            "point_ids": point_ids,
        }

        logger.info("Document ingestion complete", **stats)
        return stats

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
            try:
                # Try to extract JSON from the response
                response_text = result.text
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    entities = json.loads(response_text[json_start:json_end])
                else:
                    entities = {}
            except json.JSONDecodeError:
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
        chunk_meta = ChunkMetadata(
            document_id=document_id,
            doc_type=doc_type,
        )

        chunks = self.rag_engine.chunk_and_embed(text, chunk_meta)
        point_ids = self.rag_engine.index_chunks(chunks) if chunks else []

        return {
            "status": "completed",
            "chunks": len(chunks),
            "entities": 0,
            "point_ids": point_ids,
        }
