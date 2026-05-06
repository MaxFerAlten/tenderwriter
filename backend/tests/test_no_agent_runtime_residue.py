from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD_FILE = Path(__file__).resolve()

FORBIDDEN_PATHS = (
    ".tenderclaw",
    "backend/.tenderclaw",
    "backend/agents",
    "backend/api",
    "backend/bridge",
    "backend/cli",
    "backend/commands",
    "backend/core",
    "backend/hooks",
    "backend/mcp",
    "backend/memory",
    "backend/mix_architecture",
    "backend/orchestration",
    "backend/plans",
    "backend/plugins",
    "backend/runtime",
    "backend/schemas",
    "backend/services",
    "backend/skills",
    "backend/telemetry",
    "backend/tenderclaw_config",
    "backend/tools",
    "backend/utils",
    "backend/__init__.py",
    "backend/config.py",
    "backend/main.py",
    "backend/parity_matrix_template.md",
    "backend/package-lock.json",
    ".github/workflows/wave1-ci.yml",
    "tools/health_check_run.py",
    "tools/run_wave1_tests.py",
    "tools/wave1_check_disk.py",
    "tools/wave1_persistence_check.py",
    "tools/wave1_reload_test.py",
    "tools/wave1_restart_simulation.py",
    "tools/wave1_smoke.py",
    "tests/e2e/ollama_e2e_test.py",
)

PRODUCT_SCAN_ROOTS = (
    "backend/app",
    "backend/tests",
    "backend/test_ingestion_api.py",
    "backend/test_module_loaders.py",
    "backend/test_pdf_upload.py",
    "backend/verify_imports.py",
    "backend/e2e_verify.py",
    "frontend",
    "gateway",
    "kpi-reason-engine",
    "utility",
    "tests",
    "docs",
    "docker-compose.yml",
    ".github",
    "AGENTS.md",
    "CLAUDE.md",
)

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
}

FORBIDDEN_TEXT = (
    "TenderClaw",
    "tenderclaw",
    "TENDERCLAW_",
    "backend.main",
    "backend/utils",
    "`utils/Recall.py",
    "`utils/RAGQuality.py",
    "`utils/tune_retrieval_weights.py",
    "`utils/rag_quality_fixtures.json",
    "`utils/evaluation_set.json",
    "python3 utils/Recall.py",
    "python3 utils/RAGQuality.py",
    "python3 utils/tune_retrieval_weights.py",
    "test_tenderclaw",
    "wave1_smoke",
    "test_wave1_resume_minimal",
    "localhost:7000",
)

FORBIDDEN_IMPORT_PATTERNS = (
    "from backend.",
    "import backend.",
)


def _iter_text_files(root: Path):
    if root.is_file():
        if root.suffix in TEXT_SUFFIXES:
            yield root
        return

    if not root.exists():
        return

    for path in root.rglob("*"):
        if path.resolve() == GUARD_FILE:
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def test_agent_runtime_paths_are_absent() -> None:
    present = [path for path in FORBIDDEN_PATHS if (ROOT / path).exists()]
    assert present == []


def test_product_roots_do_not_reference_agent_runtime_or_backend_namespace() -> None:
    offenders: list[str] = []

    for relative_root in PRODUCT_SCAN_ROOTS:
        for path in _iter_text_files(ROOT / relative_root):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            relative_path = path.relative_to(ROOT)

            for forbidden in FORBIDDEN_TEXT:
                if forbidden in text:
                    offenders.append(f"{relative_path}: {forbidden}")

            for forbidden in FORBIDDEN_IMPORT_PATTERNS:
                if forbidden in text:
                    offenders.append(f"{relative_path}: {forbidden}")

    assert offenders == []
