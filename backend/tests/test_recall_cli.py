"""Unit tests for the retrieval baseline CLI."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

_TEST_ENV = {
    "APP_SECRET_KEY": "alpha-key-123456789012345678901234567890",
    "ADMIN_PASSWORD": "test-admin-password-1234567890",
    "DATABASE_URL": "postgresql+asyncpg://tester:securepass@localhost:5432/tenderwriter",
    "NEO4J_PASSWORD": "test-neo4j-password-1234567890",
    "MINIO_SECRET_KEY": "test-minio-password-1234567890",
    "ONLYOFFICE_JWT_SECRET": "office-jwt-token-12345678901234567890",
}
for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)


def _load_recall_cli_module():
    path = Path(__file__).resolve().parents[1] / "app" / "utils" / "recall_cli.py"
    spec = importlib.util.spec_from_file_location("recall_cli_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load recall_cli.py from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecallCliTests(unittest.TestCase):
    def test_default_retrievers_disable_graph_for_baseline(self) -> None:
        module = _load_recall_cli_module()

        args = module.build_parser().parse_args([])

        self.assertEqual(args.retrievers, "dense,sparse")
        self.assertEqual(
            module.parse_retriever_selection(args.retrievers),
            {"dense": True, "sparse": True, "graph": False},
        )

    def test_graph_retriever_is_opt_in(self) -> None:
        module = _load_recall_cli_module()

        self.assertEqual(
            module.parse_retriever_selection("dense,sparse,graph"),
            {"dense": True, "sparse": True, "graph": True},
        )

    def test_graph_opt_in_uses_safe_fusion_weights(self) -> None:
        module = _load_recall_cli_module()

        self.assertEqual(
            module.resolve_baseline_fusion_weights({"dense": True, "sparse": True, "graph": True}),
            {"dense": 0.45, "sparse": 0.35, "graph": 0.15},
        )

    def test_source_page_alias_offsets_are_explicit_cli_defaults(self) -> None:
        module = _load_recall_cli_module()

        args = module.build_parser().parse_args([])

        self.assertEqual(args.source_page_alias_offsets, "0,-3,-4,-5")
        self.assertEqual(
            module.parse_source_page_alias_offsets(args.source_page_alias_offsets),
            (0, -3, -4, -5),
        )

    def test_candidate_weight_grid_includes_safe_graph_profiles(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "utils" / "tune_retrieval_weights.py"
        spec = importlib.util.spec_from_file_location("tune_retrieval_weights_under_test", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load tune_retrieval_weights.py from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        grid = module.build_candidate_grid()

        self.assertIn({"dense": 0.45, "sparse": 0.35, "graph": 0.15}, grid)
        self.assertTrue(any(item["sparse"] >= 0.45 for item in grid))


if __name__ == "__main__":
    unittest.main()
