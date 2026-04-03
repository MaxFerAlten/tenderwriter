"""Opt-in smoke checks against the live backend service after Alembic rollout."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

import pytest

RUN_LIVE_SERVICE_SMOKE = os.getenv("TW_RUN_LIVE_SERVICE_SMOKE") == "1"
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
BACKEND_URL = "http://localhost:8000"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE_SERVICE_SMOKE,
    reason="Set TW_RUN_LIVE_SERVICE_SMOKE=1 to run live backend smoke checks.",
)


def _read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _request_json(url: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _request_status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.status


def _docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(REPO_ROOT),
    )
    return result.stdout.strip()


def test_live_backend_health_and_docs_are_available() -> None:
    """The live backend should expose health/docs/openapi while running in Alembic mode."""

    status, payload = _request_json(f"{BACKEND_URL}/health")

    assert status == 200
    assert payload["status"] == "healthy"
    assert _request_status(f"{BACKEND_URL}/docs") == 200
    assert _request_status(f"{BACKEND_URL}/openapi.json") == 200


def test_live_backend_env_and_schema_version_match_alembic_rollout() -> None:
    """The live backend container and DB should both report Alembic rollout state."""

    env_output = _docker(
        "inspect",
        "tw-backend",
        "--format",
        "{{range .Config.Env}}{{println .}}{{end}}",
    )
    version_output = _docker(
        "exec",
        "tw-postgres",
        "psql",
        "-U",
        "tenderwriter",
        "-d",
        "tenderwriter",
        "-At",
        "-c",
        "SELECT version_num FROM alembic_version;",
    )

    assert "DB_SCHEMA_BOOTSTRAP_MODE=alembic" in env_output
    assert version_output == "20260403_0001"


def test_live_backend_admin_login_still_succeeds() -> None:
    """The live backend should still accept admin login after the Alembic rollout."""

    env_values = _read_env_file()
    payload = {
        "email": env_values["ADMIN_USERNAME"],
        "password": env_values["ADMIN_PASSWORD"],
    }

    status, body = _request_json(f"{BACKEND_URL}/api/auth/login", method="POST", payload=payload)

    assert status == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"]
