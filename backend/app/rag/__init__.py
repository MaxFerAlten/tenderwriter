"""
TenderWriter — HybridRAG Engine Package

The HybridRAG pipeline combines three retrieval strategies:
1. Dense retrieval (vector similarity via Qdrant)
2. Sparse retrieval (BM25 keyword matching)
3. Graph retrieval (structured knowledge from Neo4j)

Results are fused with Reciprocal Rank Fusion, re-ranked with a cross-encoder,
and used as context for LLM generation via Ollama.
"""
