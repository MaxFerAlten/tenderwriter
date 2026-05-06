"""
TenderWriter — Data Explorer API

Endpoints to introspect Qdrant vector collections and Neo4j knowledge graph
for the Data Explorer dashboard.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from qdrant_client import QdrantClient

from app.api.auth import UserResponse, get_current_user
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


def admin_required(current_user: UserResponse = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


async def _get_qdrant_client(request: Request) -> QdrantClient:
    """Get Qdrant client from RAG engine or create a direct connection."""
    engine = getattr(request.app.state, "rag_engine", None)
    if engine and hasattr(engine, "dense_retriever") and engine.dense_retriever:
        client = engine.dense_retriever.client
        if client:
            return client

    try:
        return QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
            timeout=10.0,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Qdrant: {e}") from e


async def _get_neo4j_driver(request: Request):
    """Get Neo4j driver from RAG engine or create a direct connection."""
    engine = getattr(request.app.state, "rag_engine", None)
    if engine and hasattr(engine, "graph_retriever") and engine.graph_retriever:
        driver = engine.graph_retriever._driver
        if driver:
            return driver

    try:
        from neo4j import AsyncGraphDatabase

        return AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Neo4j: {e}") from e


# ── Status ──


@router.get("/status")
async def data_explorer_status(request: Request, _user: UserResponse = Depends(admin_required)):
    """Return RAG engine initialization status and DB connectivity."""
    engine = getattr(request.app.state, "rag_engine", None)
    engine_initialized = bool(engine and getattr(engine, "_initialized", False))

    qdrant_ok = False
    qdrant_collections = 0
    neo4j_ok = False
    neo4j_has_schema = False

    # Test Qdrant connectivity
    try:
        client = await _get_qdrant_client(request)
        cols = await asyncio.to_thread(client.get_collections)
        qdrant_ok = True
        qdrant_collections = len(cols.collections)
    except Exception:
        pass

    # Test Neo4j connectivity
    try:
        driver = await _get_neo4j_driver(request)
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS ping")
            await result.single()
            neo4j_ok = True
            # Check if schema constraints exist
            result = await session.run("SHOW CONSTRAINTS")
            constraints = [r async for r in result]
            neo4j_has_schema = len(constraints) > 0
    except Exception:
        pass

    return {
        "engine_initialized": engine_initialized,
        "qdrant_connected": qdrant_ok,
        "qdrant_collections": qdrant_collections,
        "neo4j_connected": neo4j_ok,
        "neo4j_has_schema": neo4j_has_schema,
        "data_ready": qdrant_ok and neo4j_ok and (qdrant_collections > 0 or neo4j_has_schema),
    }


@router.post("/initialize")
async def initialize_engine(request: Request, _user: UserResponse = Depends(admin_required)):
    """Trigger RAG engine initialization (creates Qdrant collections and Neo4j schema)."""
    engine = getattr(request.app.state, "rag_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="RAG engine not available")

    if getattr(engine, "_initialized", False):
        return {"status": "already_initialized"}

    try:
        await engine.ensure_initialized()
        return {"status": "initialized"}
    except Exception as e:
        logger.error("Engine initialization failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Initialization failed: {e}") from e


# ── Qdrant Introspection ──


@router.get("/qdrant/overview")
async def qdrant_overview(request: Request, _user: UserResponse = Depends(admin_required)):
    """Return Qdrant collections with point counts and config."""
    client = await _get_qdrant_client(request)

    try:
        collections_response = await asyncio.to_thread(client.get_collections)
        collections = []
        for col in collections_response.collections:
            info = await asyncio.to_thread(client.get_collection, col.name)
            vectors_config = info.config.params.vectors
            if hasattr(vectors_config, "size"):
                dimension = vectors_config.size
                distance = vectors_config.distance.value if vectors_config.distance else "unknown"
            else:
                dimension = None
                distance = "multi-vector"

            collections.append(
                {
                    "name": col.name,
                    "points_count": info.points_count or 0,
                    "vectors_count": getattr(info, "vectors_count", info.points_count) or 0,
                    "indexed_vectors_count": getattr(info, "indexed_vectors_count", 0) or 0,
                    "dimension": dimension,
                    "distance": distance,
                    "status": info.status.value if info.status else "unknown",
                    "segments_count": getattr(info, "segments_count", 0) or 0,
                    "on_disk_payload": getattr(info.config.params, "on_disk_payload", False)
                    or False,
                }
            )

        return {"collections": collections}
    except Exception as e:
        logger.error("Qdrant overview failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Qdrant error: {e}") from e


@router.get("/qdrant/collection/{collection_name}/sample")
async def qdrant_sample_points(
    request: Request,
    collection_name: str,
    limit: int = 10,
    offset: int = 0,
    _user: UserResponse = Depends(admin_required),
):
    """Return a sample of points from a Qdrant collection with payloads (no vectors for brevity)."""
    client = await _get_qdrant_client(request)

    try:
        limit = min(limit, 50)
        result = await asyncio.to_thread(
            client.scroll,
            collection_name=collection_name,
            limit=limit,
            offset=offset if offset else None,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result

        items = []
        for p in points:
            payload = dict(p.payload) if p.payload else {}
            text_preview = payload.pop("text", "")
            if len(text_preview) > 300:
                text_preview = text_preview[:300] + "..."
            items.append(
                {
                    "id": str(p.id),
                    "text_preview": text_preview,
                    "metadata": payload,
                }
            )

        return {
            "collection": collection_name,
            "items": items,
            "next_offset": str(next_offset) if next_offset else None,
            "count": len(items),
        }
    except Exception as e:
        logger.error("Qdrant sample failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Qdrant error: {e}") from e


@router.get("/qdrant/collection/{collection_name}/payload-keys")
async def qdrant_payload_keys(
    request: Request,
    collection_name: str,
    _user: UserResponse = Depends(admin_required),
):
    """Analyze payload keys distribution from a sample of points."""
    client = await _get_qdrant_client(request)

    try:
        result = await asyncio.to_thread(
            client.scroll,
            collection_name=collection_name,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = result

        key_stats: dict[str, dict[str, Any]] = {}
        for p in points:
            if not p.payload:
                continue
            for key, value in p.payload.items():
                if key not in key_stats:
                    key_stats[key] = {"count": 0, "type": type(value).__name__, "sample_values": []}
                key_stats[key]["count"] += 1
                if len(key_stats[key]["sample_values"]) < 5:
                    sample = str(value)[:100] if value is not None else None
                    key_stats[key]["sample_values"].append(sample)

        return {
            "collection": collection_name,
            "sampled_points": len(points),
            "keys": key_stats,
        }
    except Exception as e:
        logger.error("Qdrant payload keys failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Qdrant error: {e}") from e


# ── Neo4j Introspection ──


@router.get("/neo4j/overview")
async def neo4j_overview(request: Request, _user: UserResponse = Depends(admin_required)):
    """Return Neo4j node/relationship type counts and schema overview."""
    driver = await _get_neo4j_driver(request)

    try:
        async with driver.session() as session:
            # Node label counts
            result = await session.run(
                "CALL db.labels() YIELD label "
                "CALL { WITH label MATCH (n) WHERE label IN labels(n) RETURN count(n) AS cnt } "
                "RETURN label, cnt ORDER BY cnt DESC"
            )
            node_labels = [{"label": r["label"], "count": r["cnt"]} async for r in result]

            # Relationship type counts
            result = await session.run(
                "CALL db.relationshipTypes() YIELD relationshipType AS type "
                "CALL { WITH type MATCH ()-[r]->() WHERE type(r) = type RETURN count(r) AS cnt } "
                "RETURN type, cnt ORDER BY cnt DESC"
            )
            rel_types = [{"type": r["type"], "count": r["cnt"]} async for r in result]

            # Total counts
            result = await session.run("MATCH (n) RETURN count(n) AS total_nodes")
            record = await result.single()
            total_nodes = record["total_nodes"] if record else 0

            result = await session.run("MATCH ()-[r]->() RETURN count(r) AS total_rels")
            record = await result.single()
            total_rels = record["total_rels"] if record else 0

            # Constraints
            result = await session.run("SHOW CONSTRAINTS")
            constraints = []
            async for r in result:
                constraints.append(
                    {
                        "name": r.get("name", ""),
                        "type": r.get("type", ""),
                        "entity_type": r.get("entityType", ""),
                        "labels_or_types": r.get("labelsOrTypes", []),
                        "properties": r.get("properties", []),
                    }
                )

        return {
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "node_labels": node_labels,
            "relationship_types": rel_types,
            "constraints": constraints,
        }
    except Exception as e:
        logger.error("Neo4j overview failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Neo4j error: {e}") from e


@router.get("/neo4j/sample/{label}")
async def neo4j_sample_nodes(
    request: Request,
    label: str,
    limit: int = 20,
    _user: UserResponse = Depends(admin_required),
):
    """Return sample nodes of a given label with their relationships."""
    driver = await _get_neo4j_driver(request)

    # Sanitize label to prevent injection
    allowed_labels = {
        "Tender",
        "Project",
        "TeamMember",
        "Client",
        "Certification",
        "Category",
        "Requirement",
    }
    if label not in allowed_labels:
        raise HTTPException(
            status_code=400, detail=f"Invalid label. Allowed: {', '.join(sorted(allowed_labels))}"
        )

    limit = min(limit, 50)

    try:
        async with driver.session() as session:
            query = f"MATCH (n:{label}) RETURN n LIMIT $limit"
            result = await session.run(query, limit=limit)
            nodes = []
            async for r in result:
                node = r["n"]
                props = dict(node.items())
                nodes.append(
                    {
                        "id": node.element_id,
                        "labels": list(node.labels),
                        "properties": props,
                    }
                )

            rel_query = (
                f"MATCH (n:{label})-[r]-(m) "
                f"RETURN elementId(n) AS source_id, type(r) AS rel_type, "
                f"properties(r) AS rel_props, labels(m) AS target_labels, "
                f"properties(m) AS target_props, elementId(m) AS target_id "
                f"LIMIT $limit"
            )
            result = await session.run(rel_query, limit=limit * 3)
            relationships = []
            async for r in result:
                relationships.append(
                    {
                        "source_id": r["source_id"],
                        "rel_type": r["rel_type"],
                        "rel_props": dict(r["rel_props"]) if r["rel_props"] else {},
                        "target_id": r["target_id"],
                        "target_labels": list(r["target_labels"]),
                        "target_name": (
                            r["target_props"].get("name")
                            or r["target_props"].get("title")
                            or r["target_props"].get("id")
                            or r["target_props"].get("category")
                            or str(r["target_props"].get("text", ""))[:80]
                        ),
                    }
                )

        return {
            "label": label,
            "nodes": nodes,
            "relationships": relationships,
        }
    except Exception as e:
        logger.error("Neo4j sample failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Neo4j error: {e}") from e


@router.get("/neo4j/graph-snapshot")
async def neo4j_graph_snapshot(
    request: Request,
    limit: int = 100,
    _user: UserResponse = Depends(admin_required),
):
    """Return a snapshot of the graph for visualization (nodes + edges)."""
    driver = await _get_neo4j_driver(request)
    limit = min(limit, 200)

    try:
        async with driver.session() as session:
            result = await session.run(
                "MATCH (n)-[r]->(m) "
                "RETURN elementId(n) AS src_id, labels(n) AS src_labels, "
                "coalesce(n.name, n.title, n.id, n.category, substring(n.text, 0, 80), '') AS src_name, "
                "type(r) AS rel_type, properties(r) AS rel_props, "
                "elementId(m) AS tgt_id, labels(m) AS tgt_labels, "
                "coalesce(m.name, m.title, m.id, m.category, substring(m.text, 0, 80), '') AS tgt_name "
                "LIMIT $limit",
                limit=limit,
            )

            nodes_map: dict[str, dict] = {}
            edges: list[dict] = []

            async for r in result:
                src_id = r["src_id"]
                tgt_id = r["tgt_id"]

                if src_id not in nodes_map:
                    nodes_map[src_id] = {
                        "id": src_id,
                        "label": r["src_labels"][0] if r["src_labels"] else "Unknown",
                        "name": r["src_name"],
                    }
                if tgt_id not in nodes_map:
                    nodes_map[tgt_id] = {
                        "id": tgt_id,
                        "label": r["tgt_labels"][0] if r["tgt_labels"] else "Unknown",
                        "name": r["tgt_name"],
                    }

                edges.append(
                    {
                        "source": src_id,
                        "target": tgt_id,
                        "type": r["rel_type"],
                        "properties": dict(r["rel_props"]) if r["rel_props"] else {},
                    }
                )

            standalone_result = await session.run(
                "MATCH (n) "
                "RETURN elementId(n) AS node_id, "
                "labels(n) AS node_labels, "
                "coalesce(n.name, n.title, n.id, n.category, substring(n.text, 0, 80), '') AS node_name "
                "LIMIT $limit",
                limit=limit,
            )
            async for r in standalone_result:
                node_id = r["node_id"]
                if node_id in nodes_map:
                    continue
                nodes_map[node_id] = {
                    "id": node_id,
                    "label": r["node_labels"][0] if r["node_labels"] else "Unknown",
                    "name": r["node_name"],
                }

        return {
            "nodes": list(nodes_map.values()),
            "edges": edges,
        }
    except Exception as e:
        logger.error("Neo4j graph snapshot failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Neo4j error: {e}") from e
