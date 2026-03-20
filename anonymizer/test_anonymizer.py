import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import Response

import app as anonymizer_app


def test_rejects_loopback_target_url() -> None:
    client = TestClient(anonymizer_app.app)

    response = client.get(
        "/v1/models",
        headers={"x-target-url": "http://127.0.0.1:8000/internal"},
    )

    assert response.status_code == 400
    assert response.text == "invalid x-target-url header"


@pytest.mark.asyncio
async def test_forwards_allowed_target_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> Response:
        seen["url"] = str(request.url)
        return Response(200, content=b"ok", headers={"content-type": "text/plain"})

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(anonymizer_app.httpx, "AsyncClient", PatchedAsyncClient)
    client = TestClient(anonymizer_app.app)

    response = client.post(
        "/v1/chat/completions",
        headers={"x-target-url": "https://api.openai.com/v1/chat/completions"},
        content=b'{"messages":[]}',
    )

    assert response.status_code == 200
    assert response.text == "ok"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
