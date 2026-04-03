# Defect Evidence Ledger - Initial Cut

Data: `2026-04-03`
Scope: primo passo operativo del playbook `test-before-fix / no regressions`.
Stato: `working baseline`, non ancora una verita' finale su tutti i bug.

## Obiettivo

Creare una base di verita' iniziale che separi:

- bug storici gia' chiusi;
- bug ancora plausibili ma da riprodurre;
- difetti attuali fortemente sospetti;
- problemi operativi o strutturali che non vanno trattati come semplici bug di codice.

## Metodo

Sono stati usati tre livelli di evidenza:

1. Markdown del progetto
2. Sorgenti Python/TS e `docker-compose.yml`
3. Test gia' presenti nel repository

## Inventario usato per questo ledger

- File Markdown totali nel workspace: `505`
- File Markdown di progetto, esclusi `node_modules`, `venv`, cache e build: `112`
- File di test rilevati nel progetto: backend, frontend, anonymizer, gateway, ops-agent e KPI engine

## Fonti documentali principali lette o campionate

- `resoningfromagentic/codex/BUG-RESOLUTION.md`
- `resoningfromagentic/antigravity/bug_analysis.md`
- `resoningfromagentic/analisi-critica-comparativa/Analisi-salute-2026-04-03.md`
- `resoningfromagentic/analisi-critica-comparativa/Validazione-critica-osservazioni-2026-04-03.md`
- `resoningfromagentic/analisi-critica-comparativa/verifica-kiro-2026-04-03.md`
- `resoningfromagentic/kiro/LLAMA_SERVER_FIX.md`
- `resoningfromagentic/codex/release-checklist.md`

## Test rilevanti gia' presenti

- `anonymizer/test_ssrf_fix.py`
- `backend/tests/test_bug_fixes.py`
- `backend/tests/test_verified_bugs.py`
- `backend/tests/test_verified_bugs_round2.py`
- `backend/tests/test_rag_anonymizer_routing.py`
- `backend/tests/test_sprint_1_stability.py`
- `backend/tests/test_pre_fix_diagnostics.py`
- `frontend/src/pages/OnlyOfficeEditor.test.ts`

## Legenda classi

- `A`: difetto attuale fortemente confermato dal codice, da trasformare subito in riproduzione eseguibile
- `B`: claim o rischio plausibile, ma serve replay/test diagnostico prima di parlare di fix
- `C`: bug storico probabilmente gia' corretto o protetto da test; non toccare senza test fallente
- `D`: problema operativo/configurativo o comportamento forse intenzionale
- `E`: debito tecnico o rischio strutturale, non un semplice bug puntuale

## Conclusioni preliminari del primo passo

1. I Markdown sono utili ma non completamente allineati allo stato reale del codice.
2. Esistono gia' test storici che dimostrano la chiusura di alcuni bug documentati.
3. Le due aree piu' promettenti per il prossimo passo sono:
- `content_library` senza guardie di autenticazione
- bootstrap BM25 del `SparseRetriever` non eseguito in `HybridRAGEngine.initialize()`
4. Alcuni bug storici molto citati risultano oggi gia' chiusi o superati:
- `BUG-01`
- `BUG-02`
- `BUG-03`
- `BUG-04`
- `BUG-06`
- `BUG-07`
- `BUG-11`
- `BUG-12`
- `BUG-16`
- `BUG-18`

## Ledger iniziale - BUG-01 ... BUG-18

| ID | Claim storico | Evidenza attuale dal sorgente | Test presenti | Classe iniziale | Prossimo passo |
|---|---|---|---|---|---|
| `BUG-01` | `delete_tender` senza `db.commit()` | In `backend/app/api/tenders.py:470-471` ci sono `await db.delete(tender)` e `await db.commit()` | `backend/tests/test_bug_fixes.py::test_bug_01_delete_tender_commits` | `C` | Rieseguire il test storico; non toccare senza fallimento reale |
| `BUG-02` | `ilike` non escapato nei tender | In `backend/app/api/tenders.py:301` la query usa `escaped_search` e `escape="\\\\"` | `backend/tests/test_bug_fixes.py::test_bug_02_sql_injection_ilike_escaped` | `C` | Rieseguire il test storico; usare come modello per altri endpoint simili |
| `BUG-03` | XSS/HTML injection nel PDF export | Diagnostico confermato e fixato: il corpo sezione era gia' escapato da `_content_to_safe_pdf_html()`, ma `proposal.title`, `proposal.client` e `section.title` venivano renderizzati senza Jinja autoescape; `backend/app/tasks.py` ora usa `Environment(... autoescape=select_autoescape(...))` | `backend/tests/test_pre_fix_diagnostics.py::test_pdf_export_template_escapes_all_untrusted_fields` | `B` | Fixato; mantenere il test di rendering come regression guard |
| `BUG-04` | SSRF nell'anonymizer | Regressione riprodotta e richiusa: `_is_allowed_target_url()` risolveva il DNS ma non bloccava IP privati RFC1918; `anonymizer/app.py` ora consente solo target con `address.is_global` | `anonymizer/test_ssrf_fix.py::test_bug_04_ssrf_anonymizer_blocks_internal_dns` + `anonymizer/test_ssrf_fix.py::test_anonymizer_blocks_explicit_private_ip_targets` | `A` | Fixato; mantenere questi test nel ring unificato backend + anonymizer + gateway |
| `BUG-05` | `OnlyOffice /files/{doc_key}` senza auth | Il path non usa `get_current_user`, ma il claim come auth gap non e' riprodotto: `backend/app/api/onlyoffice.py:643-655` richiede firma HMAC + `download_token` owner-bound; test API aggiunti confermano `403` con token owner errato e `200` con token valido | `backend/tests/test_sprint_1_stability.py` helper tests + `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_file_download_rejects_token_for_wrong_owner` + `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_file_download_succeeds_with_valid_signature_and_owner_token` | `C` | Nessuna patch di produzione; mantenere i test endpoint come regression guard |
| `BUG-06` | callback OnlyOffice senza validazione token | Il claim non e' riprodotto sul codice attuale: `backend/app/api/onlyoffice.py:698-699` valida il token e i test endpoint confermano `401` con token associato a un altro documento | `backend/tests/test_sprint_1_stability.py::test_callback_token_must_match_document_key` + `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_callback_rejects_token_bound_to_another_document` + `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_callback_get_probe_is_rejected` | `C` | Nessuna patch di produzione; mantenere i test callback come regression guard |
| `BUG-07` | `asyncio.create_task()` al startup senza error handling | Claim storico non riprodotto: `backend/app/main.py` usa lazy init (`app.state.rag_engine = HybridRAGEngine()`, task `None`), senza `create_task()` nel `lifespan`; coperto da `backend/tests/test_main_route_registration.py::test_lifespan_configures_lazy_rag_initialization` e `::test_lifespan_creates_engine_without_eager_initialization` | `backend/tests/test_main_route_registration.py` | `C` | Nessuna patch di produzione; mantenere i test di lazy init come regression guard |
| `BUG-08` | mutable default SQLAlchemy columns | Claim storico non riprodotto: nel modello corrente non compaiono `default=[]` o `default={}`; coperto da `backend/tests/test_pre_fix_diagnostics.py::test_sqlalchemy_models_do_not_use_mutable_default_literals` | `backend/tests/test_pre_fix_diagnostics.py::test_sqlalchemy_models_do_not_use_mutable_default_literals` | `C` | Nessuna patch di produzione; mantenere il source-guard e valutare a parte i default mutabili nei DTO se diventano rilevanti |
| `BUG-09` | `datetime.utcnow()` naive / timezone mismatch | Claim storico non riprodotto: la scansione corrente su `backend/app` non mostra `datetime.utcnow()` ne' `datetime.now()` naive; il guardrail `backend/tests/test_pre_fix_diagnostics.py::test_backend_code_avoids_naive_datetime_calls` protegge il pattern | `backend/tests/test_pre_fix_diagnostics.py::test_backend_code_avoids_naive_datetime_calls` | `C` | Nessuna patch di produzione; mantenere il guardrail timezone-aware |
| `BUG-10` | cleanup OnlyOffice con `datetime.now()` naive | Claim storico non riprodotto: `backend/app/api/onlyoffice.py:138-142` usa cutoff UTC-aware e conversione `astimezone(timezone.utc)`; coperto da `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_cleanup_deletes_only_documents_older_than_utc_cutoff` | `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_cleanup_deletes_only_documents_older_than_utc_cutoff` | `C` | Nessuna patch di produzione; mantenere il test cleanup timezone-aware |
| `BUG-11` | `UserRegister.email` non validato | Claim storico non riprodotto: `backend/app/api/auth.py:14,63,69,74,79` usa `EmailStr`, e `backend/tests/test_sprint_1_stability.py::test_auth_dtos_require_valid_email_addresses` verifica che `UserRegister`, `UserLogin` e `OTPVerify` rifiutino email invalide | `backend/tests/test_sprint_1_stability.py::test_auth_dtos_require_valid_email_addresses` | `C` | Nessuna patch di produzione; mantenere il test DTO come guardia |
| `BUG-12` | doppio `db.refresh(user)` in registrazione | Claim storico non riprodotto: il blocco `register()` in `backend/app/api/auth.py:267-302` non contiene `await db.refresh(user)`; il guardrail `backend/tests/test_pre_fix_diagnostics.py::test_register_handler_does_not_refresh_user_after_commit` verifica che il commit di registrazione non reintroduca refresh ridondanti | `backend/tests/test_pre_fix_diagnostics.py::test_register_handler_does_not_refresh_user_after_commit` | `C` | Nessuna patch di produzione; mantenere il test source-guard sul register flow |
| `BUG-13` | `proposal.status` letto prima del null check | Claim storico non riprodotto: `backend/app/api/proposals.py:337` usa `proposal.status if proposal else None`; coperto da `backend/tests/test_pre_fix_diagnostics.py::test_proposal_update_reads_previous_status_safely_after_null_guard` | `backend/tests/test_pre_fix_diagnostics.py::test_proposal_update_reads_previous_status_safely_after_null_guard` | `C` | Nessuna patch di produzione; mantenere il source-guard sul null-safe previous_status |
| `BUG-14` | `update_section` con branch identici | Claim storico non riprodotto: `backend/app/api/proposals.py:508-511` normalizza `content` con `_normalize_section_content(value)` prima del `setattr`; coperto da `backend/tests/test_pre_fix_diagnostics.py::test_section_update_normalizes_content_before_setattr` | `backend/tests/test_pre_fix_diagnostics.py::test_section_update_normalizes_content_before_setattr` | `C` | Nessuna patch di produzione; mantenere il guardrail sulla normalizzazione del content |
| `BUG-15` | cache gateway module-level non thread-safe | Diagnostico confermato su `gateway/test_gateway.py::test_dynamic_target_cache_coalesces_concurrent_backend_fetches`: 5 miss concorrenti producevano 5 fetch backend; fix applicato in `gateway/app.py` con `_cache_locks` + double-check TTL | `gateway/test_gateway.py::test_dynamic_target_cache_coalesces_concurrent_backend_fetches` | `A` | Fixato; mantenere il test gateway come regression guard |
| `BUG-16` | utente non verificato puo' fare login | In `backend/app/api/auth.py:398` c'e' controllo `if not user.is_verified`; in `main.py:48-52` esiste anche forzatura admin verificato per bootstrap | `backend/tests/test_bug_fixes.py::test_bug_16_inactive_or_unverified_jwt_rejected` | `C` | Rieseguire il test storico |
| `BUG-17` | `docker.sock` montato nel backend | Il mount e' in `docker-compose.yml:240-251` (`ops-agent`) e `661-675` (`mattermost-bootstrap`), non nel service `backend`; guardrail aggiunto sul compose | `backend/tests/test_schema_deploy_config.py::test_docker_socket_mounts_stay_out_of_backend_service` | `C` | Claim backend corretto nei documenti canonici; mantenere il rischio sicurezza ma con perimetro corretto |
| `BUG-18` | document keys in MD5 prevedibile | In `backend/app/api/onlyoffice.py:244-279,334` si usa `hmac` con `hashlib.sha256`, non `md5` | I test signed URL in `backend/tests/test_sprint_1_stability.py` coprono il modello attuale | `C` | Marcare come storico superseded |

## Nuovi candidati o discrepanze emerse dal sorgente

## `BUG-03` - PDF export autoescape assente su metadata e headings

- Tipo: `output encoding / HTML injection`
- Classe iniziale: `B`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- `backend/app/tasks.py`
- `_content_to_safe_pdf_html()` escapava gia' il corpo delle sezioni
- il template PDF pero' veniva creato con `Template(template_str)` senza autoescape
- campi esposti al render raw:
- `proposal.title`
- `proposal.client`
- `section.title`
- Test presenti:
- `backend/tests/test_pre_fix_diagnostics.py::test_pdf_export_template_escapes_all_untrusted_fields`
- Stato test:
- pre-fix: diagnostico confermato con `xfail`, il rendering conteneva raw `<script>`, `<img onerror>` e `<svg onload>` nei campi metadata/headings
- post-fix: test verde, i campi non trusted vengono escapati, mentre il corpo sezione resta renderizzato tramite `safe_html` gia' sanitizzato
- Patch applicata:
- `backend/app/tasks.py`
- sostituito `Template(template_str)` con `Environment(autoescape=select_autoescape(default=True, default_for_string=True)).from_string(template_str)`
- Nota:
- il fix e' volutamente minimo: non cambia il formato del PDF, ma impedisce l'iniezione HTML nei campi interpolati da Jinja
- Prossimo passo:
- mantenere il test di rendering come guardia e, se in futuro si evolve il template PDF, non reintrodurre `Template(...)` senza autoescape

## `CL-01` - Content Library senza autenticazione

- Tipo: `authorization gap`
- Classe iniziale: `A`
- Stato corrente: `FIXED / regression-protected`
- Evidenza:
- `backend/app/api/content_library.py`
- route a `63`, `110`, `146`, `166`, `196`, `207`
- nessun `Depends(get_current_user)`
- Test presenti:
- `backend/tests/test_pre_fix_diagnostics.py::test_content_library_write_requires_authentication`
- `backend/tests/test_pre_fix_diagnostics.py::test_content_library_authenticated_write_still_works`
- `backend/tests/test_pre_fix_diagnostics.py::test_content_library_other_routes_require_authentication`
- Stato test:
- pre-fix: diagnostico confermato, POST anonima `201` invece di `401`
- post-fix: test verde, POST anonima `401`
- post-fix: test verde anche sul create autenticato `201`
- post-fix: test verde su `GET`, `PUT`, `DELETE` e `/use` senza auth
- Patch applicata:
- `backend/app/api/content_library.py`
- router protetto con `APIRouter(dependencies=[Depends(get_current_user)])`
- Impatto:
- lettura/scrittura/cancellazione potenzialmente anonima di blocchi riusabili
- area ad alto rischio per integrity e confidentiality
- Prossimo passo:
- mantenere i test come regression guard del router autenticato

## `CL-02` - Search della Content Library con `ilike` non escapato

- Tipo: `validation / search correctness`
- Classe iniziale: `B`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- `backend/app/api/content_library.py:70-73`
- usava `ContentBlock.title.ilike(f"%{search}%")` e `ContentBlock.content.ilike(f"%{search}%")`
- Test presenti:
- `backend/tests/test_pre_fix_diagnostics.py::test_content_library_search_escapes_ilike_wildcards`
- Nota:
- non e' SQL injection classica, ma e' lo stesso pattern storico gia' corretto in `tenders.py`
- Stato test:
- pre-fix: diagnostico confermato, SQL compilato senza clausola `ESCAPE`
- post-fix: test verde con pattern escapato e clausola `ESCAPE '\\'`
- Patch applicata:
- `backend/app/api/content_library.py`
- aggiunta helper `_escape_ilike_search()`
- query di search aggiornata con escaping di `\\`, `%`, `_` e `escape="\\\\"`
- Prossimo passo:
- mantenere il test come regression guard
- in un secondo passaggio, valutare se centralizzare l'escaping `ILIKE` in una utility condivisa con `tenders.py`

## `RAG-01` - Sparse retriever non popolato al bootstrap

- Tipo: `runtime correctness / retrieval gap`
- Classe iniziale: `A`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- `backend/app/rag/engine.py:417-430`
- `DenseRetriever.initialize()` veniva invocato
- `SparseRetriever()` veniva solo istanziato a `425`
- nessuna ricostruzione BM25 durante `initialize()`
- Segnale operativo correlato:
- benchmark storici riportano `sparse_corpus_size = 0`
- Test presenti:
- `backend/tests/test_pre_fix_diagnostics.py::test_dense_retriever_loads_persisted_chunks_from_qdrant_payloads`
- `backend/tests/test_pre_fix_diagnostics.py::test_hybrid_rag_initialization_rebuilds_sparse_index`
- Stato test:
- pre-fix: diagnostico confermato, bootstrap sparse assente
- post-fix: test verde sul caricamento dei payload persistiti da Qdrant
- post-fix: test verde su `HybridRAGEngine.initialize()` che ricostruisce BM25 da payload persistiti
- Patch applicata:
- `backend/app/rag/dense_retriever.py`
- aggiunto `load_persisted_chunks()` con paging su Qdrant `scroll()` e filtraggio dei payload privi di `text`
- `backend/app/rag/engine.py`
- aggiunto `_bootstrap_sparse_retriever()` e invocazione nel bootstrap dell'engine
- `backend/app/rag/sparse_retriever.py`
- docstring aggiornata per riflettere la reale fonte persistente del rebuild
- Nota di rischio residuo:
- il fix ricostruisce BM25 dai payload Qdrant persistiti; se il corpus persistito e' realmente vuoto, il bootstrap restera' correttamente vuoto
- Prossimo passo:
- creare integration test piu' realistico su corpus ingestito end-to-end quando l'ambiente avra' le dipendenze runtime complete

## `GR-01` - GraphRetriever: API driver da validare in esecuzione reale

- Tipo: `uncertain runtime compatibility`
- Classe iniziale: `B`
- Stato corrente: `NOT REPRODUCIBLE ON CURRENT CODE / contract-tested`
- Evidenza:
- `backend/app/rag/graph_retriever.py:288` e `355` usano `session.run(cypher, parameters_={...})`
- gli altri path (`90-98`, `123`, `146-151`, `161`, `178-185`, `196`, `218-229`) usano kwargs o `**project`
- I Markdown raccontano bug storici sui parametri Neo4j, ma il codice attuale non coincide perfettamente con quelle versioni
- Test presenti:
- `backend/tests/test_pre_fix_diagnostics.py::test_graph_retriever_search_uses_parameter_dicts_for_neo4j_queries`
- Stato test:
- test verde: `_search_projects` e `_search_team_members` passano i parametri Cypher via `parameters_` senza kwargs in conflitto
- test verde: il parsing dei record Neo4j simulati produce risultati `Project` e `TeamMember`
- Nota importante:
- nell'ambiente locale corrente il package `neo4j` non e' installato, quindi non e' stato possibile fare una verifica live contro il driver runtime reale
- `backend/pyproject.toml` dichiara comunque `neo4j>=5.26.0`
- Decisione operativa:
- non applicare patch di produzione su `GraphRetriever` in assenza di difetto riprodotto
- tenere il test di contratto come guardia contro regressioni verso il vecchio pattern `query=query`
- Prossimo passo:
- se in futuro avremo Neo4j disponibile in ambiente test, aggiungere un integration test reale con grafo minimo popolato
- non modificare il file senza un replay affidabile

## `GW-01` - Gateway dynamic-target cache stampede su miss concorrenti

- Tipo: `concurrency / backend call amplification`
- Classe iniziale: `A`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- `gateway/app.py`
- esisteva `_cache = {}` condivisa senza lock
- su miss concorrenti, piu' richieste sullo stesso `route_kind` entravano insieme nel fetch verso `tw-backend`
- Test presenti:
- `gateway/test_gateway.py::test_dynamic_target_cache_coalesces_concurrent_backend_fetches`
- Stato test:
- pre-fix: diagnostico confermato, 5 chiamate concorrenti a `/health` causavano 5 fetch backend della stessa config dinamica
- post-fix: test verde, i fetch concorrenti vengono coalesced a 1
- Patch applicata:
- `gateway/app.py`
- aggiunto `_cache_locks` per `route_kind`
- aggiunta helper `_get_cached_dynamic_targets()`
- aggiunto double-check TTL dentro la sezione critica prima del fetch remoto
- Verifica aggiuntiva:
- `pytest gateway/test_gateway.py -q`
- esito verde su tutta la suite gateway locale (`7 passed`)
- Nota:
- il problema corretto e' principalmente uno stampede di fetch concorrenti, non una corruzione del dizionario cache

## `OO-01` - OnlyOffice `/files/{doc_key}` protetto da firma e owner-bound token

- Tipo: `historical claim validation / endpoint authorization model`
- Classe iniziale: `B`
- Stato corrente: `NOT REPRODUCIBLE AS AUTH GAP / regression-protected`
- Evidenza:
- `backend/app/api/onlyoffice.py:643-655`
- l'endpoint non usa `get_current_user`, ma richiede due guardie cumulative:
- verifica firma HMAC della URL
- verifica `download_token` coerente con `doc_key` e `owner_user_id`
- Test presenti:
- `backend/tests/test_sprint_1_stability.py::test_signed_file_url_contains_valid_signature`
- `backend/tests/test_sprint_1_stability.py::test_signed_file_url_rejects_tampered_signature`
- `backend/tests/test_sprint_1_stability.py::test_download_token_is_bound_to_document_owner`
- `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_file_download_rejects_token_for_wrong_owner`
- `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_file_download_succeeds_with_valid_signature_and_owner_token`
- Stato test:
- test helper gia' presenti sul modello crittografico
- test endpoint verde: firma valida + token owner errato => `403`
- test endpoint verde: firma valida + token owner corretto => `200`
- Decisione operativa:
- non trattare piu' questo item come auth bug attuale
- mantenere i test endpoint come guardia contro future semplificazioni pericolose

## `OO-02` - OnlyOffice callback token enforcement verificato sul path HTTP

- Tipo: `historical claim validation / callback security`
- Classe iniziale: `C`
- Stato corrente: `NOT REPRODUCIBLE AS TOKEN VALIDATION GAP / regression-protected`
- Evidenza:
- `backend/app/api/onlyoffice.py:698-699`
- il callback rifiuta payload con token non valido rispetto a `payload.key`
- Test presenti:
- `backend/tests/test_sprint_1_stability.py::test_callback_token_must_match_document_key`
- `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_callback_rejects_token_bound_to_another_document`
- `backend/tests/test_pre_fix_diagnostics.py::test_onlyoffice_callback_get_probe_is_rejected`
- Stato test:
- helper gia' verde sul binding token -> document key
- test endpoint verde: `POST` con token riferito a un altro documento => `401`
- test endpoint verde: `GET` probe non e' accettato come callback valido => `405`
- Decisione operativa:
- non servono patch di produzione su questo item
- mantenere i test endpoint come guardia contro future regressioni nella callback

## `LLM-01` - Route `external_anonymized` potrebbe essere design, non bug

- Tipo: `policy / routing ambiguity`
- Classe iniziale: `D`
- Stato corrente: `NOT A BUG ON CURRENT CODE / policy-and-routing-tested`
- Evidenza:
- `backend/app/privacy_policy.py:168-172` forza `policy.mode = "external_anonymized"` in certe condizioni
- `backend/tests/test_rag_anonymizer_routing.py` contiene asserzioni esplicite su `LLMRoute.EXTERNAL_ANONYMIZED`
- `backend/tests/test_privacy_policy.py` conferma che un target esterno + policy/anonimizzazione coerenti producono `external_anonymized`
- `backend/tests/test_rag_anonymizer_routing.py` ora e' eseguibile anche in questo ambiente con shim locali per dipendenze opzionali (`qdrant_client`, `neo4j`, `rank_bm25`)
- `backend/tests/test_anonymizer_admin_api.py` e' ora eseguibile con harness isolato e conferma gli endpoint admin che espongono `external_anonymized`
- Implicazione:
- le latenze elevate possono essere una conseguenza di policy, non di malfunzionamento
- Test presenti:
- `backend/tests/test_privacy_policy.py`
- `backend/tests/test_rag_anonymizer_routing.py`
- `backend/tests/test_anonymizer_admin_api.py`
- Decisione operativa:
- non trattare `external_anonymized` come bug di prodotto sul codice attuale
- usare questi test come guardia se in futuro cambiera' la policy di routing/privacy

## `TEST-03` - `test_schema_inventory.py` instabile in sessione mista per contaminazione `sys.modules`

- Tipo: `test harness isolation`
- Classe iniziale: `D`
- Stato corrente: `FIXED / regression-protected`
- Evidenza:
- il test passava da solo ma falliva nel ring allargato per metadata parziale ereditato da precedenti import di `app.models`
- il loader di `backend/tests/test_schema_inventory.py` ora resetta sia `app.models` sia tutti i sottomoduli `app.models.*` prima di ricaricare `app.db.schema_inventory`
- Test presenti:
- `backend/tests/test_schema_inventory.py`
- ring combinato locale: `103 passed`

## `OPS-01` - Claim documentale su `docker.sock` da correggere

- Tipo: `documentation drift / security scope correction`
- Classe iniziale: `D`
- Stato corrente: `PARTIALLY CLOSED / canonical docs aligned, historical archives left untouched`
- Evidenza:
- `docker-compose.yml:240-251` mount in `ops-agent`
- `docker-compose.yml:661-675` mount in `mattermost-bootstrap`
- nessun mount nel service `backend`
- Test presenti:
- `backend/tests/test_schema_deploy_config.py::test_docker_socket_mounts_stay_out_of_backend_service`
- Aggiornamenti documentali applicati:
- `resoningfromagentic/analisi-critica-comparativa/Analisi-salute-2026-04-03.md`
- `resoningfromagentic/analisi-critica-comparativa/Validazione-critica-osservazioni-2026-04-03.md`
- `resoningfromagentic/analisi-critica-comparativa/Piano-azione-salute-2026-04-03.md`
- `resoningfromagentic/analisi-critica-comparativa/implementation_plan.md`
- Nota:
- i grandi export/storici (`my-output*.md`, `repomix-output.xml.md`, `resoningfromagentic/codex/BUG-RESOLUTION.md`, `resoningfromagentic/antigravity/*`) contengono ancora il claim originario e sono lasciati invariati come archivio di evidenza, non come fonte canonica aggiornata
- Prossimo passo:
- il rischio di sicurezza resta, ma va trattato come hardening dei servizi privilegiati e non come bug del service `backend`

## `SCHEMA-01` - Schema management non versionato nel backend principale

- Tipo: `structural debt`
- Classe iniziale: `E`
- Stato corrente: `CLOSED / raw bootstrap removed, Alembic active locally, compatibility alias retained`
- Evidenza:
- `backend/app/db/database.py:40-67`
- `Base.metadata.create_all()` + `ALTER TABLE ... IF NOT EXISTS`
- `backend/pyproject.toml` dichiara `alembic>=1.14.0`
- scaffold ora presente:
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/README.md`
- `backend/app/db/migrations.py`
- inventory ripetibile ora presente:
- `backend/app/db/schema_inventory.py`
- `backend/tests/test_schema_inventory.py`
- baseline revision ora presente:
- `backend/migrations/versions/20260403_0001_backend_schema_baseline.py`
- la revision congela `BASELINE_TABLES` e un metadata snapshot locale
- la revision crea tabelle mancanti con `metadata.create_all(checkfirst=True)` e assorbe le 4 colonne compat legacy
- switch esplicito ora presente:
- `backend/app/config.py` -> `db_schema_bootstrap_mode`
- `backend/app/db/database.py` supporta `alembic` e `metadata_compat` come alias deprecato
- default corrente: `alembic`
- deploy wiring ora presente:
- `docker-compose.yml` espone `DB_SCHEMA_BOOTSTRAP_MODE`
- `docker-compose.yml` monta `backend/migrations` e `backend/alembic.ini` nel service `backend`
- `.env.example` documenta il default `alembic`
- fix runtime del path Alembic:
- `backend/app/db/database.py` usa `asyncio.to_thread(run_migrations, ...)` per evitare nested event loop errors
- bootstrap raw rimosso:
- `backend/app/db/database.py` non contiene piu' `create_all()` ne' `ALTER TABLE ... IF NOT EXISTS`
- rollout locale effettuato:
- `.env` attivo impostato a `DB_SCHEMA_BOOTSTRAP_MODE=alembic`
- backup creato in `.env.pre-alembic-rollout-2026-04-03.bak`
- `tw-backend` ricreato con successo
- verifiche live verdi su `/health`, `/docs`, `/openapi.json`, login admin e `alembic_version`
- verifica operativa manuale disponibile:
- `backend/app/check_db_schema.py`
- output verificato: bootstrap `alembic`, `alembic_version = 20260403_0001`, `PUBLIC_TABLE_COUNT = 30`
- riferimento interno riusabile: `kpi-reason-engine/migrations/env.py` + `kpi-reason-engine/app/migrations.py`
- runbook di supporto creato: `resoningfromagentic/analisi-critica-comparativa/Schema-Migration-Readiness-2026-04-03.md`
- Test presenti:
- `backend/tests/test_schema_migration_pre_fix.py::test_backend_declares_alembic_dependency`
- `backend/tests/test_schema_migration_pre_fix.py::test_backend_exposes_versioned_alembic_scaffold`
- `backend/tests/test_schema_migration_pre_fix.py::test_init_db_no_longer_bootstraps_schema_opportunistically`
- `backend/tests/test_schema_migration_pre_fix.py::test_backend_has_initial_baseline_revision`
- `backend/tests/test_schema_inventory.py::test_schema_inventory_captures_compatibility_columns`
- `backend/tests/test_schema_inventory.py::test_baseline_revision_covers_schema_inventory_tables`
- `backend/tests/test_schema_bootstrap_mode.py::test_init_db_supports_explicit_alembic_bootstrap_mode`
- `backend/tests/test_schema_bootstrap_mode.py::test_init_db_metadata_compat_mode_delegates_to_alembic_for_backward_compatibility`
- `backend/tests/test_schema_migration_live_replay.py::test_live_upgrade_head_on_empty_database_creates_baseline_schema`
- `backend/tests/test_schema_migration_live_replay.py::test_live_upgrade_head_on_historical_shape_adds_compat_columns_and_missing_tables`
- `backend/tests/test_schema_deploy_config.py::test_backend_service_exposes_schema_bootstrap_mode_env`
- `backend/tests/test_schema_deploy_config.py::test_backend_service_mounts_alembic_assets_for_dev_rollout`
- `backend/tests/test_schema_containerized_rollout.py::test_backend_one_off_container_bootstraps_via_alembic_mode`
- `backend/tests/test_schema_containerized_rollout.py::test_backend_one_off_container_uses_alembic_deploy_default`
- `backend/tests/test_schema_containerized_rollout.py::test_backend_one_off_container_keeps_metadata_compat_as_alembic_alias`
- `backend/tests/test_schema_bootstrap_defaults.py::test_code_and_deploy_defaults_prefer_alembic`
- `backend/tests/test_schema_check_script.py::test_check_db_schema_reports_alembic_state_and_gateway_columns`
- Stato test:
- verde: il backend dichiara Alembic come dipendenza
- verde: lo scaffold Alembic minimo del backend principale ora esiste
- verde: l'inventory del metadata espone in modo ripetibile le colonne compat legacy
- verde: esiste una baseline revision iniziale del backend
- verde: `BASELINE_TABLES` della revision copre l'intero inventory corrente
- verde: replay live su PostgreSQL disposable passa sia su DB vuoto sia su DB storico simulato
- verde: `init_db()` supporta un bootstrap esplicito via Alembic
- verde: il default legacy `metadata_compat` resta protetto da test
- verde: il wiring di deploy espone e monta correttamente gli asset Alembic
- verde: un one-off container `backend` con `DB_SCHEMA_BOOTSTRAP_MODE=alembic` inizializza correttamente un DB disposable
- verde: un one-off container `backend` usa correttamente il default `alembic` anche senza override esplicito
- verde: il default di codice e deploy ora preferisce `alembic`
- verde: il backend locale attivo e' stato portato in `alembic` mode con smoke positivi
- verde: `init_db()` non esegue piu' bootstrap schema raw
- verde: `metadata_compat` resta utilizzabile solo come alias deprecato verso Alembic
- Prossimo passo:
- considerare un breve soak period prima di rimuovere anche l'alias `metadata_compat`

## `TEST-01` - Gap iniziale di copertura sulle aree piu' sospette

- Tipo: `coverage gap`
- Classe iniziale: `E`
- Stato corrente: `CLOSED / local non-regression ring established`
- Evidenza storica:
- in partenza mancavano test dedicati per `content_library`
- in partenza mancavano test dedicati per bootstrap BM25 all'avvio
- Copertura ora presente:
- `backend/tests/test_pre_fix_diagnostics.py` copre `CL-01`, `CL-02`, `RAG-01`, guardrail auth/OnlyOffice/source-level
- `backend/tests/test_main_route_registration.py` copre il lazy init del backend
- `backend/tests/test_schema_migration_pre_fix.py` apre il ring pre-fix per `SCHEMA-01`
- `backend/tests/test_sprint_1_stability.py` e' rientrato nel ring con loader test-only per auth/tasks/OnlyOffice
- `backend/tests/test_bug_fixes.py`, `backend/tests/test_tender_requirement_response.py` e `backend/tests/test_tender_title_uniqueness.py` sono ora eseguibili con harness condiviso `backend/test_module_loaders.py`
- `backend/tests/test_compliance_observability.py`, `backend/tests/test_kpi_reason_engine.py`, `backend/tests/test_operational_workflow.py` e `backend/tests/test_rag_history.py` sono ora eseguibili nello stesso ambiente locale
- `backend/tests/test_verified_bugs.py` e `backend/tests/test_verified_bugs_round2.py` non dipendono piu' dal `cwd` per leggere i sorgenti
- Stato ring:
- `pytest backend/tests -q -rxX` => `168 passed, 8 skipped`
- `pytest backend/tests anonymizer gateway/test_gateway.py -q -rxX` => `192 passed, 8 skipped`
- Hardening aggiuntivo:
- `backend/test_module_loaders.py`, `backend/tests/test_sprint_1_stability.py` e `backend/tests/test_schema_inventory.py` ora pre-caricano `app.models` fuori dai `patch.dict(sys.modules, ...)` che prima rimuovevano moduli SQLAlchemy appena importati
- Verifica stretta:
- `pytest backend/tests anonymizer gateway/test_gateway.py -q --maxfail=1 -W error::sqlalchemy.exc.SAWarning` => verde
- rerun standard del ring unificato ora pulito anche dai warning residui

## Raccomandazione per il prossimo passo

Il prossimo passo piu' sicuro e' questo, nell'ordine:

1. mantenere un breve soak period sul backend locale gia' in `alembic`
2. osservare log startup e smoke applicativi durante uso reale
3. solo dopo valutare se rimuovere anche l'alias `metadata_compat`

Motivo:

- i fix puntuali piu' urgenti sono gia' chiusi e protetti da test
- `SCHEMA-01` e' sostanzialmente chiuso sul piano tecnico
- l'unica decisione residua e' se e quando eliminare anche l'alias di rollback

## `ANON-01` - Endpoint admin anonymizer non protetti di default

- Tipo: `security configuration drift`
- Classe iniziale: `A`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- `anonymizer/app.py` protegge `/v1/config`, `/v1/stats` e `/v1/deanonymize` solo se `settings.admin_token` e' non vuoto
- `anonymizer/config.py` aveva `admin_token: str = ""`
- `backend/app/config.py` aveva `anonymizer_admin_token: str = ""`
- `docker-compose.yml` passava `ANONYMIZER_ADMIN_TOKEN` al backend con default vuoto e non lo esponeva al service `anonymizer`
- Test presenti:
- `anonymizer/test_anonymizer.py::test_api_denies_protected_endpoints_without_admin_token`
- `backend/tests/test_schema_deploy_config.py::test_anonymizer_admin_token_has_consistent_non_empty_defaults`
- Stato test:
- pre-fix: endpoint admin accessibili senza token quando la config restava di default
- post-fix: endpoint admin negati senza token; wiring sorgente allineato tra backend, compose ed `.env.example`
- Patch applicata:
- `anonymizer/config.py`
- `backend/app/config.py`
- `docker-compose.yml`
- `.env.example`
- Nota:
- la suite `backend/tests/test_anonymizer_admin_api.py` qui non e' eseguibile per dipendenza ambiente mancante (`jose`), quindi la verifica disponibile resta sui ring mirati realmente eseguibili

## `ANON-02` - Fallback anonymizer senza rilevazione `PERSON`

- Tipo: `runtime correctness / graceful degradation`
- Classe iniziale: `B`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- in assenza di Presidio/spaCy model completo, il fallback structured copriva solo `CODICE_FISCALE`, `PARTITA_IVA`, `IBAN`, `CIG`
- il contratto documentato in `anonymizer/README.md` promette anonimizzazione anche di `PERSON`
- Test presenti:
- `anonymizer/test_anonymizer.py::test_engine_anonymize_simple_text`
- `anonymizer/test_anonymizer.py::test_engine_faking_strategy_produces_synthetic_values`
- Stato test:
- pre-fix: `Mario Rossi` rimaneva in chiaro sia in redaction sia in faking quando mancava NER pieno
- post-fix: il fallback riconosce nomi persona con recognizer conservativo e i test tornano verdi
- Patch applicata:
- `anonymizer/recognizers/italian.py`
- aggiunto `PersonNameRecognizer` al path fallback structured

## `VAULT-01` - TTL zero nel vault in-memory non scade subito

- Tipo: `runtime correctness / testability`
- Classe iniziale: `B`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- `anonymizer/vault.py` calcolava `expires_at = now + ttl` ma in lettura usava solo `expires_at < time.time()`
- con `ttl_seconds=0` la sessione poteva risultare ancora viva nello stesso tick
- Test presenti:
- `anonymizer/test_anonymizer.py::test_session_expired_is_not_restored`
- Stato test:
- pre-fix: la sessione `expired` era ancora leggibile subito dopo `store_session(..., ttl_seconds=0)`
- post-fix: TTL `<= 0` non persiste la sessione e il check di expiry usa `<=`
- Patch applicata:
- `anonymizer/vault.py`

## `TEST-02` - Ring combinato backend + anonymizer falsamente rosso per collisione namespace `app`

- Tipo: `test harness / package collision`
- Classe iniziale: `D`
- Stato corrente: `FIXED / regression-protected`
- Evidenza iniziale:
- i test anonymizer importavano moduli top-level (`import app`, `from app import ...`)
- nella stessa sessione Pytest questo ombreggiava il package `backend/app`
- Test presenti:
- ring combinato:
- `backend/tests/test_pre_fix_diagnostics.py`
- `backend/tests/test_main_route_registration.py`
- `backend/tests/test_schema_*`
- `anonymizer/test_anonymizer.py`
- `anonymizer/test_ssrf_fix.py`
- Stato test:
- pre-fix: il ring combinato falliva con `ModuleNotFoundError: No module named 'app.api'; 'app' is not a package`
- post-fix intermedio: ring combinato verde `57 passed`
- stato attuale: ring unificato verde `192 passed, 8 skipped`
- Patch applicata:
- `anonymizer/__init__.py`
- `anonymizer/_test_support.py`
- `anonymizer/test_anonymizer.py`
- `anonymizer/test_ssrf_fix.py`

## Regola operativa derivata da questo primo passo

Per TenderWriter non basta dire "il bug e' noto nei Markdown".
Da qui in poi ogni item deve passare sempre per questa catena:

`claim documentale -> verifica sorgente -> test esistente -> riproduzione -> eventuale patch -> certificazione non-regressione`
