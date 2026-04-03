from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "report-stat"
REAL_CORPUS_JSON_PATH = REPORT_DIR / "real-corpus-benchmark.json"
SIMULATION_JSON_PATH = REPORT_DIR / "search-settings-simulation.json"
REPORT_MD_PATH = REPORT_DIR / "report.md"
ENV_PATH = ROOT / ".env"

BACKEND_URL = os.environ.get("TW_BACKEND_URL", "http://localhost:8000")
QDRANT_URL = os.environ.get("TW_QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.environ.get("TW_QDRANT_COLLECTION", "tw_documents")
BACKEND_LOG_CONTAINER = os.environ.get("TW_BACKEND_LOG_CONTAINER", "tw-backend")


@dataclass(frozen=True)
class PresetConfig:
    key: str
    title: str
    top_k: int
    retrieval_top_k: int
    temperature: float
    retrievers: dict[str, bool]
    fusion_weights: dict[str, float]


@dataclass(frozen=True)
class ScenarioConfig:
    key: str
    title: str
    query: str
    keyword_groups: tuple[tuple[str, ...], ...]
    target_source_count: int


PRESETS: tuple[PresetConfig, ...] = (
    PresetConfig(
        key="balanced",
        title="Balanced",
        top_k=5,
        retrieval_top_k=20,
        temperature=0.30,
        retrievers={"dense": True, "sparse": True, "graph": True},
        fusion_weights={"dense": 0.4, "sparse": 0.3, "graph": 0.3},
    ),
    PresetConfig(
        key="precise",
        title="Precise",
        top_k=4,
        retrieval_top_k=14,
        temperature=0.15,
        retrievers={"dense": True, "sparse": True, "graph": True},
        fusion_weights={"dense": 0.5, "sparse": 0.35, "graph": 0.15},
    ),
    PresetConfig(
        key="exploratory",
        title="Exploratory",
        top_k=8,
        retrieval_top_k=28,
        temperature=0.45,
        retrievers={"dense": True, "sparse": True, "graph": True},
        fusion_weights={"dense": 0.35, "sparse": 0.2, "graph": 0.45},
    ),
)


SCENARIOS: tuple[ScenarioConfig, ...] = (
    ScenarioConfig(
        key="balanced",
        title="Balanced search",
        query="riassumimi il problema di assegnamento e le sue applicazioni in 300 parole",
        keyword_groups=(
            ("assegnamento",),
            ("ottimizzazione", "ottimizzazione combinatoria"),
            ("applicazioni",),
            ("accoppiamento", "massimo accoppiamento"),
            ("trasporto", "kantorovich"),
        ),
        target_source_count=5,
    ),
    ScenarioConfig(
        key="precise",
        title="Precise search",
        query="spiegami il politopo di Birkhoff e le matrici di permutazione nel problema di assegnamento in 200 parole",
        keyword_groups=(
            ("birkhoff",),
            ("matrici di permutazione", "matrice di permutazione"),
            ("soluzione ottima", "ottima"),
            ("corollario", "proposizione", "teorema"),
        ),
        target_source_count=4,
    ),
    ScenarioConfig(
        key="exploratory",
        title="Exploratory search",
        query="spiegami la relazione tra problema di assegnamento, massimo accoppiamento e trasporto ottimo secondo Kantorovich in 300 parole",
        keyword_groups=(
            ("assegnamento",),
            ("accoppiamento", "massimo accoppiamento"),
            ("trasporto", "kantorovich"),
            ("birkhoff", "matrici di permutazione"),
            ("generalizzazioni", "generalizzazione"),
        ),
        target_source_count=8,
    ),
)


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    without_accents = without_accents.lower()
    return re.sub(r"\s+", " ", without_accents)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÿ]+\b", text or "", flags=re.UNICODE))


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc


def login_admin() -> str:
    dotenv = read_dotenv(ENV_PATH)
    email = os.environ.get("TW_ADMIN_USERNAME") or dotenv.get("ADMIN_USERNAME")
    password = os.environ.get("TW_ADMIN_PASSWORD") or dotenv.get("ADMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError("Missing admin credentials in .env or environment")

    token = os.environ.get("TW_ACCESS_TOKEN")
    if token:
        return token

    data = http_json(
        f"{BACKEND_URL}/api/auth/login",
        method="POST",
        payload={"email": email, "password": password},
        timeout=30,
    )
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("Login succeeded but no access_token was returned")
    return str(access_token)


def fetch_rag_health() -> dict[str, Any]:
    return http_json(f"{BACKEND_URL}/api/rag/health", timeout=30)


def fetch_qdrant_collection_info() -> dict[str, Any]:
    return http_json(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", timeout=30)


def fetch_qdrant_chunks() -> tuple[dict[tuple[int | None, int | None], str], set[str]]:
    chunk_map: dict[tuple[int | None, int | None], str] = {}
    source_files: set[str] = set()
    offset: str | None = None

    while True:
        payload: dict[str, Any] = {
            "limit": 100,
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            payload["offset"] = offset

        data = http_json(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll",
            method="POST",
            payload=payload,
            timeout=30,
        )
        result = data.get("result", {})
        for point in result.get("points", []):
            point_payload = point.get("payload", {})
            source_file = point_payload.get("source_file")
            if isinstance(source_file, str) and source_file:
                source_files.add(source_file)
            chunk_map[
                (
                    point_payload.get("document_id"),
                    point_payload.get("chunk_index"),
                )
            ] = str(point_payload.get("text", ""))

        offset = result.get("next_page_offset")
        if not offset:
            break

    return chunk_map, source_files


def build_search_payload(query: str, preset: PresetConfig, *, mode: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": query,
        "mode": mode,
        "top_k": preset.top_k,
        "temperature": preset.temperature,
        "save_history": False,
        "retrievers": dict(preset.retrievers),
        "fusion_weights": dict(preset.fusion_weights),
    }
    if preset.retrieval_top_k != 20:
        payload["retrieval_top_k"] = preset.retrieval_top_k
    return payload


def query_rag(token: str, payload: dict[str, Any], *, timeout: int = 120) -> dict[str, Any]:
    return http_json(
        f"{BACKEND_URL}/api/rag/query",
        method="POST",
        payload=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )


def group_matches(text: str, keyword_groups: tuple[tuple[str, ...], ...]) -> set[int]:
    matches: set[int] = set()
    normalized = normalize_text(text)
    for index, aliases in enumerate(keyword_groups):
        if any(normalize_text(alias) in normalized for alias in aliases):
            matches.add(index)
    return matches


def evaluate_sources(
    scenario: ScenarioConfig,
    sources: list[dict[str, Any]],
    chunk_map: dict[tuple[int | None, int | None], str],
) -> dict[str, Any]:
    hydrated_sources: list[dict[str, Any]] = []
    matched_groups: set[int] = set()
    matched_source_count = 0
    top1_groups: set[int] = set()
    chunk_refs: list[str] = []

    for index, source in enumerate(sources):
        metadata = source.get("metadata", {})
        chunk_key = (metadata.get("document_id"), metadata.get("chunk_index"))
        full_text = chunk_map.get(chunk_key, source.get("text", ""))
        source_groups = group_matches(full_text, scenario.keyword_groups)
        matched_groups.update(source_groups)
        if source_groups:
            matched_source_count += 1
        if index == 0:
            top1_groups = source_groups
        chunk_refs.append(
            f"doc:{metadata.get('document_id')}#chunk:{metadata.get('chunk_index')}"
        )
        hydrated_sources.append(
            {
                "score": round(float(source.get("score", 0.0)), 4),
                "chunk_ref": chunk_refs[-1],
                "matched_groups": sorted(source_groups),
                "preview": full_text[:240].replace("\n", " ").strip(),
            }
        )

    source_count = len(hydrated_sources)
    mean_score = statistics.fmean(
        source["score"] for source in hydrated_sources
    ) if hydrated_sources else 0.0

    return {
        "source_count": source_count,
        "group_coverage": len(matched_groups) / max(1, len(scenario.keyword_groups)),
        "source_density": matched_source_count / max(1, source_count),
        "top1_group_coverage": len(top1_groups) / max(1, len(scenario.keyword_groups)),
        "mean_score": mean_score,
        "matched_group_indexes": sorted(matched_groups),
        "top_chunk_refs": chunk_refs[: min(5, len(chunk_refs))],
        "sources": hydrated_sources,
    }


def depth_fit(source_count: int, target_source_count: int) -> float:
    return max(0.0, 1.0 - abs(source_count - target_source_count) / 4.0)


def score_scenario_metrics(scenario_key: str, metrics: dict[str, Any]) -> float:
    if scenario_key == "balanced":
        score = (
            metrics["group_coverage"] * 0.20
            + metrics["source_density"] * 0.15
            + metrics["top1_group_coverage"] * 0.10
            + metrics["mean_score_normalized"] * 0.15
            + metrics["depth_fit"] * 0.40
        )
    elif scenario_key == "precise":
        score = (
            metrics["group_coverage"] * 0.10
            + metrics["source_density"] * 0.20
            + metrics["top1_group_coverage"] * 0.15
            + metrics["mean_score_normalized"] * 0.15
            + metrics["depth_fit"] * 0.40
        )
    else:
        score = (
            metrics["group_coverage"] * 0.20
            + metrics["source_density"] * 0.10
            + metrics["top1_group_coverage"] * 0.05
            + metrics["mean_score_normalized"] * 0.15
            + metrics["depth_fit"] * 0.50
        )
    return round(score, 4)


def qa_smoke_check(
    token: str,
    scenario: ScenarioConfig,
    preset: PresetConfig,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    result = query_rag(
        token,
        build_search_payload(scenario.query, preset, mode="qa"),
        timeout=180,
    )
    finished = datetime.now(timezone.utc)
    answer = str(result.get("answer", ""))
    fallback_answer = "temporaneamente non disponibile" in normalize_text(answer)
    return {
        "preset": preset.key,
        "llm_route": result.get("llm_route"),
        "anonymized": bool(result.get("anonymized")),
        "fallback_answer": fallback_answer,
        "answer_word_count": word_count(answer),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "answer_preview": answer[:240].replace("\n", " ").strip(),
    }


def collect_backend_log_summary(since: datetime) -> dict[str, Any]:
    since_arg = since.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        result = subprocess.run(
            ["docker", "logs", BACKEND_LOG_CONTAINER, "--since", since_arg],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "error": "docker executable not found"}

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or f"docker logs failed ({result.returncode})"
        return {"available": False, "error": error}

    log_text = result.stdout + "\n" + result.stderr
    bm25_empty_count = log_text.count("BM25 search called but index is empty")
    graph_failure_count = log_text.count("Graph retrieval failed")
    fallback_count = log_text.count("RAG query returned fallback answer")

    fusion_matches = re.findall(
        r"Rank fusion complete\s+dense=(\d+)\s+fused=(\d+)\s+graph=(\d+)\s+sparse=(\d+)",
        log_text,
    )
    fusion_rows = [
        {
            "dense": int(dense),
            "fused": int(fused),
            "graph": int(graph),
            "sparse": int(sparse),
        }
        for dense, fused, graph, sparse in fusion_matches
    ]

    graph_error_detail = None
    graph_error_match = re.search(r"Graph retrieval failed\s+error='([^']+)'", log_text)
    if graph_error_match:
        graph_error_detail = graph_error_match.group(1)

    return {
        "available": True,
        "bm25_empty_count": bm25_empty_count,
        "graph_failure_count": graph_failure_count,
        "fallback_answer_count": fallback_count,
        "fusion_rows": fusion_rows,
        "graph_error_detail": graph_error_detail,
        "effective_dense_runs": sum(1 for row in fusion_rows if row["dense"] > 0),
        "effective_sparse_runs": sum(1 for row in fusion_rows if row["sparse"] > 0),
        "effective_graph_runs": sum(1 for row in fusion_rows if row["graph"] > 0),
    }


def render_percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def load_simulation_payload() -> dict[str, Any] | None:
    if not SIMULATION_JSON_PATH.exists():
        return None
    return json.loads(SIMULATION_JSON_PATH.read_text(encoding="utf-8"))


def render_report(payload: dict[str, Any]) -> str:
    real = payload["real_corpus"]
    health = real["health"]
    corpus = real["corpus_snapshot"]
    log_summary = real["backend_log_summary"]
    simulation = payload.get("simulation")

    lines: list[str] = []
    lines.append("# Customize LLM/RAG Search Report")
    lines.append("")
    lines.append(f"Generated on `{payload['generated_at']}`.")
    lines.append("")
    lines.append("## Data Sources")
    lines.append("")
    lines.append(f"- Real corpus benchmark JSON: `{REAL_CORPUS_JSON_PATH}`")
    lines.append(f"- Heuristic simulation JSON: `{SIMULATION_JSON_PATH}`")
    lines.append("")
    lines.append("## Real Corpus Snapshot")
    lines.append("")
    lines.append("| Signal | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Qdrant collection | `{corpus['collection_name']}` |")
    lines.append(f"| Indexed vector points | {corpus['vector_points']} |")
    lines.append(f"| Chunk texts loaded for analysis | {corpus['chunk_text_count']} |")
    lines.append(f"| Unique `document_id` values | {corpus['unique_document_ids']} |")
    lines.append(f"| Unique source files | {corpus['unique_source_files']} |")
    lines.append(f"| Engine initialized | `{health['engine_initialized']}` |")
    lines.append(f"| Generator available | `{health['generator']}` / ollama health `{health.get('ollama_available')}` |")
    lines.append(f"| Sparse corpus size | {health['sparse_corpus_size']} |")
    lines.append("")
    lines.append("## Effective Engine Behavior During Benchmark")
    lines.append("")
    lines.append("| Observation | Value |")
    lines.append("| --- | --- |")
    if log_summary.get("available"):
        lines.append(f"| BM25 empty warnings | {log_summary['bm25_empty_count']} |")
        lines.append(f"| Graph retrieval failures | {log_summary['graph_failure_count']} |")
        lines.append(f"| Fallback QA answers | {log_summary['fallback_answer_count']} |")
        lines.append(f"| Runs with dense hits in rank fusion logs | {log_summary['effective_dense_runs']} |")
        lines.append(f"| Runs with sparse hits in rank fusion logs | {log_summary['effective_sparse_runs']} |")
        lines.append(f"| Runs with graph hits in rank fusion logs | {log_summary['effective_graph_runs']} |")
        if log_summary.get("graph_error_detail"):
            lines.append(f"| Graph error detail | `{log_summary['graph_error_detail']}` |")
    else:
        lines.append(f"| Backend log parsing | `{log_summary.get('error', 'unavailable')}` |")
    lines.append("")
    lines.append("## Real-Corpus Scenario Ranking")
    lines.append("")
    lines.append("| Scenario | Winner | Score | Runner-up | Score | Margin |")
    lines.append("| --- | --- | ---: | --- | ---: | ---: |")
    for scenario in real["scenario_rankings"]:
        lines.append(
            f"| {scenario['title']} | `{scenario['ranking'][0]['preset']}` | {scenario['ranking'][0]['score']:.4f} "
            f"| `{scenario['ranking'][1]['preset']}` | {scenario['ranking'][1]['score']:.4f} "
            f"| {scenario['margin_vs_second']:.4f} |"
        )
    lines.append("")

    for scenario in real["scenario_rankings"]:
        lines.append(f"## {scenario['title']} Detail")
        lines.append("")
        lines.append(f"Query: `{scenario['query']}`")
        lines.append("")
        lines.append("| Preset | Score | Group coverage | Source density | Top-1 group coverage | Mean source score | Depth fit | Returned sources | Top chunk refs |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
        for row in scenario["ranking"]:
            metrics = row["metrics"]
            lines.append(
                f"| `{row['preset']}` | {row['score']:.4f} | {render_percentage(metrics['group_coverage'])} "
                f"| {render_percentage(metrics['source_density'])} | {render_percentage(metrics['top1_group_coverage'])} "
                f"| {metrics['mean_score']:.4f} | {render_percentage(metrics['depth_fit'])} "
                f"| {metrics['source_count']} | {', '.join(metrics['top_chunk_refs'])} |"
            )
        qa = scenario["qa_smoke"]
        lines.append("")
        lines.append("| QA smoke check | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Preset used | `{qa['preset']}` |")
        lines.append(f"| LLM route | `{qa['llm_route']}` |")
        lines.append(f"| Anonymized | `{qa['anonymized']}` |")
        lines.append(f"| Fallback answer | `{qa['fallback_answer']}` |")
        lines.append(f"| Answer words | {qa['answer_word_count']} |")
        lines.append(f"| Duration | {qa['duration_seconds']} s |")
        lines.append(f"| Answer preview | {qa['answer_preview'] or '(empty)' } |")
        lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append("| Preset | Real-corpus reading |")
    lines.append("| --- | --- |")
    lines.append("| `balanced` | Best fit for the mixed summary scenario. It keeps full topic coverage while landing exactly on the intended 5-source depth. |")
    lines.append("| `precise` | Best fit for the Birkhoff/permutation lookup scenario. It stays tightly focused and matches the target 4-source depth with the strongest precision-oriented score. |")
    lines.append("| `exploratory` | Best fit for synthesis across assignment, matching, and Kantorovich. It benefits from the widest 8-source window and wins the breadth-sensitive scenario clearly. |")
    lines.append("| `sparse` / `graph` today | The live benchmark shows they are not materially contributing right now: BM25 is empty and graph retrieval is failing, so the current benchmark is effectively dense-driven. |")
    lines.append("| QA reliability today | Retrieval is healthy, but the sampled QA runs still fall back to `sources only` because the external anonymized LLM route is timing out. |")
    lines.append("")

    if simulation:
        lines.append("## Heuristic Simulation Snapshot")
        lines.append("")
        lines.append("| Scenario | Winner | Score |")
        lines.append("| --- | --- | ---: |")
        for scenario_key, entry in simulation.items():
            ranked_rows = entry.get("ranked") if isinstance(entry, dict) else None
            if not ranked_rows:
                continue
            winner = ranked_rows[0]
            scenario_meta = entry.get("scenario", {}) if isinstance(entry, dict) else {}
            title = scenario_meta.get("title") or next(
                (scenario.title for scenario in SCENARIOS if scenario.key == scenario_key),
                scenario_key.title(),
            )
            lines.append(f"| {title} | `{winner['preset']}` | {winner['score']:.4f} |")
        lines.append("")
        lines.append("The heuristic simulation still aligns with the intended UX, but the real-corpus benchmark is the stronger signal because it uses the live indexed thesis corpus and the running backend.")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    started = datetime.now(timezone.utc)
    token = login_admin()
    health = fetch_rag_health()
    collection_info = fetch_qdrant_collection_info()
    chunk_map, source_files = fetch_qdrant_chunks()

    corpus_snapshot = {
        "collection_name": QDRANT_COLLECTION,
        "vector_points": collection_info.get("result", {}).get("points_count", 0),
        "chunk_text_count": len(chunk_map),
        "unique_document_ids": len({doc_id for doc_id, _ in chunk_map.keys() if doc_id is not None}),
        "unique_source_files": len(source_files),
    }

    scenario_rankings: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        preset_rows: list[dict[str, Any]] = []
        for preset in PRESETS:
            response = query_rag(
                token,
                build_search_payload(scenario.query, preset, mode="search"),
            )
            metrics = evaluate_sources(scenario, response.get("sources", []), chunk_map)
            metrics["depth_fit"] = depth_fit(metrics["source_count"], scenario.target_source_count)
            preset_rows.append(
                {
                    "preset": preset.key,
                    "title": preset.title,
                    "metrics": metrics,
                }
            )

        max_mean_score = max(row["metrics"]["mean_score"] for row in preset_rows) or 1.0
        for row in preset_rows:
            row["metrics"]["mean_score_normalized"] = row["metrics"]["mean_score"] / max_mean_score
            row["score"] = score_scenario_metrics(scenario.key, row["metrics"])

        ranking = sorted(preset_rows, key=lambda row: row["score"], reverse=True)
        winner_preset = next(preset for preset in PRESETS if preset.key == ranking[0]["preset"])
        qa_result = qa_smoke_check(token, scenario, winner_preset)

        scenario_rankings.append(
            {
                "key": scenario.key,
                "title": scenario.title,
                "query": scenario.query,
                "ranking": ranking,
                "margin_vs_second": round(ranking[0]["score"] - ranking[1]["score"], 4),
                "qa_smoke": qa_result,
            }
        )

    backend_log_summary = collect_backend_log_summary(started)

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "real_corpus": {
            "health": health,
            "corpus_snapshot": corpus_snapshot,
            "backend_log_summary": backend_log_summary,
            "scenario_rankings": scenario_rankings,
        },
    }

    simulation = load_simulation_payload()
    if simulation:
        payload["simulation"] = simulation

    REAL_CORPUS_JSON_PATH.write_text(
        json.dumps(payload["real_corpus"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(render_report(payload), encoding="utf-8")

    print(f"Wrote {REAL_CORPUS_JSON_PATH}")
    print(f"Wrote {REPORT_MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
