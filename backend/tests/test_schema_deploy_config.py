"""Source-level deployment guardrails for schema bootstrap rollout."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"


def test_backend_service_exposes_schema_bootstrap_mode_env() -> None:
    """The backend deploy config should expose the bootstrap mode as an explicit env var."""

    compose = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert "DB_SCHEMA_BOOTSTRAP_MODE: ${DB_SCHEMA_BOOTSTRAP_MODE:-alembic}" in compose
    assert "DB_SCHEMA_BOOTSTRAP_MODE=alembic" in env_example


def test_backend_service_mounts_alembic_assets_for_dev_rollout() -> None:
    """The backend dev container should see Alembic files without requiring a rebuild."""

    compose = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")

    assert "- ./backend/migrations:/app/migrations" in compose
    assert "- ./backend/alembic.ini:/app/alembic.ini:ro" in compose


def test_docker_socket_mounts_stay_out_of_backend_service() -> None:
    """The Docker socket should remain confined to the explicitly privileged services."""

    compose = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")
    backend_block = compose.split("\n  backend:\n", 1)[1].split("\n  # --- OnlyOffice", 1)[0]
    ops_agent_block = compose.split("\n  ops-agent:\n", 1)[1].split("\n  # --- Backend", 1)[0]
    mattermost_bootstrap_block = compose.split("\n  mattermost-bootstrap:\n", 1)[1].split(
        "\n  # --- Jitsi Prosody", 1
    )[0]

    assert "/var/run/docker.sock:/var/run/docker.sock" not in backend_block
    assert "/var/run/docker.sock:/var/run/docker.sock" in ops_agent_block
    assert "/var/run/docker.sock:/var/run/docker.sock" in mattermost_bootstrap_block
    assert compose.count("/var/run/docker.sock:/var/run/docker.sock") == 2


def test_anonymizer_admin_token_has_consistent_non_empty_defaults() -> None:
    """Backend and anonymizer should agree on a secure-by-default admin token baseline."""

    compose = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    backend_config = (REPO_ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    anonymizer_config = (REPO_ROOT / "anonymizer" / "config.py").read_text(encoding="utf-8")

    expected = "tw-anonymizer-admin-token-change-me"

    assert (
        f"ANONYMIZER_ADMIN_TOKEN: ${{ANONYMIZER_ADMIN_TOKEN:-{expected}}}" in compose
    )
    assert f"ANONYMIZER_ADMIN_TOKEN={expected}" in env_example
    assert f'anonymizer_admin_token: str = "{expected}"' in backend_config
    assert f'admin_token: str = "{expected}"' in anonymizer_config
