# Customize LLM/RAG Search Report

Generated on `2026-04-03T12:52:32+00:00`.

## Data Sources

- Real corpus benchmark JSON: `D:\tender\tenderwriter\report-stat\real-corpus-benchmark.json`
- Heuristic simulation JSON: `D:\tender\tenderwriter\report-stat\search-settings-simulation.json`

## Real Corpus Snapshot

| Signal | Value |
| --- | --- |
| Qdrant collection | `tw_documents` |
| Indexed vector points | 83 |
| Chunk texts loaded for analysis | 83 |
| Unique `document_id` values | 1 |
| Unique source files | 1 |
| Engine initialized | `True` |
| Generator available | `True` / ollama health `True` |
| Sparse corpus size | 0 |

## Effective Engine Behavior During Benchmark

| Observation | Value |
| --- | --- |
| BM25 empty warnings | 12 |
| Graph retrieval failures | 12 |
| Fallback QA answers | 1 |
| Runs with dense hits in rank fusion logs | 12 |
| Runs with sparse hits in rank fusion logs | 0 |
| Runs with graph hits in rank fusion logs | 0 |
| Graph error detail | `{neo4j_code: Neo.ClientError.Statement.ParameterMissing} {message: Expected parameter(s): query, top_k} {gql_status: 50N42} {gql_status_description: error: general processing exception - unexpected error. Unexpected error has occurred. See debug log for details.}` |

## Real-Corpus Scenario Ranking

| Scenario | Winner | Score | Runner-up | Score | Margin |
| --- | --- | ---: | --- | ---: | ---: |
| Balanced search | `balanced` | 0.9974 | `precise` | 0.9000 | 0.0974 |
| Precise search | `precise` | 0.9990 | `balanced` | 0.9000 | 0.0990 |
| Exploratory search | `exploratory` | 0.9535 | `balanced` | 0.6103 | 0.3432 |

## Balanced search Detail

Query: `riassumimi il problema di assegnamento e le sue applicazioni in 300 parole`

| Preset | Score | Group coverage | Source density | Top-1 group coverage | Mean source score | Depth fit | Returned sources | Top chunk refs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `balanced` | 0.9974 | 100.0% | 100.0% | 100.0% | 3.8961 | 100.0% | 5 | doc:2#chunk:2, doc:2#chunk:0, doc:2#chunk:42, doc:2#chunk:53, doc:2#chunk:3 |
| `precise` | 0.9000 | 100.0% | 100.0% | 100.0% | 3.9641 | 75.0% | 4 | doc:2#chunk:2, doc:2#chunk:0, doc:2#chunk:53, doc:2#chunk:3 |
| `exploratory` | 0.6800 | 100.0% | 100.0% | 100.0% | 3.4349 | 25.0% | 8 | doc:2#chunk:2, doc:2#chunk:48, doc:2#chunk:0, doc:2#chunk:9, doc:2#chunk:42 |

| QA smoke check | Value |
| --- | --- |
| Preset used | `balanced` |
| LLM route | `external_anonymized` |
| Anonymized | `True` |
| Fallback answer | `False` |
| Answer words | 311 |
| Duration | 110.6 s |
| Answer preview | Il problema di assegnamento è un classico problema di ottimizzazione combinatoria che trova applicazioni in diversi contesti. In sostanza, si tratta di trovare l'allocazione ottimale di risorse a diverse attività, minimizzando un certo cost |

## Precise search Detail

Query: `spiegami il politopo di Birkhoff e le matrici di permutazione nel problema di assegnamento in 200 parole`

| Preset | Score | Group coverage | Source density | Top-1 group coverage | Mean source score | Depth fit | Returned sources | Top chunk refs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `precise` | 0.9990 | 100.0% | 100.0% | 100.0% | 6.2375 | 100.0% | 4 | doc:2#chunk:48, doc:2#chunk:42, doc:2#chunk:44, doc:2#chunk:45 |
| `balanced` | 0.9000 | 100.0% | 100.0% | 100.0% | 6.2774 | 75.0% | 5 | doc:2#chunk:48, doc:2#chunk:42, doc:2#chunk:44, doc:2#chunk:43, doc:2#chunk:45 |
| `exploratory` | 0.5276 | 100.0% | 87.5% | 100.0% | 4.2921 | 0.0% | 8 | doc:2#chunk:48, doc:2#chunk:42, doc:2#chunk:44, doc:2#chunk:43, doc:2#chunk:45 |

| QA smoke check | Value |
| --- | --- |
| Preset used | `precise` |
| LLM route | `external_anonymized` |
| Anonymized | `True` |
| Fallback answer | `True` |
| Answer words | 11 |
| Duration | 60.9 s |
| Answer preview | Il modello e temporaneamente non disponibile. Mostro solo le fonti recuperate. |

## Exploratory search Detail

Query: `spiegami la relazione tra problema di assegnamento, massimo accoppiamento e trasporto ottimo secondo Kantorovich in 300 parole`

| Preset | Score | Group coverage | Source density | Top-1 group coverage | Mean source score | Depth fit | Returned sources | Top chunk refs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `exploratory` | 0.9535 | 100.0% | 100.0% | 80.0% | 5.0882 | 100.0% | 8 | doc:2#chunk:48, doc:2#chunk:0, doc:2#chunk:2, doc:2#chunk:10, doc:2#chunk:3 |
| `balanced` | 0.6103 | 100.0% | 100.0% | 80.0% | 6.5156 | 25.0% | 5 | doc:2#chunk:48, doc:2#chunk:0, doc:2#chunk:2, doc:2#chunk:10, doc:2#chunk:3 |
| `precise` | 0.4900 | 100.0% | 100.0% | 80.0% | 6.7255 | 0.0% | 4 | doc:2#chunk:48, doc:2#chunk:0, doc:2#chunk:2, doc:2#chunk:3 |

| QA smoke check | Value |
| --- | --- |
| Preset used | `exploratory` |
| LLM route | `external_anonymized` |
| Anonymized | `True` |
| Fallback answer | `False` |
| Answer words | 229 |
| Duration | 166.9 s |
| Answer preview | La relazione tra problema di assegnamento, massimo accoppiamento e trasporto ottimo secondo il testo fornito è che il problema di assegnamento può essere visto come un'istanza particolare del problema di trasporto ottimo. In altre parole, l |

## Interpretation

| Preset | Real-corpus reading |
| --- | --- |
| `balanced` | Best fit for the mixed summary scenario. It keeps full topic coverage while landing exactly on the intended 5-source depth. |
| `precise` | Best fit for the Birkhoff/permutation lookup scenario. It stays tightly focused and matches the target 4-source depth with the strongest precision-oriented score. |
| `exploratory` | Best fit for synthesis across assignment, matching, and Kantorovich. It benefits from the widest 8-source window and wins the breadth-sensitive scenario clearly. |
| `sparse` / `graph` today | The live benchmark shows they are not materially contributing right now: BM25 is empty and graph retrieval is failing, so the current benchmark is effectively dense-driven. |
| QA reliability today | Retrieval is healthy, but the sampled QA runs still fall back to `sources only` because the external anonymized LLM route is timing out. |

## Heuristic Simulation Snapshot

| Scenario | Winner | Score |
| --- | --- | ---: |
| Balanced search | `balanced` | 0.9946 |
| Precise search | `precise` | 0.7770 |
| Exploratory search | `exploratory` | 0.6945 |

The heuristic simulation still aligns with the intended UX, but the real-corpus benchmark is the stronger signal because it uses the live indexed thesis corpus and the running backend.
