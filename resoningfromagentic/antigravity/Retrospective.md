CODEX:

ok from 0 to 10 give me a vote on codebase

6.5/10 overall.

It’s clearly above average in ambition and structure: there’s real product thinking here, multiple services, domain modeling, observability work, and a meaningful test suite instead of a toy app. The KPI engine in particular has solid depth.

What keeps it out of the 8-9 range is reliability and polish. I found workflow-state bugs in important lifecycle paths, there’s some environment/test friction, naming/organization is inconsistent in places, and the repo carries a fair amount of generated or noisy material that makes maintenance harder.

My rough split:

- Architecture: 7.5/10
- Product scope: 8/10
- Reliability: 5.5/10
- Developer experience: 5.5/10
- Test discipline: 6.5/10

If we keep tightening lifecycle correctness, trim repo noise, and smooth setup/test ergonomics, this can move to 8/10 without needing a rewrite.

for any dot please create table with "specific case", "motivation explain", "solution proposal"

|specific case|motivation explain|solution proposal|
|---|---|---|
|Overall 6.5/10|Strong product ambition, real multi-service architecture, useful domain modeling, and non-trivial tests. The main drag is operational reliability: important lifecycle/state paths were inconsistent, setup is a bit rough, and the repo has noise that increases maintenance cost.|Focus the next cycle on correctness and maintainability rather than new features: stabilize workflow transitions, clean repo hygiene, standardize testing/setup, and reduce incidental complexity.|
|Architecture 7.5/10|The split between backend, frontend, and kpi-reason-engine is meaningful, not arbitrary. There is a visible domain model and the KPI service has a clear responsibility. The weakness is that state is duplicated across boundaries, so drift bugs become likely.|Define a stricter contract for lifecycle/state transitions, centralize canonical workflow semantics, and add contract/regression tests around service boundaries.|
|Product scope 8/10|The codebase clearly aims at a real business workflow, not a demo. Tender lifecycle, proposal work, observability, and KPI reasoning all point to a credible product direction. The risk is that scope has grown faster than hardening.|Keep the scope, but gate new features behind a “stability budget”: every new lifecycle feature should land with regression tests, API contract notes, and operational fallback behavior.|
|Reliability 5.5/10|This is the biggest weakness. The bugs we just fixed were not cosmetic; they affected user-visible workflow state. That usually means there are still edge cases hiding in transition-heavy paths.|Build out lifecycle truth tables and test them end-to-end. Prioritize invariants such as “failed submission cannot remain submitted” and “closed clarification cannot remain active.”|
|Developer experience 5.5/10|The repo is workable, but not smooth. Test setup needed manual venv intervention, there is mixed repo noise, and naming/organization is uneven in places. That slows onboarding and raises the chance of accidental mistakes.|Add a single bootstrap path for local setup, pin test dependencies, document the happy path, and remove or isolate generated/debug artifacts from the main repo surface.|
|Test discipline 6.5/10|Better than many repos at this stage because tests already exist in the right areas. The gap is that some important lifecycle regressions were still missing, which let real logic bugs survive.|Keep expanding tests around workflow transitions, not just route existence. Favor regression tests that encode business behavior over broad but shallow coverage.|

If you want, I can turn this into a sharper 8/10 plan with prioritized actions for the next 2 sprints.


OPENCODE:

## Potential Bugs Found (23 total)

### High Severity

|Issue|Location|
|---|---|
|**Hardcoded localhost URLs**|`frontend/src/pages/ProposalEditor.tsx:61,148,220,232`, `TaskManager.tsx:69,93,131,151-152,164` - Will fail in production|

### Medium Severity

|Issue|Location|
|---|---|
|**Silent error swallowing**|`TaskManager.tsx:172` - Empty `catch (e) {}` hides bugs|
|**Silent DB migration failures**|`db/database.py:53` - Errors ignored with `pass`|
|**Resource leak**|`services/chat.py:181-182`, `api/onlyoffice.py:93-94` - MinIO response not properly closed|
|**Race condition**|`ObservabilityKPI.tsx:361-392` - `cancelled` flag checked too late|
|**Empty sequence crash**|`kpi-reason-engine/app/analytics.py:1197,1231` - `min()` on empty list|
|**Type safety bypass**|Multiple files - `(import.meta as any).env`|
|**No rate limiting on OTP**|`api/auth.py:166-197` - 5 attempts/minute on verification|

### Low Severity

|Issue|Location|
|---|---|
|**Duplicate `db.refresh()`**|`api/auth.py:192` - Wasted query|
|**Deprecated `get_event_loop()`**|`api/auth.py:139` - Python 3.10+ warning|
|**Global Redis client**|`db/redis.py:9` - No shutdown cleanup|
|**In-memory cache growth**|`api/client.ts:254-255` - Maps grow indefinitely|

Want me to fix any of these bugs?

KIRO:

Faccio un'analisi approfondita del codebase per trovare potenziali bug.


Invoked Context Gatherer
Using context-gatherer to do a thorough codebase analysis and identify all relevant files with potential bugs before diving into specifics.
Now let me provide the comprehensive analysis:

Ora leggo i file chiave per verificare i bug più critici con i miei occhi:

Analyzed code

backend/app/api/auth.py

backend/app/tasks.py

backend/app/rag/engine.py

backend/app/rag/engine.py

backend/app/api/auth.py

backend/app/api/auth.py

backend/app/rag/dense_retriever.py

backend/app/rag/engine.py

main.py

backend/app/rag/dense_retriever.py

frontend/src/api/client.ts

frontend/src/api/client.ts

backend/app/tasks.py
Ho ora una visione chiara e verificata dei bug reali. Ecco l'analisi completa con solo i bug confermati dal codice sorgente:

Bug confermati nel codebase
CRITICI
1. generate_proposal_section_task chiama un metodo inesistente 
tasks.py
 riga 75:

result = await engine.generate(...)  # ❌ HybridRAGEngine non ha metodo .generate()
Il metodo si chiama .query() e accetta un RAGQuery object, non keyword args. Questo task fallisce sempre al runtime.

2. double await db.refresh(user) in register 
auth.py
 riga 193-194:

await db.refresh(user)
await db.refresh(user)  # ❌ doppio refresh inutile, round-trip extra al DB
3. RAG engine inizializzato in background senza error handling 
main.py
 riga 63:

asyncio.create_task(app.state.rag_engine.initialize())
Se l'inizializzazione fallisce, l'errore viene silenziosamente inghiottito. L'app parte con _initialized = False e ogni query RAG lancia RuntimeError senza log chiaro.

4. _ensure_collection è async ma usa solo metodi sync di Qdrant 
dense_retriever.py
 righe 55-68:

async def _ensure_collection(self, name: str):
    collections = self.client.get_collections().collections  # sync
    self.client.create_collection(...)  # sync
Dichiarata async ma non fa nulla di asincrono — non è un crash ma è fuorviante e blocca l'event loop durante le chiamate I/O di rete.

ALTI
5. verify_otp non gestisce più OTP token per lo stesso utente 
auth.py
 riga 211:

result = await db.execute(select(OTPToken).where(OTPToken.user_id == user.id))
otp_record = result.scalar_one_or_none()  # ❌ se esistono 2 token → eccezione MultipleResultsFound
Se un utente richiede l'OTP due volte (senza che il primo scada), ci sono 2 record e scalar_one_or_none() lancia eccezione. Il vecchio token non viene mai cancellato in register.

6. export_proposal_pdf_task — XSS via Jinja2 |safe 
tasks.py
 riga 140:

<p>{{ section.content|safe }}</p>
Il contenuto delle sezioni viene renderizzato senza escaping nel PDF. Se il contenuto proviene da input utente, è un vettore XSS nel documento generato.

7. cleanup_expired_otp usa datetime.utcnow() naive vs timezone-aware 
tasks.py
 riga 196:

delete(OTPToken).where(OTPToken.expires_at < datetime.utcnow())
Se OTPToken.expires_at è timezone-aware (come in auth.py dove si usa datetime.now(timezone.utc)), il confronto con un datetime naive può fallire o dare risultati errati su PostgreSQL.

8. get_async_session() crea un nuovo engine ad ogni chiamata 
tasks.py
 riga 22-25:

def get_async_session():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)  # ❌ nuovo engine ogni volta
Ogni task Celery crea un nuovo connection pool. Con molti task concorrenti si esauriscono le connessioni al DB.

MEDI
9. resolveTenderChatContext — race condition nella cache 
client.ts
 riga 284: la promise viene salvata in cache, ma se due chiamate arrivano quasi simultaneamente prima che la prima risolva, entrambe creano una nuova promise sovrascrivendo la precedente. Il .catch poi non trova cached?.promise === promise e non pulisce correttamente.

10. Redis client creato senza timeout 
redis.py
:

redis_client = redis.from_url(settings.redis_url, decode_responses=True)
# ❌ nessun socket_timeout, connection_timeout
Se Redis è irraggiungibile, le operazioni pendono indefinitamente.

11. send_otp_email è async ma chiama _send_sync_email in un thread executor non gestito 
auth.py
 riga 111: se _send_sync_email lancia eccezione SMTP, l'utente è già registrato nel DB ma non riceve l'OTP — account bloccato senza possibilità di recovery automatico.

SICUREZZA
12. User enumeration in verify_otp

if not user:
    raise HTTPException(status_code=400, detail="User not found")  # ❌ rivela se l'email esiste
Risposta diversa per email inesistente vs OTP errato permette di enumerare gli utenti registrati.

13. admin_password con default vuoto 
config.py
:

admin_password: str = ""
Se ADMIN_PASSWORD non è settata, l'admin viene creato con password vuota e hash_password("") è un hash valido.

I bug più urgenti da fixare sono nell'ordine: #1 (task che crashano sempre), #5 (MultipleResultsFound in produzione), #3 (RAG silenziosamente rotto), #8 (connection pool exhaustion), #13 (admin senza password).


NEMOTROM 3 SUPER:

# 

analizza in code base e cerca i potenziali bug

my-output.md

1 passaggio completato

Ho trovato diversi punti potenzialmente **fragili** o fonte di bug nella codebase che mi hai passato, soprattutto nell’area workflow operativo, KPI/eventi e integrazione OnlyOffice.​

## Possibili bug logici nel workflow operativo

- `derivecontributionstatus`: se `assignedto` è `None` e `sectionstatus` è `INPROGRESS`, il codice ritorna `OPEN` e non c’è nessun percorso che riporti a `REQUESTED` in assenza di assegnatario. Rischio: stato incoerente per contributi “in lavorazione” ma non assegnati.​
    
- `buildsectiontransitionplan`:
    
    - Quando da `INPROGRESS` si passa direttamente ad `APPROVED` viene forzata la creazione di una review completata con outcome `approved`, anche se non esiste nessun passo esplicito di review; questo potrebbe gonfiare gli eventi di review e confondere i KPI.​
        
    - `cancelopenrequests` viene chiamato solo se `assignmentchanged` e `previousassignedto is not None`; se un contributo nasce senza assegnatario e poi viene assegnato, le eventuali richieste pregresse non vengono mai chiuse.​
        

## Incongruenze/eventi duplicati o mancanti

- In `syncsectionoperationalworkflow` si costruisce un `plan` e poi si invocano in sequenza `ensurerequestforassignment`, `marklatestrequestreceived`, `ensureopenreview`, `completereview`, `ensureopenrework`, ecc.; la combinazione di flag può generare sequenze di eventi non intuitive (es. review creata e subito completata nello stesso tick, con emissione multipla di eventi per lo stesso stato).​
    
- In `completereview` si emettono sempre sia `contributionreviewcompleted` sia un evento `reviewapproved` o `reviewchangesrequested`, di fatto duplicando l’informazione outcome per i consumer.​
    
- In `resolveopenreworks` tutti i rework aperti vengono marcati come `RESOLVED` con note di default, anche se erano già parzialmente compilati; override silenzioso di informazioni distribuite.​
    

## Edge case su date e timezone

- Utility `asutc`, `datetimetoiso`, `durationhours`: se un datetime naïve arriva già in UTC ma con interpretazione diversa lato client, lo forzi a UTC senza conversione e i calcoli di durata possono risultare sballati (lateness/SLT, response time, ecc.).​
    
- In `buildcontributionreceivedeventpayload` e funzioni simili, se `requestedat` o `responsereceivedat` sono `None` ritorni `None` per `durationhours` ma continui a esporre altri campi di tempo; consumer che assumono `responseTimeHours` sempre presente potrebbero rompersi.​
    

## Potenziali bug su OnlyOffice e MinIO

- `servedocument`: se i metadati in Redis mancano o sono corrotti, fai fallback a `objectname = dockey` e se il file non esiste logghi un warning e ritorni `404 Document not found`; questo è ok, ma non c’è alcun backoff o tentativo di rebuild, e l’errore si manifesta come “file mancante” anziché “sessione scaduta/corrotta”, che rende il debugging lato client più difficile.​
    
- `onlyofficecallback`: gestisce sia GET che POST; nel caso POST senza `payload` ritorni comunque `error: 0` (successo) invece di segnalare errore, il che può nascondere chiamate malformate del Document Server.​
    

## Possibili bug di mapping / serializzazione

- `buildtendersyncpayload` ordina sezioni e requisiti per `order`/`id`, ma `selectprimaryproposal` sceglie il proposal usando `version`, `createdat` e `id`; se hai proposals con `createdat` `None` o versioni non coerenti, il “primary” può cambiare in modo non deterministico causando salti strani nello snapshot KPI.​
    
- `tendertoresponse`: `lifecyclemetadata` viene estratto da `tender.metadatajson.get("lifecycle")`; se `metadatajson` non è un dict ma una stringa JSON (per improvviso cambiamento di schema), la `.get` lancerà, rompendo l’endpoint per tutte le gare con metadati vecchi.​
    

## API e stati HTTP

- Nelle route di gestione chiarimenti (`drafttenderclarificationresponse`, `submittenderclarificationresponse`, `closetenderclarification`) il caso “clarification non trovata” usa `404` anche quando il tender esiste ma il record è stato cancellato o non appartiene a quel tender; logicamente sarebbe più vicino a `404 Clarification not found` su una subrisorsa, ma attento a non confondere col caso “tender non accessibile” che è anch’esso 404: lato client è impossibile distinguere permesso mancante da record assente.​
    

## Suggerimento per passo successivo

Per andare più in profondità, possiamo concentrarci su una macro-area e fare una revisione riga per riga (es. solo `operationalworkflow.py` + relativi test) proponendo patch concrete. Quale parte preferisci analizzare per prima?

Preparato usando Nemotron 3 Super

si vai in profondità

1 passaggio completato

Vado in profondità sull’**operational workflow** (business logic, stati, eventi KPI) usando il codice reale e il tuo bug report già generato.​

## derive_contribution_status: stati incoerenti

Funzione (rimappata dai nomi snake-case):​

python

`def derive_contribution_status(     *,    section_status: SectionStatus,    assigned_to: int | None,    has_open_rework: bool, ) -> ContributionUnitStatus:     if has_open_rework:        return ContributionUnitStatus.REWORK    if section_status == SectionStatus.APPROVED:        return ContributionUnitStatus.COMPLETED    if section_status == SectionStatus.IN_REVIEW:        return ContributionUnitStatus.IN_REVIEW    if assigned_to is not None and section_status == SectionStatus.IN_PROGRESS:        return ContributionUnitStatus.RECEIVED    if assigned_to is not None:        return ContributionUnitStatus.REQUESTED    return ContributionUnitStatus.OPEN`

Bug/edge case:​

- Sezione `IN_PROGRESS` ma `assigned_to is None` → ritorna `OPEN`. In UI vedrai “sezione in lavorazione” ma contribution “open”, rompendo metriche su “lavoro in corso”.​
    
- Nessun modo di distinguere “TO_DO ma già assegnato” (REQUESTED) da “TO_DO non assegnato” (OPEN) se qualcuno sbaglia a settare status/owner; la funzione è fortemente dipendente da combinazioni coerenti che il resto del codice **non** garantisce.​
    

Fix suggerito:

- Se `section_status == IN_PROGRESS` e non c’è assegnatario, forzare uno stato più esplicito (es. BLOCKED) o almeno loggare errore e mantenere `OPEN` ma con metrica separata.
    
- Valutare esplicitamente `SectionStatus.TODO` quando `assigned_to is not None` per togliere ambiguità:
    

python

`if section_status == SectionStatus.TODO:     return ContributionUnitStatus.REQUESTED if assigned_to is not None else ContributionUnitStatus.OPEN`

## build_section_transition_plan: “piano” troppo aggressivo

Struttura (estratta dai test e dal file):​

python

`@dataclass(slots=True) class SectionTransitionPlan:     cancel_open_requests: bool = False    ensure_request: bool = False    mark_request_received: bool = False    start_review: bool = False    complete_review: bool = False    review_outcome: str | None = None    open_rework: bool = False    resolve_rework: bool = False`

Logica chiave:​

python

`assignment_changed = previous_assigned_to != new_assigned_to if assignment_changed and previous_assigned_to is not None:     plan.cancel_open_requests = True if assignment_changed and new_assigned_to is not None and new_status in (TODO, IN_PROGRESS):     plan.ensure_request = True if new_status == IN_REVIEW and previous_status != IN_REVIEW:     plan.mark_request_received = True    plan.start_review = True    plan.resolve_rework = True if new_status == APPROVED and previous_status != APPROVED:     plan.mark_request_received = True    plan.resolve_rework = True    plan.complete_review = True    plan.review_outcome = "approved"    if previous_status != IN_REVIEW:        plan.start_review = True elif previous_status == IN_REVIEW and new_status in (TODO, IN_PROGRESS):     plan.complete_review = True    plan.review_outcome = "changes_requested"    plan.open_rework = True`

Problemi:​

1. **Cambio assegnatario da None → X non chiude richieste pregresse**
    
    - `cancel_open_requests` scatta solo se `previous_assigned_to is not None`. Se per qualunque motivo esistono `ContributionRequest` aperti su una section non ancora assegnata e poi la assegni, non vengono chiusi.​
        
    - In `ensure_request_for_assignment` poi ti ritrovi potenzialmente più richieste aperte per lo stesso `assigned_to` se lo stato gira più volte TO_DO/IN_PROGRESS.​
        
2. **APPROVED crea review “fantasma”**
    
    - Da `IN_PROGRESS -> APPROVED`: `start_review = True`, `complete_review = True`, `review_outcome = "approved"`, `mark_request_received = True`, `resolve_rework = True`.​
        
    - In `sync_section_operational_workflow` questo genera in coda: `ensure_open_review` (se necessario) + `complete_review` + `resolve_open_reworks`, di fatto creando un ciclo di review completo in un singolo tick, anche se nessuno ha mai messo la section in `IN_REVIEW`.​
        
    - Impatto KPI: sovrastima “review completate” e “tempo medio di review” (spesso zero).​
        
3. **Leaving review sempre “changes_requested”**
    
    - Da `IN_REVIEW` a `IN_PROGRESS`/`TODO` imposta sempre `review_outcome = "changes_requested"` e `open_rework = True`, anche se il caso d’uso potrebbe includere “review annullata” o “review fallback senza richiesta esplicita di rework”.​
        

Fix suggeriti:

- `cancel_open_requests` dovrebbe attivarsi su **ogni** cambio assegnatario, incluso `None → X`, e forse anche su cambio status bloccante.
    
- Limitare il caso “APPROVED fa partire review implicita” (es. permetterlo solo se c’è un feature flag o se non ci sono review storiche), altrimenti richiedere sempre `IN_REVIEW` prima di `APPROVED`.
    
- Aggiungere branch per distinguere “review chiusa senza rework” (p.es. `review_outcome = "cancelled"`) da “changes_requested`.
    

## sync_section_operational_workflow: combinatoria di eventi

Schema sintetico (ribattezzato dai nomi in snake-case):​

python

`async def sync_section_operational_workflow(     db: AsyncSession,    *,    tender_id: int,    section: ProposalSection,    actor_id: int | None,    previous_status: SectionStatus,    previous_assigned_to: int | None, ) -> list[tuple[str, dict]]:     contribution = await ensure_contribution_for_section(...)    plan = build_section_transition_plan(...)    occurred_at = now_utc()    events: list[tuple[str, dict]] = []     if plan.cancel_open_requests and section.assigned_to != previous_assigned_to:        await cancel_open_requests(db, contribution=contribution, keep_user_id=section.assigned_to)     if plan.ensure_request and section.assigned_to is not None:        events.extend(await ensure_request_for_assignment(...))     if plan.mark_request_received:        events.extend(await mark_latest_request_received(...))     if plan.resolve_rework:        events.extend(await resolve_open_reworks(...))     if plan.start_review:        review, created = await ensure_open_review(...)        if created:            events.append(("contribution_review_started", build_review_cycle_started_event_payload(...)))     if plan.complete_review and plan.review_outcome:        events.extend(await complete_review(..., outcome=plan.review_outcome))     if plan.open_rework:        events.extend(await ensure_open_rework(...))     contribution.status = derive_contribution_status(        section_status=section.status or SectionStatus.TODO,        assigned_to=section.assigned_to,        has_open_rework=bool(await load_open_reworks(db, contribution_id=contribution.id)),    )    await db.flush()    return events`

Problemi:​

1. **Sequenza “APPROVED” genera doppia emissione eventi review**
    
    - Caso IN_PROGRESS → APPROVED:
        
        - `ensure_open_review` (crea review aperta, emette `contribution_review_started` se `created=True`).
            
        - `complete_review` la chiude subito, emettendo a sua volta `contribution_review_completed` + `review_approved`.​
            
    - Questo rende la timeline review “start & complete nello stesso istante” per tutti i casi “approvazione diretta”, sporcando indicatori come `reviewDurationHours` e “lead time to approval”.
        
2. **resolve_open_reworks sempre prima di start_review**
    
    - In `plan.entering_review` hai `resolve_rework = True` + `start_review = True`, quindi qualsiasi rework aperto viene automaticamente marcato `RESOLVED` (con note di default) semplicemente entrando in `IN_REVIEW`, anche se nessuno ha effettivamente consegnato il rework.​
        
    - KPI di rework vengono falsati (tutti risolti all’ingresso in review, mai al vero completamento).
        
3. **Derivazione finale di status potenzialmente inconsistente con eventi appena emessi**
    
    - Dopo `complete_review` puoi aver portato `ContributionUnitStatus` a COMPLETED all’interno di `complete_review`, ma alla fine della funzione sovrascrivi comunque con il risultato di `derive_contribution_status`. Se lì la combinazione (status sezione / assigned_to / has_open_rework) non è coerente, puoi riportare lo stato indietro.​
        

Fix suggeriti:

- Spostare `resolve_open_reworks` **dopo** `complete_review` (o parametrizzare), o richiamarlo solo quando il review_outcome è `changes_requested` → `rework_resolved`, non quando entri in review.
    
- In `sync_section_operational_workflow`, usare una logica “non regressiva”:
    

python

`final_status = derive_contribution_status(...) if final_status != contribution.status:     contribution.status = final_status`

oppure fare in modo che `complete_review` non cambi lo status e lasci tutto alla derivazione finale.

## KPI Reason Engine: payload e durate

Dalla libreria eventi KPI:​

- Funzioni tipo `build_contribution_request_created_event_payload`, `build_contribution_assignment_confirmed_event_payload`, `build_contribution_review_completed_event_payload`, `build_rework_requested_event_payload`, ecc. costruiscono dict con campi come `requestedAt`, `dueAt`, `responseTimeHours`, `slaTargetHours`, `isLate`.​
    
- La funzione `_duration_hours` fa `if not start or not end: return None`, quindi molte metriche temporalmente incomplete diventano `null` ma gli eventi continuano a essere emessi.​
    

Problemi di business:​

- Con il pattern “review fantasma” e “rework auto-resolti” di cui sopra, i payload KPI conterranno tempi sempre cortissimi (a volte 0) per review e rework, rovinando medie/p95.
    
- In più, la logica di clean-up/aggiornamento (es. `mark_latest_request_received` che mette `response_received_at` se non presente) viene forzata ogni volta che il piano dice `mark_request_received`, anche se il tempo corretto sarebbe quello della prima vera risposta.​
    

Fix suggeriti:

- Introdurre nel payload un campo `isSyntheticLifecycleEvent` (o simile) quando i cambi di stato derivano da automazioni (es. `APPROVED` senza passare da `IN_REVIEW`), così il Reason Engine può escluderli da certi KPI.
    
- Rendere idempotente `mark_latest_request_received` con una policy chiara: se `response_received_at` esiste già, non toccare `response_summary`/status, per non sovrascrivere annotazioni manuali.
    

## Bug già mappati nel tuo bug_analysis.md

Nel file `resoningfromagentic/antigravity/bug_analysis.md` hai già una lista numerata di bug critici/medi (BUG-01 … BUG-18) che copre:​

- Security (SSRF anonymizer, OnlyOffice senza auth, MD5 doc_key).​
    
- Data integrity (mutable default in colonne SQLAlchemy, datetime naive vs aware, cleanup OnlyOffice con `datetime.now()` locale).​
    
- Logic errors in API (`update_proposal` che dereferenzia `proposal` prima del null-check, `update_section` con if/else identici).​
    

Quindi sul fronte “bug di business logic + KPI” l’area più scoperta rimane proprio l’**operational_workflow** che stiamo sezionando ora.

---

Se vuoi, nel prossimo passo posso proporti direttamente una patch concreta (diff) per `operational_workflow.py` che:

- ripulisce `build_section_transition_plan` e `sync_section_operational_workflow`,
    
- rende esplicite le transizioni valide,
    
- e riduce al minimo gli eventi “sintetici” per non inquinare la Reason Engine. Vuoi che ti proponga un refactor guidato da una tabella di stato (state machine esplicita) o preferisci solo fix mirati alle anomalie che ti ho evidenziato?
    

Preparato usando Nemotron 3 Super

in questa fase devi elencare tutti i problemi e possibili traccie di soluzioni non patch

1 passaggio completato

Elenco tutti i problemi che emergono dall’analisi (operational workflow + resto backend) e, per ciascuno, una possibile **traccia** di soluzione (senza patch dettagliate).​

---

## 1. derive_contribution_status: mapping troppo fragile

Problemi:​

- Sezione `IN_PROGRESS` con `assigned_to is None` → contribution `OPEN`, incoerenza semantica tra sezione “in lavorazione” e contribution “aperto generico”.
    
- Non distingue chiaramente `TODO` assegnata (`REQUESTED`) da casi limite (es. sezione `IN_REVIEW` ma senza assegnatario).
    
- Il mapping dipende da combinazioni “ideali” di `section_status` e `assigned_to` che il resto del sistema non sempre garantisce.
    

Tracce di soluzione (concettuali):

- Definire una matrice formale `(section_status, assigned_to, has_open_rework) → contribution_status` e validarla in test.​
    
- Introdurre uno stato esplicito per “IN_PROGRESS senza owner” (es. `BLOCKED`) o almeno loggare warning e tenerlo separato nei KPI.
    
- Gestire `TODO` in modo esplicito: se assegnata → `REQUESTED`, se non assegnata → `OPEN`.
    

---

## 2. build_section_transition_plan: logica di transizione troppo “magica”

Problemi:​

- `cancel_open_requests` scatta solo quando `previous_assigned_to` non è `None`; se esistono richieste aperte con `assigned_to=None` e poi assegni la sezione, non vengono chiuse.
    
- Transizione `IN_PROGRESS → APPROVED` forza un intero ciclo di review (start + complete) anche se la sezione non ha mai avuto `IN_REVIEW`, generando review “fantasma”.
    
- Uscita da `IN_REVIEW` verso `IN_PROGRESS`/`TODO` imposta sempre `review_outcome="changes_requested"` e `open_rework=True`, anche quando la review non ha realmente richiesto rework.
    
- La combinazione dei flag (start_review, complete_review, resolve_rework, open_rework) è poco leggibile e difficile da controllare in modo esaustivo.
    

Tracce di soluzione:

- Esplicitare una tabella di transizione `(previous_status, new_status)` che definisca: se ci deve essere review, se è richiesta rework, se le richieste vanno cancellate.​
    
- Separare i casi “APPROVED dopo IN_REVIEW” da “APPROVED diretto” e impedire che il secondo crei automaticamente review complete, oppure marcarle come “synthetic”.
    
- Introdurre un outcome aggiuntivo (“cancelled” / “no_changes”) per quando esci da review senza rework.
    
- Normalizzare la logica `assignment_changed`: ogni cambio owner può chiudere richieste non più valide, indipendentemente dal fatto che `previous_assigned_to` fosse `None` o meno.
    

---

## 3. sync_section_operational_workflow: ordine effetti/eventi e stato finale

Problemi:​

- Sequenza “APPROVED” con `start_review + complete_review` nel medesimo ciclo produce eventi `review_started` e `review_completed` a distanza temporale minima, falsando i KPI di durata review.
    
- `resolve_open_reworks` viene eseguito entrando in `IN_REVIEW`, quindi tutti i rework aperti risultano “risolti” anche se la sezione non è stata realmente lavorata.
    
- Alla fine, `contribution.status` viene sempre ricalcolato via `derive_contribution_status` anche se funzioni come `complete_review` hanno già cambiato lo stato; rischio di inconsistenza o regressione.
    
- L’ordine in cui vengono chiamate `cancel_open_requests`, `ensure_request_for_assignment`, `mark_latest_request_received`, `ensure_open_review`, `complete_review`, `ensure_open_rework`, `resolve_open_reworks` è complesso e poco auto‑esplicativo.
    

Tracce di soluzione:

- Definire una sequenza stabile: prima mutazioni (assignment, richieste, review, rework), poi **un solo punto** di derivazione finale dello stato contribution.​
    
- Non fare cambiare `ContributionUnitStatus` dentro `complete_review`/`ensure_open_rework`, ma lasciare che lo stato sia sempre derivato alla fine.
    
- Rinviare `resolve_open_reworks` al momento del completamento review (e solo con outcome “approved”), invece che all’ingresso in review.
    
- Introdurre flag per distinguere eventi “sintetici” (generate automaticamente per far quadrare lo schema) da eventi derivanti da azioni utente.
    

---

## 4. Eventi KPI: distorsione di metriche e incompletezza dati

Problemi:​

- Review virtuali e rework auto-risolti generano tempi artificialmente brevi (anche 0) per `reviewDurationHours`, `reworkDurationHours`, `timeToFirstResponse`.
    
- `_duration_hours` restituisce `None` se uno degli estremi manca; molti eventi così risultano “parziali” e possono rompere aggregazioni se consumer si aspettano sempre un valore numerico.
    
- Funzioni come `mark_latest_request_received` scrivono `response_received_at` e `responsesummary` con default generici (“Auto-received from proposal section workflow”), sovrascrivendo potenzialmente annotazioni manuali.
    

Tracce di soluzione:

- Definire uno schema di eventi con campi opzionali **chiaramente documentati** (quali possono essere null) e aggiornare il Reason Engine per gestire in sicurezza i `null`.
    
- Marcare negli eventi una proprietà tipo `is_automated` / `source="section-workflow"` per distinguere misurazioni “organiche” da quelle derivanti da automazioni.​
    
- Rendere idempotente `mark_latest_request_received`: se esiste già `response_received_at`, non sovrascrivere né tempo né summary, o farlo solo se provengono da un flusso “meno affidabile”.
    
- Introdurre test golden dataset che coprano casi borderline (approve diretto, rework multipli, reassignment) e verifichino che le metriche aggregate non risultino distorte.
    

---

## 5. OnlyOffice: superfici di rischio e incoerenze

Problemi:​

- Endpoint `/files/{doc_key}` senza autenticazione: chiunque conosca il `doc_key` può scaricare file, e i `doc_key` sono MD5 su input prevedibile.​
    
- Callback OnlyOffice non valida il JWT del payload, accettando update non autenticati.
    
- Cleanup documenti usa `datetime.now()` rispetto a `last_modified` (UTC) causando possibili cancellazioni anticipate o ritardate.
    
- Error handling del callback: in alcuni casi risponde `{"error": 0}` anche quando il payload è invalido o mancano campi essenziali.
    

Tracce di soluzione:

- Richiedere sempre `get_current_user` o almeno un token di servizio per `/files/{doc_key}`; opzionalmente verificare che l’utente abbia accesso a tender/proposal associati al documento.
    
- Verificare il token JWT nel callback con lo stesso secret usato per generarlo; rifiutare richieste con token mancante/invalid.
    
- Uniformare tutto a `datetime.now(timezone.utc)` e confronti tra aware datetime; spiegitarlo anche nei commenti e nella documentazione tecnica.​
    
- Restituire `error != 0` quando il payload è malformato, in modo che il Document Server possa reagire correttamente.
    

---

## 6. Sicurezza generale backend: bug_analysis esistenti

Dal tuo `bug_analysis.md` risultano già diversi problemi che vale la pena tracciare chiaramente:​

- Mancato commit esplicito in `delete_tender` → cancellazione “silenziosa” se qualcosa fallisce dopo `db.delete` ma prima del commit implicito; nessun evento KPI né cleanup storage MinIO.​
    
- Uso di `|safe` in template PDF senza sanitizzazione del contenuto sezione → rischio XSS lato generazione PDF.​
    
- Proxy anonymizer che forwarda a `X-Target-Url` senza whitelist/validazione → SSRF verso servizi interni o metadata cloud.​
    
- Uso di MD5 per doc_key e Docker socket montato nel backend → superfici di attacco per data leak ed escalation privilegi.​
    

Tracce di soluzione:

- Rendere sistematico l’uso di `db.commit()` e l’emissione di eventi (inclusi cleanup e KPI) sulle operazioni distruttive (delete tender, delete proposal, ecc.).
    
- Sanitizzare HTML di input o rimuovere `|safe` dove non strettamente indispensabile, usando librerie di sanitizzazione lato server.​
    
- Limitare anonymizer a domini/host configurati, oppure rimuoverlo da percorsi di produzione.
    
- Eliminare il mount del Docker socket o isolarlo in un servizio amministrativo non esposto.
    

---

## 7. API / DTO: coerenza dei contratti e validazioni

Problemi:​

- Modelli Pydantic per email (registrazione/login) usano `str` senza `EmailStr`, nessuna validazione del formato email.
    
- `update_proposal` accede a `proposal.status` prima di verificare che `proposal` non sia `None`; l’eccezione generata è un generico `AttributeError` invece di una HTTPException controllata.
    
- `update_section` ha un ramo `if key == "content"` ma esegue lo stesso identico `setattr` di `else`; probabile mancanza di conversione/normalizzazione contenuto.
    

Tracce di soluzione:

- Allineare la definizione di DTO a tipi Pydantic più specifici (EmailStr, constr, ecc.) per avere validazione server-side consistente.​
    
- In tutti i path “get X then muta X”, spostare il null-check subito dopo la query e prima di qualsiasi accesso ai campi, con test dedicati.
    
- Decidere una rappresentazione canonica del contenuto sezione (plain text vs JSON tiptap/OnlyOffice) e centralizzare la conversione in helper riusabili.
    

---

## 8. Modello dati: mutable default e timezone

Problemi:​

- Colonne `ARRAY` e `JSONB` con `default=[]` e `default={}` usano oggetti Python mutabili condivisi tra istanze, con rischio di side effects invisibili.
    
- Uso estensivo di `datetime.utcnow()` su campi `DateTime(timezone=True)` genera mismatch naive/aware e può creare warning o errori al confronto.
    

Tracce di soluzione:

- Sostituire i default mutabili con callables (`default=list`, `default=dict`) o usare `server_default` per casi semplici.​
    
- Uniformare tutti i timestamp di default/aggiornamento a `datetime.now(timezone.utc)` o, in alternativa, usare `func.now()` lato database per ridurre la divergenza.
    

---

Se per il prossimo passo vuoi, posso prendere una sola area (ad esempio solo `operational_workflow.py`) e costruire:

- una tabella completa delle transizioni `SectionStatus` e relativi effetti,
    
- seguita da uno “scheletro” di refactor a state machine (solo in pseudo‑codice), sempre senza ancora passare a patch concrete.


GEMINI 3.1 PRO:

Alziamo il livello dell'analisi. Lasciamo da parte per un momento i bug di sintassi (come le f-string o le validazioni mancanti) e guardiamo il sistema con le lenti dell'**architettura distribuita**, della **concorrenza** e della **consistenza di stato**, che sono le aree dove si nascondono i bug più letali in produzione.

Ecco un'analisi profonda dei colli di bottiglia architetturali e dei flaw logici nella codebase, con le relative tracce di mitigazione.

---

## 1. Dual-Write Problem e Perdita di Eventi KPI

**Il Problema Architetturale:**  
Nel backend, funzioni come `sync_section_operational_workflow` eseguono mutazioni sul database (Entity `ContributionUnit`, `ReviewCycle`, ecc.) e, contestualmente, accumulano in memoria una lista di tuple (es. `[("contribution_review_started", payload)]`).  
Se l'architettura corrente prevede di fare il `db.commit()` a fine richiesta HTTP e poi pubblicare questi eventi (su Redis/Kafka o via HTTP al KPI Reason Engine), siamo di fronte a un classico **Dual-Write Problem**:

- Se il commit DB fallisce, l'API va in 500. Gli eventi in memoria non partono. (OK)
    
- Se il commit DB ha successo, ma il pod backend crasha un millisecondo prima di fare il dispatch degli eventi, oppure la rete verso il Reason Engine va in timeout, **il database è aggiornato ma il Reason Engine perde per sempre l'evento**. I KPI si disallineano irreversibilmente dallo stato transazionale.
    

**Traccia di Soluzione (Pattern):**

- Implementare il **Transactional Outbox Pattern**: scrivere gli eventi in una tabella `outbox_events` all'interno della _stessa_ transazione SQL in cui si aggiornano le sezioni.
    
- Un worker asincrono (Celery o un loop interno) legge da `outbox_events`, pubblica al Reason Engine, e solo in caso di ACK positivo marca l'evento come `published`.
    

## 2. Assenza di Concurrency Control (Optimistic Locking)

**Il Problema Logico:**  
Il sistema permette l'editing collaborativo di `ProposalSection` e l'assegnazione tramite l'`operational_workflow`. Nel file `proposals.py` (API `update_section` e simili), il pattern è:

1. `SELECT` della section.
    
2. Modifica in memoria dei campi (es. status, content, assigned_to).
    
3. `UPDATE` implicito via flush/commit.  
    Non c'è alcun meccanismo di Lock (né ottimistico con `@version`, né pessimistico con `SELECT FOR UPDATE`).  
    Se il Manager A approva la sezione mentre il Manager B la riassegna o ne cambia lo stato un istante dopo (ma partendo dai dati non aggiornati), **l'ultimo che scrive vince**. L'evento di `complete_review` potrebbe partire per un utente che non è più l'assegnatario, sfociando in uno stato "ibrido" irrisolvibile.
    

**Traccia di Soluzione (Pattern):**

- Aggiungere una colonna `version (Integer)` nei modelli core (`ProposalSection`, `ContributionUnit`, `TenderRequirement`).
    
- Adottare **Optimistic Concurrency Control**: le API di update accettano la `version` in input. Se la versione sul DB nel frattempo è cambiata, il backend rifiuta con HTTP 409 (Conflict) obbligando il client a ricaricare i dati e ripetere l'azione.
    

## 3. Incoerenza tra Compliance Status e Mapping (Orphaned Requirements)

**Il Problema Logico:**  
Da `test_tender_requirement_response.py` e dai modelli si deduce che un `TenderRequirement` ha un legame verso `ProposalSection` via `proposal_section_id`.  
Cosa succede se una sezione viene cancellata o resettata?  
Nel modello, `proposal_section_id = Column(..., ondelete="SET NULL")`. Se elimino la sezione `Compliance Matrix`, il foreign key sul requisito diventa `NULL`.  
**Il bug latente:** Il campo `compliance_status` (es. `FULLY_ADDRESSED`) rimane inalterato! Avrai KPI che mostrano requisiti pienamente soddisfatti, ma che non sono mappati su nessuna sezione esistente del documento.

**Traccia di Soluzione:**

- Spostare la valutazione della "Compliance" in modo che sia computata _dinamicamente_ a partire dallo stato delle sezioni mappate, oppure:
    
- Aggiungere un Event Listener su SQLAlchemy (`after_delete` o `before_update` sulle sezioni) che forza il `compliance_status = NOT_ADDRESSED` per tutti i requisiti il cui `proposal_section_id` viene reciso.
    

## 4. RAG Pipeline: Timeout e Sezioni "Zombie" (Stuck States)

**Il Problema Architetturale:**  
Quando viene avviato un `generate_proposal_section_task` (file `tasks.py`), lo status della sezione passa verosimilmente a `IN_PROGRESS` o simili mentre Celery chiama l'LLM.  
Celery è configurato con `task_time_limit=3600` e `task_soft_time_limit=3000`.  
Se l'istanza di LLM (specialmente locale, es. LM Studio/Ollama visti nei tuoi log storici) va in crash o genera un OOM senza chiudere la connessione TCP, il task resta appeso fino al soft timeout (50 minuti). Peggio ancora, se il worker Celery muore bruscamente (es. pod eviction su Kubernetes o un kill -9), il task muore senza ripulire lo stato sul DB.  
Il risultato è una "Sezione Zombie": bloccata in generazione, senza che l'utente possa sbloccarla o riavviarla perché il sistema la crede ancora attivamente in esecuzione.

**Traccia di Soluzione:**

- Introdurre un pattern **Heartbeat / TTL** o una "Dead Letter Queue" procedurale:
    
    - La sezione salva un `generation_started_at`.
        
    - Un cron job (`celery beat`) cerca ciclicamente le sezioni in generazione da più di 10 minuti per cui non c'è più un task Celery attivo (usando le API di ispezione o verificando il fallimento) e le resetta a `FAILED` o `TODO`.
        

## 5. Security & Authorization: JWT Revocation Flow Assente

**Il Problema Logico:**  
Se un utente viene rimosso da un Tender (`deactivate_chat_member_for_tender` nel modulo chat e simili rimozioni lato RBAC), o se un Admin banna un utente in tempo reale, i token JWT che l'utente ha già nel suo browser **restano validi fino alla naturale scadenza**.  
Il backend, usando token stateless, estrarrà l'identità dell'utente ad ogni chiamata API. Se i check di accesso (`check_tender_access`) si basano su cache o sui claim del token senza ri-verificare sul database, l'utente continuerà a poter scaricare PDF dal sistema (in particolare quelli tramite OnlyOffice e `/files/` non protetti) per ore.

**Traccia di Soluzione:**

- Essendo impossibile invalidare un JWT stateless, è necessario introdurre un **Token Blacklist (DenyList)** su Redis. Quando i permessi di un utente cambiano criticamente, si inserisce il suo `user_id` o `jti` in Redis. I middleware di autenticazione fanno un check in-memory veloce su Redis (molto più rapido di una query Postgres) per respingere i token revocati.
    

## 6. OnlyOffice Document Synchronization Race

**Il Problema Logico:**  
Dal codice di `onlyoffice.py` emergono salvataggi asincroni attivati dal callback (quando l'utente chiude l'editor e il documento assume stato 2 - "Saved").  
Se l'utente chiude l'editor (innescando il trigger di OnlyOffice) ma **immediatamente** preme il pulsante "Genera PDF" o "Valuta Compliance" dall'interfaccia React di Lifecycle Control:

- Il Document Server di OnlyOffice può impiegare dai 2 ai 10 secondi per inviare il file al callback.
    
- L'utente genera l'output lavorando sui dati del database che **non contengono ancora l'ultima versione del testo**.  
    L'utente invierà una proposta mancante dell'ultimo paragrafo.
    

**Traccia di Soluzione:**

- Il backend, quando l'utente clicca "Genera" o avvia l'analisi, deve interrogare lo stato di _OnlyOffice Document Server_ (Force Save API) per accertarsi che non vi siano sessioni di editing "dirty" (pendenti) per quel `doc_key`.
    
- In alternativa, l'UI in React deve attendere un evento Server-Sent-Events (SSE) / WebSocket che notifichi `DOCUMENT_SAVED` dal backend prima di abilitare le azioni di downstream sulla sezione.
    

---

Se l'obiettivo è costruire un sistema Enterprise robusto (come immagino tu sia abituato a gestire con Spring Boot), questi sono i "buchi neri" in cui i dati perdono consistenza in produzione. Vuoi che ci concentriamo sulla risoluzione di uno di questi macro-temi (es. il refactoring verso un **Transactional Outbox** per i KPI) per blindare il passaggio dei dati al Reason Engine?

Preparato usando Gemini 3.1 Pro Thinking

voglio che me li elenchi tutti mi tracci una scenario di casistiche plausivili e traccie di soluzioni non risoluzioni completer

1 passaggio completato

Ecco la mappatura completa di tutte le vulnerabilità architetturali, logiche e di processo individuate nella codebase, strutturata in **Problema**, **Scenario Plausibile (Casistica)** e **Traccia di Soluzione** (design pattern o logica, senza implementazione).

---

## AREA 1: Architettura, Transazioni e Consistenza Dati

## 1. Il problema del "Dual-Write" (DB transazionale vs Eventi KPI)

- **Problema**: L'emissione degli eventi verso il _Reason Engine_ è disaccoppiata dal commit sul database Postgres.
    
- **Scenario Plausibile**: Un manager approva una sezione (HTTP request). Il backend scrive su Postgres, ma un istante prima di inviare l'evento HTTP/Kafka al Reason Engine, il container va in OOM (Out Of Memory) o la rete subisce un micro-distacco. Il DB registra l'approvazione, ma il Reason Engine perde per sempre l'evento. I KPI (es. _lead time to approval_) si corrompono irreversibilmente.
    
- **Traccia di Soluzione**: Adottare il **Transactional Outbox Pattern**. Scrivere il payload dell'evento in una tabella `outbox_events` all'interno della stessa transazione SQL dell'aggiornamento della sezione. Un worker asincrono leggerà poi l'outbox garantendo la consegna _at-least-once_.
    

## 2. Assenza di Concurrency Control (Race Conditions sulle Sezioni)

- **Problema**: L'aggiornamento delle `ProposalSection` avviene con un pattern di read-modify-write senza lock (né ottimistico né pessimistico).
    
- **Scenario Plausibile**: L'utente A (Tender Manager) apre la maschera per assegnare la sezione a Mario. Contemporaneamente l'utente B (Revisore) decide di marcare la sezione come "Approved". Entrambi partono dalla stessa versione dei dati. L'ultimo che preme "Salva" sovrascrive silenziosamente il lavoro dell'altro, portando il sistema in uno stato ibrido (es. approvata ma riassegnata come se fosse da fare).
    
- **Traccia di Soluzione**: Introdurre **Optimistic Locking**. Aggiungere una colonna `version` (interger) sul DB. Ogni operazione di update deve fallire (HTTP 409 Conflict) se la `version` fornita dal client non combacia con quella su DB, forzando un refresh dell'interfaccia.
    

## 3. Dati Orfani tra Requisiti (Compliance) e Sezioni

- **Problema**: `TenderRequirement` ha una foreign key su `ProposalSection` impostata a `ON DELETE SET NULL`, ma lo stato di compliance (es. `FULLY_ADDRESSED`) è salvato come stringa statica sul requisito.
    
- **Scenario Plausibile**: Un requisito tecnico viene marcato come `FULLY_ADDRESSED` mappandolo alla sezione "Matrice di Sicurezza". Un utente successivamente elimina l'intera sezione "Matrice di Sicurezza". Il legame scompare (diventa NULL), ma il requisito continua a figurare magicamente come "soddisfatto" nei report della gara.
    
- **Traccia di Soluzione**: Adottare eventi di dominio (SQLAlchemy listeners o logica applicativa) in fase di cancellazione sezione per scatenare in cascata il downgrade della compliance a `NOT_ADDRESSED`, oppure calcolare la compliance dinamicamente a runtime a partire dalle sezioni collegate.
    

## 4. Fallimento Silenzioso nelle Operazioni Distruttive

- **Problema**: In funzioni come `delete_tender`, manca un `db.commit()` esplicito ed eventuale rollback coordinato con i sistemi esterni (es. file su MinIO).
    
- **Scenario Plausibile**: Viene invocata l'eliminazione di una gara. I file associati vengono rimossi dallo storage object. Successivamente, prima che avvenga l'auto-commit di fine richiesta, un'eccezione interrompe il flusso. Risultato: il DB mantiene la gara, ma i suoi documenti sono spariti.
    
- **Traccia di Soluzione**: Implementare il pattern **Unit of Work** o un blocco `try/except` esplicito con rollback. Se si coordinano sistemi non transazionali (MinIO e DB), utilizzare meccanismi di soft-delete sul DB e cron job successivi per la rimozione asincrona dei file (Eventual Consistency).
    

---

## AREA 2: Integrazione OnlyOffice & Asincronicità

## 5. Race Condition di Salvataggio Documenti

- **Problema**: Il salvataggio del testo da OnlyOffice al DB avviene tramite un webhook/callback asincrono invocato dal Document Server circa 2-10 secondi dopo la chiusura del documento.
    
- **Scenario Plausibile**: Il Bid Manager finisce di scrivere l'ultimo paragrafo cruciale, chiude l'editor e _immediatamente_ clicca "Genera PDF Finale". Il backend legge il DB e crea il PDF mancando l'ultimo paragrafo, poiché il callback di OnlyOffice non è ancora arrivato a destinazione.
    
- **Traccia di Soluzione**: Introdurre un trigger di "Force Save" (API esposta da OnlyOffice) prima di qualsiasi operazione di esportazione/RAG, oppure notificare al client via WebSocket/SSE l'avvenuto update del DB, inibendo il pulsante "Genera PDF" finché il salvataggio non è completato.
    

## 6. Task Zombie e Timeout RAG

- **Problema**: I task Celery (es. generazione tramite LLM locale/Ollama) hanno limiti di tempo hard-coded lunghi (es. 50 minuti), e non ci sono meccanismi di recovery per task abortiti.
    
- **Scenario Plausibile**: Durante la generazione AI di una sezione complessa, il container dell'LLM crasha (OOM). Il task Celery si blocca, o il pod Celery stesso viene riavviato dal cluster. L'interfaccia utente rimarrà bloccata perennemente su "Generazione in corso", senza possibilità di sbloccare o ritentare l'azione.
    
- **Traccia di Soluzione**: Modello a stati espliciti con **Heartbeat** o timeout breve. Implementare un job di "reconciliation" (Sweep) che cerca transizioni bloccate da troppo tempo e le riporta a uno stato `FAILED` o `TODO`.
    

---

## AREA 3: Operational Workflow e Logica degli Stati

## 7. Generazione Automatica di Eventi Sintetici (Review Fantasma)

- **Problema**: La logica di transizione forza il passaggio attraverso la fase di "Review" anche se si salta direttamente ad "Approvato".
    
- **Scenario Plausibile**: Una sezione passa da `IN_PROGRESS` ad `APPROVED` con un singolo click del manager. Il codice genera istantaneamente una `review_started` e subito dopo una `review_completed`. I KPI del Reason Engine registreranno un tempo di revisione di 0.001 secondi, inquinando drasticamente le medie (SLT, LTA) della dashboard dirigenziale.
    
- **Traccia di Soluzione**: Separare i rami di business logic. Le approvazioni dirette devono generare un evento differenziato (es. `direct_approval_registered`), permettendo al Reason Engine di escluderle dalle metriche di durata "Review".
    

## 8. Fragilità della Derivazione di Stato (`derive_contribution_status`)

- **Problema**: Lo stato della "Contribution" (il contenitore concettuale del lavoro) è calcolato incrociando lo stato della sezione, la presenza di assegnatari e i rework aperti. Manca una gestione esplicita degli stati impossibili.
    
- **Scenario Plausibile**: Una sezione in `IN_PROGRESS` assegnata a "Giulia". Giulia viene rimossa dal team e l'assegnatario diventa `None`. Lo status della sezione resta `IN_PROGRESS`, ma la formula lo ricalcola silenziosamente a `OPEN`. Il task sparisce dai radar "in lavorazione" e non è tracciato come bloccato.
    
- **Traccia di Soluzione**: Costruire una **State Machine (FSM)** stretta. Non derivare ciecamente lo stato ad ogni giro, ma definire transizioni permesse (es. non si può togliere l'assegnatario se lo stato è `IN_PROGRESS`, si deve prima mettere in `TODO` o `BLOCKED`).
    

---

## AREA 4: Sicurezza, Permessi e Network (Vulnerabilità architetturali)

## 9. Impossibilità di Revocare i JWT Esistenti

- **Problema**: L'autenticazione tramite JWT è puramente stateless.
    
- **Scenario Plausibile**: Un consulente esterno lavora a un bando riservato. Alle 14:00 viene rimosso dai permessi di quel Tender. Tuttavia, il suo token JWT scade alle 18:00. Fino a quell'ora, può usare script o Postman per chiamare liberamente l'API `/files/` e scaricare documenti a cui non ha più diritto, bypassando i controlli dell'interfaccia.
    
- **Traccia di Soluzione**: Introdurre un meccanismo ibrido con **Redis DenyList**. Ad ogni cambio critico di permessi (o logout forzato), il JTI (ID univoco del token) o l'ID utente finisce in Redis. Il middleware API farà un check ultra-veloce contro Redis per invalidare la sessione in tempo reale.
    

## 10. SSRF (Server-Side Request Forgery) nel Gateway Anonymizer

- **Problema**: Il microservizio Anonymizer (visto nel file proxy) usa un header `x-target-url` fornito dal client per effettuare le chiamate HTTP interne senza validarlo.
    
- **Scenario Plausibile**: Un attaccante intercetta il traffico e invia una richiesta all'anonymizer chiedendo di reindirizzarla verso `http://169.254.169.254/latest/meta-data/` (se su AWS) o verso `http://localhost:5432`. Il proxy ubbidirà, recuperando variabili d'ambiente, credenziali cloud, o attaccando servizi interni non esposti al web.
    
- **Traccia di Soluzione**: Mantenere una rigida **AllowList (Whitelist)** di domini e porte verso cui il proxy è autorizzato a inoltrare (es. solo endpoint LLM noti o URL approvati a DB).
    

## 11. Endpoint Documenti Non Protetti ed Esiltrabili (ID Prevedibili)

- **Problema**: La risorsa che serve i documenti ad OnlyOffice e al frontend (`/files/{doc_key}`) non valida il JWT dell'utente, e genera le key con MD5 prevedibili (es. timestamp + ID).
    
- **Scenario Plausibile**: Conoscendo l'ID di un proposal, un attaccante scrive uno script Python che calcola gli MD5 per gli ultimi 10.000 timestamp al secondo, interrogando in massa l'endpoint aperto. Riesce così a scaricare file di gare sensibili senza alcuna autenticazione.
    
- **Traccia di Soluzione**: Rendere l'endpoint autenticato con JWT (passandolo tramite parametri o header configurati dal Document Server). Modificare la generazione della doc_key usando algoritmi sicuri (es. HMAC-SHA256 con un secret lato server, o UUID v4 associati al DB).
