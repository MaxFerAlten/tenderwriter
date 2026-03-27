import ipaddress
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from config import get_settings
from engine import AnonymizerEngine
from vault import RedisVault


class AnonymizeRequest(BaseModel):
    text: str | None = None
    chunks: list[str] | None = None
    session_id: str | None = None
    config: dict | None = None


class DeanonymizeRequest(BaseModel):
    text: str
    session_id: str


class ConfigRequest(BaseModel):
    entities: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1)
    strategy: str | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    mask_cig: bool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    vault = RedisVault(
        redis_url=settings.redis_url, default_ttl_seconds=settings.default_ttl_seconds
    )
    await vault.connect()
    stored_config = await vault.load_config()
    if not stored_config:
        await vault.save_config(settings.default_config())
    app.state.settings = settings
    app.state.vault = vault
    app.state.engine = AnonymizerEngine(settings=settings, vault=vault)
    yield
    await vault.close()


app = FastAPI(
    title="tw-anonymizer",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


def _is_allowed_target_url(target_url: str) -> bool:
    try:
        parsed = urlparse(target_url)
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    hostname = (parsed.hostname or "").strip().casefold()
    if not hostname:
        return False
    if hostname in {"localhost", "0.0.0.0", "::1", "metadata.google.internal"}:
        return False
    if hostname.endswith(".localhost"):
        return False

    try:
        import socket
        ip_str = socket.gethostbyname(hostname)
        address = ipaddress.ip_address(ip_str)
    except (ValueError, socket.gaierror):
        return False

    return not any(
        [
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        ]
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tw-anonymizer"}


@app.post("/v1/anonymize")
async def anonymize(payload: AnonymizeRequest, request: Request):
    if not payload.text and not payload.chunks:
        raise HTTPException(status_code=400, detail="either text or chunks is required")

    engine: AnonymizerEngine = request.app.state.engine
    settings = request.app.state.settings

    if payload.text is not None:
        if len(payload.text) > settings.max_chunk_chars:
            raise HTTPException(status_code=400, detail="text exceeds max_chunk_chars")
        return await engine.anonymize_text(
            text=payload.text, session_id=payload.session_id, config=payload.config
        )

    chunks = payload.chunks or []
    if len(chunks) > settings.max_chunks:
        raise HTTPException(status_code=400, detail="too many chunks")
    if any(len(chunk) > settings.max_chunk_chars for chunk in chunks):
        raise HTTPException(status_code=400, detail="one or more chunks exceed max_chunk_chars")
    return await engine.anonymize_chunks(
        chunks=chunks, session_id=payload.session_id, config=payload.config
    )


@app.post("/v1/deanonymize")
async def deanonymize(payload: DeanonymizeRequest, request: Request):
    engine: AnonymizerEngine = request.app.state.engine
    try:
        return await engine.deanonymize_text(text=payload.text, session_id=payload.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/config")
async def get_config(request: Request):
    return await request.app.state.vault.load_config()


@app.post("/v1/config")
async def save_config(payload: ConfigRequest, request: Request):
    settings = request.app.state.settings
    current = settings.default_config()
    current.update(await request.app.state.vault.load_config())
    update = payload.model_dump(exclude_none=True)
    current.update(update)
    return await request.app.state.vault.save_config(current)


@app.get("/v1/stats")
async def get_stats(request: Request):
    return await request.app.state.vault.get_stats()


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def forward(path: str, request: Request) -> Response:
    """Transparent forwarder: target URL must be provided in X-Target-Url header."""
    target_url = request.headers.get("x-target-url")
    if not target_url:
        return Response(
            content=b"missing x-target-url header", status_code=400, media_type="text/plain"
        )
    if not _is_allowed_target_url(target_url):
        return Response(
            content=b"invalid x-target-url header", status_code=400, media_type="text/plain"
        )

    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "x-target-url"}

    async with httpx.AsyncClient(timeout=30) as client:
        upstream_resp = await client.request(
            request.method,
            target_url,
            params=request.query_params,
            content=body,
            headers=headers,
        )

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers={
            k: v
            for k, v in upstream_resp.headers.items()
            if k.lower() in {"content-type", "content-length"}
        },
    )
