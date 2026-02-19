"""
TenderWriter — Graph Retriever (Neo4j Knowledge Graph)

Queries the knowledge graph for structured relationships between entities
(projects, team members, certifications, clients, requirements).
Returns structured context that complements the unstructured text
retrieved by dense and sparse retrievers.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from neo4j import AsyncGraphDatabase

from app.config import settings

logger = structlog.get_logger()


@dataclass
class GraphSearchResult:
    """A single result from knowledge graph retrieval."""
    text: str
    score: float
    metadata: dict
    entity_type: str
    relationships: list[dict]


class GraphRetriever:
    """
    Knowledge graph retrieval using Neo4j.

    Provides structured context by querying entity relationships
    that can't be captured by text similarity alone.
    """

    def __init__(self):
        self._driver = None

    async def initialize(self):
        """Connect to Neo4j and ensure schema constraints exist."""
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        # Verify connectivity
        async with self._driver.session() as session:
            result = await session.run("RETURN 1 AS ping")
            await result.single()

        logger.info("Connected to Neo4j", uri=settings.neo4j_uri)

        # Create indexes and constraints
        await self._ensure_schema()

    async def _ensure_schema(self):
        """Create Neo4j indexes and constraints for the knowledge graph."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:TeamMember) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Client) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (cert:Certification) REQUIRE cert.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Requirement) REQUIRE r.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.name)",
            "CREATE INDEX IF NOT EXISTS FOR (t:TeamMember) ON (t.name)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.category)",
        ]

        async with self._driver.session() as session:
            for stmt in constraints + indexes:
                await session.run(stmt)

        logger.info("Neo4j schema constraints ensured")

    # ──────────────────────────────────────────────
    # Ingestion: Build the graph from extracted entities
    # ──────────────────────────────────────────────

    async def add_project(self, project: dict):
        """
        Add a project node and its relationships to the graph.

        Expected keys: id, name, description, category, client, team_members,
                       certifications, value, year
        """
        query = """
        MERGE (p:Project {id: $id})
        SET p.name = $name,
            p.description = $description,
            p.category = $category,
            p.value = $value,
            p.year = $year,
            p.updated_at = datetime()

        // Link to client
        WITH p
        FOREACH (_ IN CASE WHEN $client IS NOT NULL THEN [1] ELSE [] END |
            MERGE (c:Client {name: $client})
            MERGE (p)-[:FOR_CLIENT]->(c)
        )

        // Link to category
        WITH p
        FOREACH (_ IN CASE WHEN $category IS NOT NULL THEN [1] ELSE [] END |
            MERGE (cat:Category {name: $category})
            MERGE (p)-[:HAS_CATEGORY]->(cat)
        )
        """
        async with self._driver.session() as session:
            await session.run(query, **project)

        # Add team member relationships
        for member in project.get("team_members", []):
            await self._link_team_member_to_project(project["id"], member)

        # Add certification relationships
        for cert in project.get("certifications", []):
            await self._link_certification_to_project(project["id"], cert)

        logger.debug("Added project to graph", project_name=project.get("name"))

    async def _link_team_member_to_project(self, project_id: str, member: dict):
        """Link a team member to a project with their role."""
        query = """
        MATCH (p:Project {id: $project_id})
        MERGE (t:TeamMember {id: $member_id})
        SET t.name = $name, t.title = $title
        MERGE (t)-[r:DELIVERED]->(p)
        SET r.role = $role
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                project_id=project_id,
                member_id=member.get("id", member.get("name", "")),
                name=member.get("name", ""),
                title=member.get("title", ""),
                role=member.get("role", ""),
            )

    async def _link_certification_to_project(self, project_id: str, cert_name: str):
        """Link a certification to a project."""
        query = """
        MATCH (p:Project {id: $project_id})
        MERGE (c:Certification {name: $cert_name})
        MERGE (p)-[:REQUIRES_CERT]->(c)
        """
        async with self._driver.session() as session:
            await session.run(query, project_id=project_id, cert_name=cert_name)

    async def add_team_member(self, member: dict):
        """
        Add or update a team member node.

        Expected keys: id, name, title, years_experience, certifications, skills
        """
        query = """
        MERGE (t:TeamMember {id: $id})
        SET t.name = $name,
            t.title = $title,
            t.years_experience = $years_experience,
            t.skills = $skills,
            t.updated_at = datetime()
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                id=member["id"],
                name=member.get("name", ""),
                title=member.get("title", ""),
                years_experience=member.get("years_experience", 0),
                skills=member.get("skills", []),
            )

        # Link certifications
        for cert in member.get("certifications", []):
            cert_query = """
            MATCH (t:TeamMember {id: $member_id})
            MERGE (c:Certification {name: $cert_name})
            MERGE (t)-[:HOLDS]->(c)
            """
            async with self._driver.session() as session:
                await session.run(cert_query, member_id=member["id"], cert_name=cert)

    async def add_requirement(self, requirement: dict, tender_id: str):
        """Add a requirement node linked to a tender context."""
        query = """
        MERGE (r:Requirement {id: $id})
        SET r.text = $text,
            r.category = $category,
            r.priority = $priority
        WITH r
        MERGE (t:Tender {id: $tender_id})
        MERGE (t)-[:HAS_REQUIREMENT]->(r)
        """
        async with self._driver.session() as session:
            await session.run(
                query,
                id=requirement["id"],
                text=requirement.get("text", ""),
                category=requirement.get("category", ""),
                priority=requirement.get("priority", "medium"),
                tender_id=tender_id,
            )

    # ──────────────────────────────────────────────
    # Retrieval: Query the graph for structured context
    # ──────────────────────────────────────────────

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

        # Search projects
        project_results = await self._search_projects(query, top_k, filters)
        results.extend(project_results)

        # Search team members
        member_results = await self._search_team_members(query, top_k, filters)
        results.extend(member_results)

        # Sort by score and take top_k
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

        logger.debug("Graph search complete", query_len=len(query), results=len(results))
        return results

    async def _search_projects(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
    ) -> list[GraphSearchResult]:
        """Search for projects matching the query."""
        # Use CONTAINS for simple text matching
        # In production, consider Neo4j full-text indexes
        cypher = """
        MATCH (p:Project)
        WHERE toLower(p.name) CONTAINS toLower($query)
           OR toLower(p.description) CONTAINS toLower($query)
           OR toLower(p.category) CONTAINS toLower($query)
        OPTIONAL MATCH (p)-[:FOR_CLIENT]->(c:Client)
        OPTIONAL MATCH (p)-[:HAS_CATEGORY]->(cat:Category)
        OPTIONAL MATCH (t:TeamMember)-[r:DELIVERED]->(p)
        OPTIONAL MATCH (p)-[:REQUIRES_CERT]->(cert:Certification)
        RETURN p, c, cat,
               collect(DISTINCT {name: t.name, role: r.role}) AS team,
               collect(DISTINCT cert.name) AS certifications
        LIMIT $top_k
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(cypher, query=query, top_k=top_k)
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
        cypher = """
        MATCH (t:TeamMember)
        WHERE toLower(t.name) CONTAINS toLower($query)
           OR toLower(t.title) CONTAINS toLower($query)
           OR ANY(skill IN t.skills WHERE toLower(skill) CONTAINS toLower($query))
        OPTIONAL MATCH (t)-[:HOLDS]->(cert:Certification)
        OPTIONAL MATCH (t)-[r:DELIVERED]->(p:Project)
        RETURN t,
               collect(DISTINCT cert.name) AS certifications,
               collect(DISTINCT {name: p.name, role: r.role}) AS projects
        LIMIT $top_k
        """

        results: list[GraphSearchResult] = []
        async with self._driver.session() as session:
            cursor = await session.run(cypher, query=query, top_k=top_k)
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

    async def get_compliance_context(self, requirement_text: str) -> list[GraphSearchResult]:
        """
        Find projects and team members related to a specific requirement.

        This is used by the compliance checker to find evidence
        that the team can meet specific tender requirements.
        """
        return await self.search(requirement_text, top_k=5)

    async def shutdown(self):
        """Close the Neo4j driver."""
        if self._driver:
            await self._driver.close()
            logger.info("Neo4j connection closed")
