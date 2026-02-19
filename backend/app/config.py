"""
TenderWriter — Application Configuration

All settings are loaded from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- App ---
    app_name: str = "TenderWriter"
    app_version: str = "0.1.0"
    app_debug: bool = True
    app_secret_key: str = "changeme_app_secret_key"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- PostgreSQL ---
    database_url: str = (
        "postgresql+asyncpg://tenderwriter:changeme_pg_password@localhost:5432/tenderwriter"
    )

    # --- Qdrant ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_collection_prefix: str = "tw_"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme_neo4j_password"

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:8b"
    ollama_timeout: int = 120

    # --- Embeddings ---
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # --- Re-Ranker ---
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- MinIO ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "changeme_minio_password"
    minio_bucket: str = "tenderwriter"
    minio_secure: bool = False

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- RAG Pipeline ---
    rag_top_k_dense: int = 20
    rag_top_k_sparse: int = 20
    rag_top_k_graph: int = 10
    rag_top_k_final: int = 5
    rag_rrf_k: int = 60
    rag_dense_weight: float = 0.4
    rag_sparse_weight: float = 0.3
    rag_graph_weight: float = 0.3

    # --- Chunking ---
    chunk_min_size: int = 200
    chunk_max_size: int = 1500
    chunk_overlap: int = 100

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton settings instance
settings = Settings()
