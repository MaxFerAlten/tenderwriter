"""
TenderWriter — Application Configuration

All settings are loaded from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from pydantic import model_validator


UNSAFE_DEFAULTS = [
    "changeme_app_secret_key",
    "changeme_pg_password",
    "changeme_neo4j_password",
    "changeme_minio_password",
    "changeme_oo_jwt_secret",
    "changeme",
    "secret",
]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- App ---
    app_name: str = "TenderWriter"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_secret_key: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    
    # --- Auth ---
    admin_username: str = "admin@admin.com"
    admin_password: str = ""
    admin_enabled: bool = True

    # --- PostgreSQL ---
    database_url: str = ""

    # --- Qdrant ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_collection_prefix: str = "tw_"

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # --- Ollama (DEPRECATED - use llama_server instead) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:8b"
    ollama_timeout: int = 120

    # --- Llama Server (for RAG/TenderWriter) ---
    llama_server_url: str = "http://llama-tender:8080/v1"
    llama_model: str = "qwen2.5-coder-7b"
    llama_timeout: int = 300  # 5 minutes for slow CPU inference
    llama_max_tokens: int = 256
    llama_temperature: float = 0.3
    llama_stop_tokens: str = "</s>,<|im_end|>,<|endoftext|>"

    # --- Embeddings ---
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # --- Re-Ranker ---
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- MinIO ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = ""
    minio_bucket: str = "tenderwriter"
    minio_secure: bool = False

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- SMTP (Email) --- REALI
    # smtp_host: str = ""
    # smtp_port: int = 587
    # smtp_user: str = ""
    # smtp_password: str = ""
    # smtp_from: str = "noreply@tenderwriter.ai"
    # smtp_tls: bool = True

    # --- SMTP (Email) --- MAILPIT TEST
    smtp_host: str = "mailpit"   # nome service nel docker-compose
    smtp_port: int = 1025        # SMTP di Mailpit
    smtp_user: str = ""          # non serve
    smtp_password: str = ""      # non serve
    smtp_from: str = "noreply@tenderwriter.ai"
    smtp_tls: bool = False       # niente TLS su 1025

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

    # --- OnlyOffice ---
    onlyoffice_url: str = "http://localhost:8443"  # URL raggiungibile dal browser
    onlyoffice_jwt_secret: str = ""
    onlyoffice_internal_url: str = "http://onlyoffice"  # URL interno Docker
    backend_public_url: str = "http://tw-backend:8000"  # URL raggiungibile dal container OnlyOffice

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode='before')
    @classmethod
    def validate_secrets(cls, values: dict) -> dict:
        """Validate that sensitive settings are not using unsafe defaults."""
        sensitive_fields = {
            'app_secret_key': values.get('app_secret_key', ''),
            'admin_password': values.get('admin_password', ''),
            'database_url': values.get('database_url', ''),
            'neo4j_password': values.get('neo4j_password', ''),
            'minio_secret_key': values.get('minio_secret_key', ''),
            'onlyoffice_jwt_secret': values.get('onlyoffice_jwt_secret', ''),
        }
        
        errors = []
        for field_name, field_value in sensitive_fields.items():
            if not field_value or field_value.strip() == '':
                errors.append(f"{field_name} è obbligatorio e non può essere vuoto")
            elif any(unsafe in field_value.lower() for unsafe in UNSAFE_DEFAULTS):
                errors.append(f"{field_name} usa un valore non sicuro. Cambialo da '{field_value}'")
        
        if errors:
            raise ValueError("; ".join(errors))
        
        return values


# Singleton settings instance
settings = Settings()
