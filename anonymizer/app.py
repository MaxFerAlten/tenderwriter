import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI(title="tw-anonymizer", version="0.1.0", docs_url=None, redoc_url=None)


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
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True

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
    return {"status": "ok"}


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
