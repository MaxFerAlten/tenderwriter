"""
TenderWriter — Graph Retriever (Neo4j Knowledge Graph)

Retrieves structured information from the knowledge graph including
projects, team members, certifications, and their relationships.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

import structlog
from neo4j import AsyncGraphDatabase

from app.config import settings
from app.intelligence.ontology import TenderOntologyService

logger = structlog.get_logger()

GOLD_DOMAIN_TO_ONTOLOGY_DOMAINS = {
    "AMMINISTRATIVO": {"amministrativo"},
    "CERTIFICAZIONI": {"compliance"},
    "CLAUSOLE_CONTRATTUALI": {"contrattuale"},
    "ECONOMICO_FINANZIARIO": {"economico_finanziario"},
    "ORGANIZZATIVO": {"organizzativo"},
    "PENALITA": {"contrattuale"},
    "SLA_PENALITA": {"tecnico", "contrattuale"},
    "SUBAPPALTO_RTI": {"amministrativo"},
    "TECNICO": {"tecnico"},
}

GRAPH_QUERY_STOPWORDS = {
    "quali",
    "quale",
    "cosa",
    "come",
    "sono",
    "deve",
    "devono",
    "fornitore",
    "fornitura",
    "gara",
    "contratto",
    "durante",
    "entro",
    "quanto",
    "tempi",
    "richieste",
    "richiesta",
    "obbligatorie",
    "obbligatorio",
    "previsto",
    "prevista",
    "accordo",
    "quadro",
}

ONTOLOGY_DOMAIN_QUERY_TERMS = {
    "amministrativo": ("procedura", "piattaforma", "subappalto", "rti", "consorzio"),
    "compliance": ("certificazione", "certificazioni", "iso", "gdpr", "audit"),
    "contrattuale": ("penali", "penale", "risoluzione", "recesso", "danni", "garanzie"),
    "economico_finanziario": ("fatturato", "garanzia", "cauzione", "polizza", "corrispettivo"),
    "organizzativo": ("personale", "risorse", "team", "profili", "responsabile"),
    "tecnico": ("acn", "oscat", "sct", "sla", "integrazione", "infrastruttura", "servizi"),
}

GRAPH_QUERY_TOKEN_RE = re.compile(r"[\wÀ-ÿ/.-]+", re.UNICODE)


@dataclass
class GraphSearchResult:
    """A single result from graph search."""

    text: str
    score: float
    metadata: dict
    entity_type: str
    relationships: list[dict]


class GraphRetriever:
    """
    Knowledge graph retrieval using Neo4j.

    Manages graph schema, entity indexing, and relationship-aware search.
    """

    def __init__(self):
        self._driver = None
        self._ontology_service = TenderOntologyService()

    async def initialize(self):
        """Connect to Neo4j and ensure schema constraints."""
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

        # Verify connectivity
        async with self._driver.session() as session:
            result = await session.run("RETURN 1 AS ping")
            await result.single()

        logger.info("Connected to Neo4j", uri=settings.neo4j_uri)
        await self._ensure_schema()

    async def _ensure_schema(self):
        """Create indexes and constraints for the knowledge graph."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (tnd:Tender) REQUIRE tnd.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:TeamMember) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Client) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (cert:Certification) REQUIRE cert.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (req:Requirement) REQUIRE req.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (chunk:EvidenceChunk) REQUIRE chunk.id IS UNIQUE",
            (
                "CREATE CONSTRAINT IF NOT EXISTS FOR (ev:RequirementEvent) "
                "REQUIRE ev.external_event_id IS UNIQUE"
            ),
        ]

        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (tnd:Tender) ON (tnd.title)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.name)",
            "CREATE INDEX IF NOT EXISTS FOR (t:TeamMember) ON (t.name)",
            "CREATE INDEX IF NOT EXISTS FOR (req:Requirement) ON (req.identity_hash)",
            "CREATE INDEX IF NOT EXISTS FOR (req:Requirement) ON (req.ontology_domain)",
            "CREATE INDEX IF NOT EXISTS FOR (req:Requirement) ON (req.page_number)",
            "CREATE INDEX IF NOT EXISTS FOR (chunk:EvidenceChunk) ON (chunk.ontology_domain)",
            "CREATE INDEX IF NOT EXISTS FOR (chunk:EvidenceChunk) ON (chunk.tender_id)",
            "CREATE INDEX IF NOT EXISTS FOR (chunk:EvidenceChunk) ON (chunk.page_number)",
            "CREATE INDEX IF NOT EXISTS FOR (ev:RequirementEvent) ON (ev.occurred_at)",
            "CREATE INDEX IF NOT EXISTS FOR (ev:RequirementEvent) ON (ev.event_type)",
        ]

        async with self._driver.session() as session:
            for stmt in constraints + indexes:
                await session.run(stmt)

        logger.info("Neo4j schema constraints ensured")

    async def upsert_tender(self, tender: dict):
        """Create or update a Tender node in the knowledge graph."""
        query = """
        MERGE (t:Tender {id: $id})
        SET t.title = $title,
            t.status = $status,
            t.client = $client,
            t.category = $category,
            t.deadline = $deadline
        """

        async with self._driver.session() as session:
            await session.run(
                query,
                id=tender["id"],
                title=tender.get("title") or tender["id"],
                status=tender.get("status"),
                client=tender.get("client"),
                category=tender.get("category"),
                deadline=tender.get("deadline"),
            )

        logger.info("Upserted tender in graph", tender_id=tender["id"])

    async def add_project(self, project: dict):
        """
        Add a project node to the knowledge graph.

        Expected keys: id, name, description, category, year, client, team, certifications
        """
        query = """
        MERGE (p:Project {id: $id})
        SET p.name = $name,
            p.description = $description,
            p.category = $category,
            p.year = $year
        WITH p
        MERGE (c:Client {name: $client})
        MERGE (p)-[:FOR_CLIENT]->(c)
        WITH p
        MERGE (cat:Category {name: $category})
        MERGE (p)-[:HAS_CATEGORY]->(cat)
        """

        async with self._driver.session() as session:
            await session.run(query, **project)

        # Add team member relationships
        if "team" in project and project["team"]:
            for member in project["team"]:
                await self._link_team_member_to_project(project["id"], member)

        # Add certification requirements
        if "certifications" in project and project["certifications"]:
            for cert_name in project["certifications"]:
                await self._link_certification_to_project(project["id"], cert_name)

        logger.info("Added project to graph", project_id=project["id"])

    async def _link_team_member_to_project(self, project_id: str, member: dict):
        """Link a team member to a project with role information."""
        query = """
        MATCH (p:Project {id: $project_id})
        MERGE (t:TeamMember {id: $member_id})
        MERGE (t)-[r:DELIVERED]->(p)
        SET r.role = $role
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                project_id=project_id,
                member_id=member.get("id"),
                role=member.get("role", "Team Member"),
            )

    async def _link_certification_to_project(self, project_id: str, cert_name: str):
        """Link a certification requirement to a project."""
        query = """
        MATCH (p:Project {id: $project_id})
        MERGE (cert:Certification {name: $cert_name})
        MERGE (p)-[:REQUIRES_CERT]->(cert)
        """
        async with self._driver.session() as session:
            await session.run(query, project_id=project_id, cert_name=cert_name)

    async def add_team_member(self, member: dict):
        """
        Add a team member node to the knowledge graph.

        Expected keys: id, name, title, years_experience, skills, certifications
        """
        query = """
        MERGE (t:TeamMember {id: $id})
        SET t.name = $name,
            t.title = $title,
            t.years_experience = $years_experience,
            t.skills = $skills
        """

        async with self._driver.session() as session:
            await session.run(
                query,
                id=member["id"],
                name=member["name"],
                title=member.get("title", ""),
                years_experience=member.get("years_experience", 0),
                skills=member.get("skills", []),
            )

        # Add certifications
        if "certifications" in member and member["certifications"]:
            for cert in member["certifications"]:
                cert_query = """
                MATCH (t:TeamMember {id: $member_id})
                MERGE (cert:Certification {name: $cert_name})
                MERGE (t)-[:HOLDS]->(cert)
                """
                async with self._driver.session() as session:
                    await session.run(cert_query, member_id=member["id"], cert_name=cert)

    async def add_requirement(self, requirement: dict, tender_id: str, tender: dict | None = None):
        """Add a tender requirement to the knowledge graph and link it to its tender."""
        query = """
        MERGE (t:Tender {id: $tender_id})
        ON CREATE SET t.title = coalesce($tender_title, $tender_id)
        SET t.title = coalesce($tender_title, t.title),
            t.status = coalesce($tender_status, t.status),
            t.client = coalesce($tender_client, t.client),
            t.category = coalesce($tender_category, t.category),
            t.deadline = coalesce($tender_deadline, t.deadline)
        WITH t
        MERGE (r:Requirement {id: $id})
        SET r.text = $text,
            r.identity_hash = $identity_hash,
            r.category = $category,
            r.priority = $priority,
            r.tender_id = $tender_id,
            r.ontology_domain = $ontology_domain,
            r.ontology_subdomain = $ontology_subdomain,
            r.criticality = $criticality,
            r.evidence_type = $evidence_type,
            r.owner_role = $owner_role,
            r.evaluation_axis = $evaluation_axis,
            r.ontology_version = $ontology_version,
            r.mapping_confidence = $mapping_confidence,
            r.page_number = $page_number,
            r.source_document_ref = $source_document_ref,
            r.procedure_key = $procedure_key
        MERGE (t)-[:HAS_REQUIREMENT]->(r)
        """
        tender = tender or {}
        ontology_payload = self._ontology_payload_for_requirement(requirement)
        async with self._driver.session() as session:
            await session.run(
                query,
                id=requirement["id"],
                identity_hash=requirement.get("identity_hash"),
                text=requirement["text"],
                category=requirement.get("category", "general"),
                priority=requirement.get("priority", "medium"),
                ontology_domain=ontology_payload.get("ontology_domain"),
                ontology_subdomain=ontology_payload.get("ontology_subdomain"),
                criticality=ontology_payload.get("criticality"),
                evidence_type=ontology_payload.get("evidence_type"),
                owner_role=ontology_payload.get("owner_role"),
                evaluation_axis=ontology_payload.get("evaluation_axis"),
                ontology_version=ontology_payload.get("ontology_version"),
                mapping_confidence=ontology_payload.get("mapping_confidence"),
                page_number=self._as_int(requirement.get("page_number")),
                source_document_ref=requirement.get("source_document_ref"),
                procedure_key=requirement.get("procedure_key"),
                tender_id=tender_id,
                tender_title=tender.get("title"),
                tender_status=tender.get("status"),
                tender_client=tender.get("client"),
                tender_category=tender.get("category"),
                tender_deadline=tender.get("deadline"),
            )

    async def upsert_evidence_chunk(self, chunk: dict) -> None:
        """Upsert a cited retrieval chunk into Neo4j as ontology-tagged evidence."""

        ontology_payload = self._ontology_payload_for_requirement(chunk)
        query = """
        MERGE (c:EvidenceChunk {id: $id})
        SET c.text = $text,
            c.doc_type = $doc_type,
            c.tender_id = $tender_id,
            c.document_id = $document_id,
            c.chunk_index = $chunk_index,
            c.section_title = $section_title,
            c.page_number = $page_number,
            c.source_document_ref = $source_document_ref,
            c.procedure_key = $procedure_key,
            c.ontology_domain = $ontology_domain,
            c.ontology_subdomain = $ontology_subdomain,
            c.criticality = $criticality,
            c.evidence_type = $evidence_type,
            c.owner_role = $owner_role,
            c.evaluation_axis = $evaluation_axis,
            c.ontology_version = $ontology_version,
            c.mapping_confidence = $mapping_confidence
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                id=chunk["id"],
                text=chunk["text"],
                doc_type=chunk.get("doc_type"),
                tender_id=str(chunk.get("tender_id")) if chunk.get("tender_id") else None,
                document_id=chunk.get("document_id"),
                chunk_index=chunk.get("chunk_index"),
                section_title=chunk.get("section_title"),
                page_number=self._as_int(chunk.get("page_number")),
                source_document_ref=chunk.get("source_document_ref"),
                procedure_key=chunk.get("procedure_key"),
                ontology_domain=ontology_payload.get("ontology_domain"),
                ontology_subdomain=ontology_payload.get("ontology_subdomain"),
                criticality=ontology_payload.get("criticality"),
                evidence_type=ontology_payload.get("evidence_type"),
                owner_role=ontology_payload.get("owner_role"),
                evaluation_axis=ontology_payload.get("evaluation_axis"),
                ontology_version=ontology_payload.get("ontology_version"),
                mapping_confidence=ontology_payload.get("mapping_confidence"),
            )

    async def update_requirement_snapshot(
        self,
        requirement_id: str,
        snapshot: dict,
    ) -> None:
        """Merge lifecycle snapshot fields onto an existing Requirement node.

        ``snapshot`` accepts the canonical keys ``current_status``,
        ``coverage_status``, ``risk_level``, ``gate_state``,
        ``last_event_type``, ``last_event_at``. Unknown keys are ignored
        so callers can pass partial updates.
        """
        allowed = {
            "current_status",
            "coverage_status",
            "risk_level",
            "gate_state",
            "last_event_type",
            "last_event_at",
        }
        payload = {key: snapshot.get(key) for key in allowed if key in snapshot}
        if not payload:
            return

        query = """
        MERGE (r:Requirement {id: $id})
        SET r.current_status = coalesce($current_status, r.current_status),
            r.coverage_status = coalesce($coverage_status, r.coverage_status),
            r.risk_level = coalesce($risk_level, r.risk_level),
            r.gate_state = coalesce($gate_state, r.gate_state),
            r.last_event_type = coalesce($last_event_type, r.last_event_type),
            r.last_event_at = coalesce($last_event_at, r.last_event_at)
        """

        params = {
            "id": requirement_id,
            "current_status": payload.get("current_status"),
            "coverage_status": payload.get("coverage_status"),
            "risk_level": payload.get("risk_level"),
            "gate_state": payload.get("gate_state"),
            "last_event_type": payload.get("last_event_type"),
            "last_event_at": payload.get("last_event_at"),
        }

        async with self._driver.session() as session:
            await session.run(query, **params)

    async def append_requirement_lifecycle_event(
        self,
        requirement_id: str,
        event: dict,
    ) -> None:
        """Append a RequirementEvent node and link it via HAS_LIFECYCLE_EVENT.

        ``event`` must include ``external_event_id`` (unique). Other fields:
        ``event_type``, ``occurred_at`` (ISO-8601 string), ``actor_id``,
        ``payload`` (JSON-serialisable dict, stored as a JSON string), and
        ``tender_id`` for traceability.
        """
        external_event_id = str(event.get("external_event_id") or "").strip()
        if not external_event_id:
            raise ValueError("external_event_id is required for lifecycle event")

        query = """
        MERGE (r:Requirement {id: $requirement_id})
        MERGE (ev:RequirementEvent {external_event_id: $external_event_id})
        SET ev.event_type = $event_type,
            ev.occurred_at = $occurred_at,
            ev.actor_id = $actor_id,
            ev.tender_id = $tender_id,
            ev.payload_json = $payload_json
        MERGE (r)-[:HAS_LIFECYCLE_EVENT]->(ev)
        """

        import json as _json

        params = {
            "requirement_id": requirement_id,
            "external_event_id": external_event_id,
            "event_type": event.get("event_type"),
            "occurred_at": event.get("occurred_at"),
            "actor_id": event.get("actor_id"),
            "tender_id": event.get("tender_id"),
            "payload_json": _json.dumps(
                event.get("payload") or {},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        }

        async with self._driver.session() as session:
            await session.run(query, **params)

    async def fetch_requirement_lifecycle(
        self,
        requirement_id: str,
        *,
        limit: int = 25,
    ) -> dict:
        """Return the snapshot + recent lifecycle events for a Requirement node.

        Used by the explain tool to surface the projected lifecycle without
        re-querying PostgreSQL. Returns ``{"snapshot": {...}, "events": [...]}``;
        empty dicts when the node is missing.
        """
        query = """
        MATCH (r:Requirement {id: $id})
        OPTIONAL MATCH (r)-[:HAS_LIFECYCLE_EVENT]->(ev:RequirementEvent)
        WITH r, ev
        ORDER BY ev.occurred_at DESC
        WITH r, collect(ev)[..$limit] AS events
        RETURN r AS requirement, events
        """

        async with self._driver.session() as session:
            cursor = await session.run(query, id=requirement_id, limit=limit)
            records = await cursor.data()

        if not records:
            return {"snapshot": {}, "events": []}

        record = records[0]
        node = record.get("requirement") or {}
        snapshot = {
            "current_status": node.get("current_status"),
            "coverage_status": node.get("coverage_status"),
            "risk_level": node.get("risk_level"),
            "gate_state": node.get("gate_state"),
            "last_event_type": node.get("last_event_type"),
            "last_event_at": node.get("last_event_at"),
        }
        events = [
            {
                "external_event_id": ev.get("external_event_id"),
                "event_type": ev.get("event_type"),
                "occurred_at": ev.get("occurred_at"),
                "actor_id": ev.get("actor_id"),
                "tender_id": ev.get("tender_id"),
                "payload_json": ev.get("payload_json"),
            }
            for ev in (record.get("events") or [])
            if ev
        ]
        return {"snapshot": snapshot, "events": events}

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> list[GraphSearchResult]:
        """
        Search the knowledge graph for relevant entities and relationships.

        Uses full-text matching on node properties and returns structured
        context including entity relationships.
        """
        top_k = top_k or settings.rag_top_k_graph
        results: list[GraphSearchResult] = []
        tender_id_filter = self._extract_tender_id_filter(filters)
        ontology_domains = self._ontology_filter_domains(filters)

        evidence_results = await self._search_evidence_chunks(query, top_k, filters)
        results.extend(evidence_results)

        if tender_id_filter is not None:
            tender_results = await self._search_tenders(query, top_k, filters)
            results.extend(tender_results)
        elif not ontology_domains:
            project_results = await self._search_projects(query, top_k, filters)
            results.extend(project_results)

            member_results = await self._search_team_members(query, top_k, filters)
            results.extend(member_results)

        requirement_results = await self._search_requirements(query, top_k, filters)
        results.extend(requirement_results)

        # Sort by score and take top_k
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

        logger.debug("Graph search complete", query_len=len(query), results=len(results))
        return results

    def _extract_tender_id_filter(self, filters: dict | None) -> str | None:
        if not filters:
            return None

        tender_id = filters.get("tender_id")
        if isinstance(tender_id, list):
            tender_id = tender_id[0] if tender_id else None
        if tender_id in (None, ""):
            return None

        return str(tender_id)

    async def _search_evidence_chunks(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Search ontology-tagged retrieval chunks stored in the graph."""
        tender_id_filter = self._extract_tender_id_filter(filters)
        ontology_domains = self._ontology_filter_domains(filters)
        keywords = self._query_keywords(query, ontology_domains)

        cypher = """
        MATCH (c:EvidenceChunk)
        WHERE any(kw IN $keywords WHERE
               toLower(coalesce(c.text, "")) CONTAINS kw
               OR toLower(coalesce(c.section_title, "")) CONTAINS kw)
          AND (
            $tender_id IS NULL
            OR coalesce(toString(c.tender_id), "") = $tender_id
          )
        RETURN c
        LIMIT $limit
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(
                cypher,
                keywords=keywords,
                limit=max(top_k * 3, top_k),
                tender_id=tender_id_filter,
            )
            records = await cursor.data()

            for record in records:
                result = self._build_evidence_chunk_result(
                    record["c"],
                    ontology_domains=ontology_domains,
                )
                if result:
                    result.score += min(self._keyword_overlap(result.text, keywords), 6) * 0.03
                    results.append(result)

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def _ontology_filter_domains(self, filters: dict | None) -> set[str]:
        if not filters:
            return set()

        raw_value = filters.get("graph_ontology_domain") or filters.get("ontology_domain")
        values = raw_value if isinstance(raw_value, list | tuple | set) else [raw_value]
        domains: set[str] = set()
        for value in values:
            if value in (None, ""):
                continue
            text = str(value).strip()
            domains.update(GOLD_DOMAIN_TO_ONTOLOGY_DOMAINS.get(text.upper(), set()))
            normalized = text.casefold()
            if normalized in {
                "amministrativo",
                "economico_finanziario",
                "tecnico",
                "premiale",
                "compliance",
                "contrattuale",
                "sicurezza",
                "organizzativo",
                "documentale",
                "altro",
            }:
                domains.add(normalized)
        return domains

    def _ontology_payload_for_requirement(self, requirement: Mapping) -> dict:
        if requirement.get("ontology_domain"):
            return {
                "ontology_domain": str(requirement.get("ontology_domain")).casefold(),
                "ontology_subdomain": requirement.get("ontology_subdomain") or "non_classificato",
                "criticality": requirement.get("criticality") or "medium",
                "evidence_type": requirement.get("evidence_type") or "documentary_proof",
                "owner_role": requirement.get("owner_role") or "unknown",
                "evaluation_axis": requirement.get("evaluation_axis") or "mandatory",
                "ontology_version": requirement.get("ontology_version") or "tw-ontology-v1",
                "mapping_confidence": requirement.get("mapping_confidence") or 0.8,
            }

        tag = self._ontology_service.tag_text(
            str(requirement.get("text") or ""),
            category=str(requirement.get("category") or "") or None,
            priority=str(requirement.get("priority") or "") or None,
        )
        return tag.model_dump(mode="json")

    @staticmethod
    def _as_int(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _query_keywords(self, query: str, ontology_domains: set[str]) -> list[str]:
        keywords: list[str] = []
        for token in GRAPH_QUERY_TOKEN_RE.findall(str(query or "").casefold()):
            normalized = token.strip(".,;:!?()[]{}")
            if len(normalized) <= 3 or normalized in GRAPH_QUERY_STOPWORDS:
                continue
            if normalized not in keywords:
                keywords.append(normalized)

        for domain in sorted(ontology_domains):
            for term in ONTOLOGY_DOMAIN_QUERY_TERMS.get(domain, ()):
                if term not in keywords:
                    keywords.append(term)

        if not keywords and query:
            keywords.append(str(query).casefold())
        return keywords

    @staticmethod
    def _keyword_overlap(text: str, keywords: list[str]) -> int:
        normalized_text = str(text or "").casefold()
        return sum(1 for keyword in keywords if keyword and keyword in normalized_text)

    def _build_requirement_result(
        self,
        requirement: Mapping,
        tender: Mapping | None,
        ontology_domains: set[str],
    ) -> GraphSearchResult | None:
        ontology_payload = self._ontology_payload_for_requirement(requirement)
        ontology_domain = str(ontology_payload.get("ontology_domain") or "").casefold()
        if ontology_domains and ontology_domain not in ontology_domains:
            return None

        page_number = self._as_int(requirement.get("page_number"))
        source_document_ref = requirement.get("source_document_ref")
        procedure_key = requirement.get("procedure_key")
        score = 0.9 if page_number or source_document_ref else 0.55
        if ontology_domains and ontology_domain:
            score += 0.05

        text_parts = [
            f"Requirement: {requirement.get('text', 'N/A')}",
            f"Category: {requirement.get('category', 'N/A')}",
            f"Priority: {requirement.get('priority', 'N/A')}",
            f"Ontology: {ontology_domain}:{ontology_payload.get('ontology_subdomain')}",
        ]
        if tender:
            text_parts.append(f"Tender: {tender.get('title', tender.get('id', 'N/A'))}")
        if page_number:
            text_parts.append(f"Page: {page_number}")

        metadata = {
            "source": "knowledge_graph",
            "entity_id": requirement.get("id"),
            "tender_id": requirement.get("tender_id"),
            "page_number": page_number,
            "source_document_ref": source_document_ref,
            "procedure_key": procedure_key,
            **ontology_payload,
            "has_provenance": bool(page_number or source_document_ref),
        }
        return GraphSearchResult(
            text="\n".join(text_parts),
            score=score,
            metadata=metadata,
            entity_type="Requirement",
            relationships=[
                {
                    "type": "BELONGS_TO_TENDER",
                    "target": tender.get("title") if tender else None,
                }
            ],
        )

    def _build_evidence_chunk_result(
        self,
        chunk: Mapping,
        ontology_domains: set[str],
    ) -> GraphSearchResult | None:
        ontology_payload = self._ontology_payload_for_requirement(chunk)
        ontology_domain = str(ontology_payload.get("ontology_domain") or "").casefold()
        if ontology_domains and ontology_domain not in ontology_domains:
            return None

        text = str(chunk.get("text") or "").strip()
        if not text:
            return None

        page_number = self._as_int(chunk.get("page_number"))
        source_document_ref = chunk.get("source_document_ref")
        metadata = {
            "source": "knowledge_graph",
            "entity_type": "EvidenceChunk",
            "entity_id": chunk.get("id"),
            "tender_id": chunk.get("tender_id"),
            "doc_type": chunk.get("doc_type"),
            "document_id": chunk.get("document_id"),
            "chunk_index": chunk.get("chunk_index"),
            "section_title": chunk.get("section_title"),
            "page_number": page_number,
            "source_document_ref": source_document_ref,
            "procedure_key": chunk.get("procedure_key"),
            **ontology_payload,
            "has_provenance": bool(page_number or source_document_ref),
        }
        return GraphSearchResult(
            text=text,
            score=0.95 if metadata["has_provenance"] else 0.6,
            metadata=metadata,
            entity_type="EvidenceChunk",
            relationships=[],
        )

    async def _search_tenders(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Return scoped tender context when the query is limited to a specific tender."""
        tender_id = self._extract_tender_id_filter(filters)
        if tender_id is None:
            return []

        cypher = """
        MATCH (t:Tender {id: $tender_id})
        OPTIONAL MATCH (t)-[:HAS_REQUIREMENT]->(r:Requirement)
        WITH t, collect(r)[..5] AS requirements
        RETURN t, requirements
        LIMIT 1
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(cypher, tender_id=tender_id)
            records = await cursor.data()

            for record in records:
                tender = record["t"]
                requirements = record.get("requirements", [])

                text_parts = [
                    f"Tender: {tender.get('title', tender.get('id', 'Unknown'))}",
                ]

                if tender.get("client"):
                    text_parts.append(f"Client: {tender.get('client')}")
                if tender.get("category"):
                    text_parts.append(f"Category: {tender.get('category')}")
                if tender.get("status"):
                    text_parts.append(f"Status: {tender.get('status')}")
                if tender.get("deadline"):
                    text_parts.append(f"Deadline: {tender.get('deadline')}")

                requirement_summaries = [
                    str(requirement.get("text") or "").strip()
                    for requirement in requirements
                    if requirement and str(requirement.get("text") or "").strip()
                ]
                if requirement_summaries:
                    text_parts.append("Known requirements: " + "; ".join(requirement_summaries[:5]))

                results.append(
                    GraphSearchResult(
                        text="\n".join(text_parts),
                        score=0.95,
                        metadata={
                            "source": "knowledge_graph",
                            "entity_id": tender.get("id"),
                            "tender_id": tender.get("id"),
                        },
                        entity_type="Tender",
                        relationships=[
                            {"type": "HAS_REQUIREMENT", "target": summary}
                            for summary in requirement_summaries[:5]
                        ],
                    )
                )

        return results

    async def _search_projects(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Search for projects matching the query."""
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            keywords = [query.lower()]

        cypher = """
        MATCH (p:Project)
        WHERE any(kw IN $keywords WHERE
               toLower(p.name) CONTAINS kw
               OR toLower(p.description) CONTAINS kw
               OR toLower(p.category) CONTAINS kw)
        OPTIONAL MATCH (p)-[:FOR_CLIENT]->(c:Client)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (t:TeamMember)-[r:DELIVERED]->(p)
        OPTIONAL MATCH (p)-[:REQUIRES_CERT]->(cert:Certification)
        RETURN p, c, cat,
               collect(DISTINCT {name: t.name, role: r.role}) AS team,
               collect(DISTINCT cert.name) AS certifications
        LIMIT $limit
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(cypher, keywords=keywords, limit=top_k)
            records = await cursor.data()

            for record in records:
                project = record["p"]
                client = record.get("c")
                team = record.get("team", [])
                certs = record.get("certifications", [])

                # Build human-readable text from graph data
                text_parts = [
                    f"Project: {project.get('name', 'Unknown')}",
                    f"Description: {project.get('description', 'N/A')}",
                    f"Category: {project.get('category', 'N/A')}",
                    f"Client: {client.get('name', 'N/A') if client else 'N/A'}",
                    f"Year: {project.get('year', 'N/A')}",
                ]

                if team:
                    team_str = ", ".join(
                        f"{m['name']} ({m.get('role', 'N/A')})" for m in team if m.get("name")
                    )
                    text_parts.append(f"Team: {team_str}")

                if certs:
                    text_parts.append(f"Certifications: {', '.join(c for c in certs if c)}")

                relationships = [
                    {"type": "FOR_CLIENT", "target": client.get("name") if client else None},
                    *[
                        {"type": "DELIVERED_BY", "target": m["name"], "role": m.get("role")}
                        for m in team
                        if m.get("name")
                    ],
                    *[{"type": "REQUIRES_CERT", "target": c} for c in certs if c],
                ]

                results.append(
                    GraphSearchResult(
                        text="\n".join(text_parts),
                        score=1.0,  # Exact match from graph
                        metadata={"source": "knowledge_graph", "entity_id": project.get("id")},
                        entity_type="Project",
                        relationships=[r for r in relationships if r.get("target")],
                    )
                )

        return results

    async def _search_team_members(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Search for team members matching the query."""
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            keywords = [query.lower()]

        cypher = """
        MATCH (t:TeamMember)
        WHERE any(kw IN $keywords WHERE
               toLower(t.name) CONTAINS kw
               OR toLower(t.title) CONTAINS kw
               OR ANY(skill IN t.skills WHERE toLower(skill) CONTAINS kw))
        OPTIONAL MATCH (t)-[:HOLDS]->(cert:Certification)
        OPTIONAL MATCH (t)-[r:DELIVERED]->(p:Project)
        RETURN t,
               collect(DISTINCT cert.name) AS certifications,
               collect(DISTINCT {name: p.name, role: r.role}) AS projects
        LIMIT $limit
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(cypher, keywords=keywords, limit=top_k)
            records = await cursor.data()

            for record in records:
                member = record["t"]
                certs = record.get("certifications", [])
                projects = record.get("projects", [])

                text_parts = [
                    f"Team Member: {member.get('name', 'Unknown')}",
                    f"Title: {member.get('title', 'N/A')}",
                    f"Experience: {member.get('years_experience', 'N/A')} years",
                ]

                if certs:
                    text_parts.append(f"Certifications: {', '.join(c for c in certs if c)}")

                if projects:
                    proj_str = ", ".join(
                        f"{p['name']} ({p.get('role', 'N/A')})" for p in projects if p.get("name")
                    )
                    text_parts.append(f"Projects: {proj_str}")

                relationships = [
                    *[{"type": "HOLDS_CERT", "target": c} for c in certs if c],
                    *[
                        {"type": "DELIVERED_PROJECT", "target": p["name"], "role": p.get("role")}
                        for p in projects
                        if p.get("name")
                    ],
                ]

                results.append(
                    GraphSearchResult(
                        text="\n".join(text_parts),
                        score=0.9,
                        metadata={"source": "knowledge_graph", "entity_id": member.get("id")},
                        entity_type="TeamMember",
                        relationships=[r for r in relationships if r.get("target")],
                    )
                )

        return results

    async def _search_requirements(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Search for tender requirements matching the query."""
        tender_id_filter = self._extract_tender_id_filter(filters)
        ontology_domains = self._ontology_filter_domains(filters)
        keywords = self._query_keywords(query, ontology_domains)

        cypher = """
        MATCH (r:Requirement)
        OPTIONAL MATCH (t:Tender)-[:HAS_REQUIREMENT]->(r)
        WHERE any(kw IN $keywords WHERE
               toLower(r.text) CONTAINS kw
               OR toLower(r.category) CONTAINS kw)
          AND (
            $tender_id IS NULL
            OR coalesce(toString(r.tender_id), toString(t.id), "") = $tender_id
          )
        RETURN r, t
        LIMIT $limit
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(
                cypher,
                keywords=keywords,
                limit=top_k,
                tender_id=tender_id_filter,
            )
            records = await cursor.data()

            for record in records:
                req = record["r"]
                tender = record.get("t")
                result = self._build_requirement_result(
                    req,
                    tender=tender,
                    ontology_domains=ontology_domains,
                )
                if result:
                    result.score += min(self._keyword_overlap(result.text, keywords), 6) * 0.03
                    results.append(result)

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    async def get_compliance_context(self, requirement_text: str) -> list[GraphSearchResult]:
        """Get relevant context for compliance checking."""
        return await self.search(requirement_text, top_k=5)

    async def shutdown(self):
        """Close the Neo4j driver connection."""
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j connection closed")
