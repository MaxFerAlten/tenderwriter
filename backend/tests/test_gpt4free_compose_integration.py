"""Regression tests for docker-compose GPT4Free wiring."""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class GPT4FreeComposeIntegrationTests(unittest.TestCase):
    def test_docker_compose_exposes_gpt4free_service_and_configurable_backend_llm_url(self) -> None:
        compose_text = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("gpt4free:", compose_text)
        self.assertIn("hlohaus789/g4f:latest-slim", compose_text)
        self.assertIn('user: "0:0"', compose_text)
        self.assertIn(
            "LLAMA_SERVER_URL: ${LLAMA_SERVER_URL:-http://tw-gateway:8080/v1}", compose_text
        )
        self.assertIn(
            "GATEWAY_TENDER_UPSTREAM: ${GATEWAY_TENDER_UPSTREAM:-http://llama-tender:8080}",
            compose_text,
        )
        self.assertIn(
            "GATEWAY_TENDER_DMZ_UPSTREAM: ${GATEWAY_TENDER_DMZ_UPSTREAM:-http://llama-tender:8080}",
            compose_text,
        )
        self.assertIn("gpt4free:\n        condition: service_healthy", compose_text)

    def test_env_templates_route_backend_through_gateway_and_keep_llama_cpp_as_default_gateway_upstream(
        self,
    ) -> None:
        root_env_example = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        backend_env_example = (_REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")

        self.assertIn("LLAMA_SERVER_URL=http://tw-gateway:8080/v1", root_env_example)
        self.assertIn("GATEWAY_TENDER_UPSTREAM=http://llama-tender:8080", root_env_example)
        self.assertIn("GATEWAY_TENDER_DMZ_UPSTREAM=http://llama-tender:8080", root_env_example)
        self.assertEqual(root_env_example.count("GATEWAY_TENDER_UPSTREAM="), 1)
        self.assertIn("EXTERNAL_LLM_URL=", root_env_example)

        for template in (root_env_example, backend_env_example):
            self.assertIn("LLAMA_MODEL=gpt-4o-mini", template)
            self.assertIn("EXTERNAL_LLM_MODEL=gpt-4o-mini", template)


if __name__ == "__main__":
    unittest.main()
