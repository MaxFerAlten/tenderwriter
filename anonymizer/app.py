import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI(title="tw-anonymizer", version="0.1.0", docs_url=None, redoc_url=None)


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
