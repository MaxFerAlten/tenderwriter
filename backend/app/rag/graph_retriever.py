"""
TenderWriter — Graph Retriever (Neo4j Knowledge Graph)

Retrieves structured information from the knowledge graph including
projects, team members, certifications, and their relationships.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from neo4j import AsyncGraphDatabase

from app.config import settings

logger = structlog.get_logger()


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
        ]

        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (tnd:Tender) ON (tnd.title)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.name)",
            "CREATE INDEX IF NOT EXISTS FOR (t:TeamMember) ON (t.name)",
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
            r.category = $category,
            r.priority = $priority,
            r.tender_id = $tender_id
        MERGE (t)-[:HAS_REQUIREMENT]->(r)
        """
        tender = tender or {}
        async with self._driver.session() as session:
            await session.run(
                query,
                id=requirement["id"],
                text=requirement["text"],
                category=requirement.get("category", "general"),
                priority=requirement.get("priority", "medium"),
                tender_id=tender_id,
                tender_title=tender.get("title"),
                tender_status=tender.get("status"),
                tender_client=tender.get("client"),
                tender_category=tender.get("category"),
                tender_deadline=tender.get("deadline"),
            )

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

        if tender_id_filter is not None:
            tender_results = await self._search_tenders(query, top_k, filters)
            results.extend(tender_results)
        else:
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
                    text_parts.append(
                        "Known requirements: " + "; ".join(requirement_summaries[:5])
                    )

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
                        f"{m['name']} ({m.get('role', 'N/A')})"
                        for m in team if m.get("name")
                    )
                    text_parts.append(f"Team: {team_str}")

                if certs:
                    text_parts.append(f"Certifications: {', '.join(c for c in certs if c)}")

                relationships = [
                    {"type": "FOR_CLIENT", "target": client.get("name") if client else None},
                    *[{"type": "DELIVERED_BY", "target": m["name"], "role": m.get("role")}
                      for m in team if m.get("name")],
                    *[{"type": "REQUIRES_CERT", "target": c} for c in certs if c],
                ]

                results.append(GraphSearchResult(
                    text="\n".join(text_parts),
                    score=1.0,  # Exact match from graph
                    metadata={"source": "knowledge_graph", "entity_id": project.get("id")},
                    entity_type="Project",
                    relationships=[r for r in relationships if r.get("target")],
                ))

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
                        f"{p['name']} ({p.get('role', 'N/A')})"
                        for p in projects if p.get("name")
                    )
                    text_parts.append(f"Projects: {proj_str}")

                relationships = [
                    *[{"type": "HOLDS_CERT", "target": c} for c in certs if c],
                    *[{"type": "DELIVERED_PROJECT", "target": p["name"], "role": p.get("role")}
                      for p in projects if p.get("name")],
                ]

                results.append(GraphSearchResult(
                    text="\n".join(text_parts),
                    score=0.9,
                    metadata={"source": "knowledge_graph", "entity_id": member.get("id")},
                    entity_type="TeamMember",
                    relationships=[r for r in relationships if r.get("target")],
                ))

        return results

    async def _search_requirements(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Search for tender requirements matching the query."""
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            keywords = [query.lower()]
        tender_id_filter = self._extract_tender_id_filter(filters)

        cypher = """
        MATCH (r:Requirement)
        OPTIONAL MATCH (t:Tender)-[:HAS_REQUIREMENT]->(r)
        WHERE any(kw IN $keywords WHERE
               toLower(r.text) CONTAINS kw
               OR toLower(r.category) CONTAINS kw)
          AND ($tender_id IS NULL OR coalesce(toString(r.tender_id), toString(t.id), "") = $tender_id)
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

                text_parts = [
                    f"Requirement: {req.get('text', 'N/A')}",
                    f"Category: {req.get('category', 'N/A')}",
                    f"Priority: {req.get('priority', 'N/A')}",
                ]
                if tender:
                    text_parts.append(f"Tender: {tender.get('title', tender.get('id', 'N/A'))}")

                results.append(GraphSearchResult(
                    text="\n".join(text_parts),
                    score=0.85,
                    metadata={
                        "source": "knowledge_graph",
                        "entity_id": req.get("id"),
                        "tender_id": req.get("tender_id"),
                    },
                    entity_type="Requirement",
                    relationships=[
                        {"type": "BELONGS_TO_TENDER", "target": tender.get("title") if tender else None}
                    ],
                ))

        return results

    async def get_compliance_context(self, requirement_text: str) -> list[GraphSearchResult]:
        """Get relevant context for compliance checking."""
        return await self.search(requirement_text, top_k=5)

    async def shutdown(self):
        """Close the Neo4j driver connection."""
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j connection closed")
