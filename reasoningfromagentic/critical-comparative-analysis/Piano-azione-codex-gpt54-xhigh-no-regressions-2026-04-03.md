# Piano di Azione Microstrutturato per Agente Codex GPT-5.4 (Reasoning xhigh)

Documento operativo pensato per un agente Codex agganciato a `gpt-5.4` con reasoning effort `xhigh`.

Vincolo assoluto: **nessuna modifica al codebase prima di avere una prova riproducibile del difetto e nessuna patch senza un test che certifichi la scomparsa del problema e la non introduzione di regressioni**.

## 1. Scopo

Questo piano serve a guidare un agente Codex in una campagna di diagnosi e remediation del progetto TenderWriter con approccio:

- `docs-first but source-of-truth in code`;
- `reproduce first, fix second, certify third`;
- `zero-regression discipline`;
- `un defect at a time unless shared root cause is provable`.

## 2. Vincoli Operativi Non Negoziabili

1. Nessuna patch senza una delle due condizioni:
- test automatico che fallisce prima della patch;
- oppure procedura manuale ripetibile documentata, da trasformare subito dopo in test automatico.

2. Nessuna chiusura del difetto senza tutte e tre le prove:
- riproduzione pre-fix;
- verifica post-fix;
- non-regressione sul perimetro correlato.

3. Nessun refactor opportunistico mentre si corregge un bug.

4. Nessun upgrade di dipendenze salvo se il difetto e' chiaramente riconducibile a incompatibilita' di versione.

5. Ogni intervento deve lasciare una traccia oggettiva:
- file di test;
- output test;
- nota di root cause;
- elenco impatti laterali verificati.

6. Se i Markdown e il codice divergono, il codice e i test sono la source of truth; i Markdown diventano solo indizi da verificare.

## 3. Configurazione dell'Agente

### Profilo consigliato

- `model`: `gpt-5.4`
- `reasoning_effort`: `xhigh`
- `temperature`: bassa o default conservativo
- `stile operativo`: analitico, lento sulle decisioni, rapido solo sull'esecuzione di task gia' verificati

### Comportamento richiesto

- leggere prima i documenti e poi i sorgenti correlati;
- costruire una matrice di evidenze prima di proporre fix;
- privilegiare test mirati e piccoli PR interni rispetto a mega-patch;
- interrompersi e riallinearsi se emergono incongruenze forti tra docs, test e codice.

## 4. Esito della Scansione Markdown Gia' Eseguita

Prima di definire il piano e' stata effettuata una scansione del repository.

### Inventario

- File `.md` totali trovati nel workspace: `505`
- File `.md` di progetto, esclusi `node_modules`, `venv`, build artefacts e cache: `112`
- Aree piu' dense di documentazione:
- `resoningfromagentic/codex`
- `resoningfromagentic/antigravity`
- `resoningfromagentic/kiro`
- `kpi-reason-engine/docs`
- root del repository

### Segnali emersi dai Markdown

- I bug documentati coprono almeno `BUG-01` fino a `BUG-18`.
- Esistono gia' documenti di bug analysis, retrospettive, checklist, closure e fix log.
- Alcuni bug risultano gia' coperti da test o gia' corretti nel codice attuale.
- Alcune osservazioni nei Markdown sono stale o parzialmente superate.

### Evidenze rilevanti per il piano

1. Esistono gia' test di bug/regressione in:
- `anonymizer/test_ssrf_fix.py`
- `backend/tests/test_bug_fixes.py`
- `backend/tests/test_verified_bugs.py`
- `backend/tests/test_verified_bugs_round2.py`
- `backend/tests/test_rag_anonymizer_routing.py`

2. Alcuni claim documentali risultano da verificare con massima prudenza:
- `BUG-01` e' citato in molti Markdown, ma nel codice attuale `delete_tender` contiene `await db.commit()` e c'e' anche un test dedicato.
- La questione `GraphRetriever` compare in piu' documenti, ma il codice attuale mostra sia chiamate corrette sia chiamate potenzialmente rischiose a `session.run(...)`; quindi non si deve assumere ne' che il bug sia risolto ne' che sia ancora lo stesso.
- La vulnerabilita' SSRF e' discussa in piu' file, ma esistono sia test dedicati sia logica di validazione gia' presente.
- Le route della `content_library` risultano candidate forti a mancanza di auth nel codice attuale e vanno trattate come sospette fino a prova contraria.
- La questione `external_anonymized` compare nei benchmark e nei test esistenti: potrebbe essere comportamento intenzionale, non necessariamente bug.

### Implicazione strategica

Il piano non deve partire da "fixare quanto dicono i documenti", ma da:

1. classificare i claim dei Markdown;
2. verificare i claim nel codice;
3. mappare i test gia' presenti;
4. solo dopo decidere cosa e' bug attuale, bug gia' chiuso, regression, issue operativo o debito tecnico.

## 5. Classificazione dei Problemi Prima di Ogni Intervento

Ogni item sospetto deve essere classificato in una di queste categorie:

### Classe A - Bug confermato e riproducibile

- Il codice mostra il problema.
- Esiste una riproduzione o un test fallente.
- Va corretto con massima priorita'.

### Classe B - Bug documentato ma stato attuale incerto

- I Markdown lo citano.
- Il codice non lo conferma in modo netto oppure mostra fix parziale.
- Serve test diagnostico o replay dello scenario prima di decidere.

### Classe C - Bug storico gia' corretto

- I Markdown lo citano.
- Il codice attuale lo mostra gia' fixato.
- Esiste magari anche un test che protegge la correzione.
- Non va "rifixato"; va solo registrato come chiuso e va verificato che il test continui a passare.

### Classe D - Problema operativo o di configurazione, non bug di codice

- Esempio: corpus vuoto, env sbagliato, servizio non popolato, benchmark non rappresentativo.
- Richiede test di sistema e non necessariamente patch al sorgente.

### Classe E - Debito tecnico non difettivo

- Esempio: assenza di Alembic, script operativi nel package, repo hygiene.
- Non si tratta con logica "fix bug", ma con RFC, migrazione controllata e suite di sicurezza.

## 6. Obiettivo Primario del Piano

Evitare due errori classici:

1. correggere bug gia' corretti e reintrodurre regressioni;
2. trattare come bug di codice problemi che in realta' sono di dati, bootstrap, routing o configurazione.

## 7. Sequenza Operativa Obbligatoria

## Fase 0 - Preparazione del Tavolo di Lavoro

### Output attesi

- matrice difetti iniziale;
- elenco test esistenti;
- lista claim Markdown da verificare;
- perimetro dei servizi coinvolti.

### Azioni

1. Creare una tabella `Defect Evidence Ledger`.
2. Per ogni bug o anomalia sospetta, registrare:
- `ID`
- `fonte markdown`
- `file sorgente coinvolti`
- `test esistenti`
- `stato attuale`
- `classe A/B/C/D/E`
- `riproduzione disponibile?`
- `owner`

3. Identificare subito i file Markdown piu' autorevoli:
- report architetturali recenti;
- bug analysis;
- bug resolution;
- validazioni critiche;
- release checklist;
- retrospective;
- runbook.

4. Etichettare come `stale candidate` tutti i documenti che contraddicono test o codice attuale.

### Gate di uscita

- nessun lavoro sul codice finche' il ledger non esiste;
- nessuna priorita' assegnata senza classificazione A/B/C/D/E.

## Fase 1 - Mappatura Test Esistenti

### Obiettivo

Capire cosa e' gia' protetto e dove ci sono buchi reali.

### Azioni

1. Inventariare i test backend, frontend, anonymizer, gateway, ops-agent, KPI engine.
2. Mappare i test di bug gia' presenti, almeno:
- `backend/tests/test_bug_fixes.py`
- `backend/tests/test_verified_bugs.py`
- `backend/tests/test_verified_bugs_round2.py`
- `anonymizer/test_ssrf_fix.py`
- `backend/tests/test_rag_anonymizer_routing.py`
- `frontend/src/pages/OnlyOfficeEditor.test.ts`

3. Per ogni test gia' presente, annotare:
- cosa verifica;
- se e' unit, integration, smoke o regression;
- se copre davvero il comportamento desiderato o solo la forma del codice.

4. Separare i test in quattro anelli:
- `L0`: static review / grep / import safety
- `L1`: unit test puri
- `L2`: integration test su modulo o API
- `L3`: smoke test di sistema / container

### Gate di uscita

- ogni difetto prioritario deve avere indicato se ha gia' copertura in L1/L2/L3;
- i difetti senza test devono avere un piano esplicito di test da creare prima della patch.

## Fase 2 - Verifica Source-of-Truth per Claim Documentali

### Obiettivo

Impedire che l'agente lavori su assunzioni vecchie.

### Azioni per ogni claim Markdown

1. Aprire i file sorgente citati.
2. Cercare il path reale e le linee attuali.
3. Verificare se il comportamento indicato e':
- ancora presente;
- corretto;
- corretto parzialmente;
- spostato altrove;
- sostituito da un nuovo bug.

4. Verificare se esiste gia' un test dedicato e se quel test e' ancora coerente.
5. Registrare il risultato nel ledger:
- `confirmed`
- `partially confirmed`
- `superseded`
- `not reproducible`
- `operational only`

### Esempi da trattare subito

- `BUG-01` delete con commit
- `BUG-04` SSRF anonymizer
- `BUG-05` OnlyOffice access protection
- GraphRetriever / session.run / parametri Cypher
- BM25 load all'avvio
- `content_library` auth
- routing LLM `external_anonymized`
- XSS o HTML injection nel rendering PDF

### Gate di uscita

- ogni item P0/P1 deve avere stato attuale verificato sul codice;
- i bug storici gia' chiusi vanno marcati `do not touch without failing regression`.

## Fase 3 - Costruzione delle Prove di Riproduzione

### Obiettivo

Creare la prova pre-fix, non opinioni.

### Regola

Per ogni difetto attuale, l'agente deve costruire una prova riproducibile con questo ordine preferenziale:

1. test automatico unit o integration;
2. test end-to-end ridotto;
3. script di riproduzione manuale ripetibile;
4. solo in casi estremi, evidenza log con procedura deterministica.

### Template obbligatorio per ogni riproduzione

- `Bug/Issue ID`
- `Versione del codice`
- `Servizi richiesti`
- `Dati richiesti`
- `Comando di esecuzione`
- `Risultato atteso`
- `Risultato ottenuto`
- `Perche' il comportamento e' errato`

### Pattern di test richiesto

- se il bug e' di API: test HTTP con assertion su status code, payload, side effects;
- se il bug e' di persistence: assertion su DB prima e dopo;
- se il bug e' di security: test che mostra l'accesso non autorizzato oppure il blocco mancato;
- se il bug e' di routing/LLM: test su trace/metadati, non solo sul testo risposta;
- se il bug e' di startup/runtime: smoke test che fallisce in modo diagnostico.

### Gate di uscita

- nessuna patch viene autorizzata senza una prova pre-fix archiviata nel ledger.

## Fase 4 - Prioritizzazione Finale Prima delle Patch

### Regola di priorita'

Ordinare gli item confermati cosi':

1. sicurezza sfruttabile;
2. corruzione dati / data integrity;
3. crash runtime e task always-failing;
4. auth / authorization gaps;
5. regressioni note gia' coperte da test storici;
6. problemi operativi ad alto impatto;
7. debito tecnico strutturale.

### Matrice di scoring

Per ogni item assegnare:

- `Impact`: 1-5
- `Exploitability`: 1-5
- `Reproducibility`: 1-5
- `Regression risk`: 1-5
- `Fix complexity`: 1-5

Formula consigliata:

`priority_score = impact + exploitability + reproducibility + regression_risk - fix_complexity`

### Gate di uscita

- nessun fix in parallelo su aree ad alta interferenza;
- un solo difetto alla volta per file critici o moduli condivisi.

## Fase 5 - Design della Patch

### Obiettivo

Ridurre il rischio della soluzione prima ancora di scrivere codice.

### Azioni

1. Scrivere una mini scheda di design per il difetto:
- root cause;
- comportamento desiderato;
- approccio minimo;
- alternative scartate;
- possibili regressioni indotte.

2. Identificare il `blast radius`:
- file modificati;
- moduli che importano quel codice;
- test da rieseguire per sicurezza.

3. Definire le `guardrail` della patch:
- niente rename non necessario;
- niente reformatting massivo;
- niente cleanup collateral;
- niente modifica a env/compose senza test corrispondenti.

### Gate di uscita

- la patch plan deve essere approvata internamente dall'agente come "minimal safe change".

## Fase 6 - Implementazione con Test-First o Test-Adjacent

### Modalita' ammesse

#### Modalita' A - Test first puro

- scrivere il test che fallisce;
- verificare il fallimento;
- applicare la patch;
- verificare il passaggio.

#### Modalita' B - Test-adjacent

Se il test automatico completo e' difficile da produrre prima, l'agente puo':

1. preparare harness o fixture;
2. creare riproduzione manuale;
3. applicare patch minima;
4. trasformare subito la riproduzione in test automatico.

### Regole di implementazione

- patch piccole;
- un commit logico per difetto;
- nessun fix accorpato se i root cause non coincidono;
- inserire commenti solo se evitano ambiguita' reali.

## Fase 7 - Certificazione Post-Fix

### Obiettivo

Dimostrare che il problema e' sparito e che non ne sono comparsi altri.

### Per ogni difetto, eseguire obbligatoriamente

1. stesso test/procedura della riproduzione pre-fix;
2. test di regressione dedicato;
3. anello di test adiacenti.

### Anelli di regressione consigliati

- Se tocchi `content_library`: test auth, CRUD, permessi, eventuale frontend correlato.
- Se tocchi `OnlyOffice`: test firma/token, editor page, callback, download.
- Se tocchi `anonymizer`: test SSRF, routing privacy, fallback, header handling.
- Se tocchi RAG:
- dense retriever tests
- sparse retriever tests
- graph retriever tests
- routing tests
- benchmark smoke minimo

- Se tocchi Celery/tasks:
- unit test del task
- integration sul path asincrono
- prova di cleanup/shutdown

- Se tocchi schema o DB:
- test su create/update/delete
- backward compatibility
- migrazione o bootstrap compatibile

### Gate di uscita

- nessun fix chiuso senza evidenza post-fix;
- nessuna evidenza post-fix valida se manca il ring di non-regressione.

## Fase 8 - Suite di Non-Regressione Trasversale

### Obiettivo

Compensare il fatto che TenderWriter e' un sistema multi-servizio dove piccoli fix possono rompere percorsi laterali.

### Anello minimo da rieseguire per ogni patch backend significativa

- `backend/tests/test_bug_fixes.py`
- `backend/tests/test_verified_bugs.py`
- `backend/tests/test_verified_bugs_round2.py`
- `backend/tests/test_main_route_registration.py`
- `backend/tests/test_rag_anonymizer_routing.py`
- test specifici del modulo toccato

### Anello aggiuntivo quando pertinente

- `anonymizer/test_ssrf_fix.py`
- `frontend/src/pages/OnlyOfficeEditor.test.ts`
- `frontend/src/pages/searchAnswerSanitizer.test.ts`
- `backend/tests/test_operational_workflow.py`
- `backend/tests/test_system_api.py`
- `kpi-reason-engine/tests/*` se il bug tocca KPI o integrazione

### Smoke di sistema consigliati

- avvio servizi critici;
- health/ready endpoints;
- una query RAG semplice;
- un flusso auth minimo;
- un flusso document/proposal minimo se toccato.

## Fase 9 - Chiusura del Difetto

Ogni item puo' essere dichiarato chiuso solo se il ledger contiene:

- root cause finale;
- file modificati;
- test pre-fix;
- test post-fix;
- ring di non-regressione passato;
- eventuali limiti residui;
- aggiornamento docs se una fonte Markdown e' stata smentita o superata.

## 8. Piano Microstrutturato per Workstream

## Workstream A - Doc Reconciliation

### A1

Creare tabella `markdown_claims.csv` o equivalente con:

- `doc_path`
- `claim_id`
- `claim_summary`
- `related_bug`
- `related_files`
- `status_after_source_check`

### A2

Marcare come `high-risk stale` tutti i claim che:

- contraddicono il codice attuale;
- contraddicono test esistenti;
- si basano su benchmark vecchi;
- descrivono bug gia' fixati.

### A3

Produrre una lista finale:

- `claim confermati`
- `claim superati`
- `claim operativi`
- `claim da riesaminare`

## Workstream B - Test Inventory e Gap Analysis

### B1

Per ogni modulo critico, compilare:

- `backend/app/api`
- `backend/app/rag`
- `backend/app/tasks.py`
- `anonymizer/app.py`
- `gateway/app.py`
- `frontend/src/pages`
- `kpi-reason-engine`

### B2

Per ogni modulo, indicare:

- test esistenti;
- test mancanti;
- severita' del gap.

### B3

Produrre matrice `defect -> existing test -> missing test`.

## Workstream C - Candidate Defects da Trattare con Precedenza

Questi non vanno dati per certi: vanno confermati con riproduzione.

### C1 - `content_library` authorization gap

- forte sospetto da sorgente;
- richiede test API non autenticata;
- richiede test autenticata e permessi.

### C2 - BM25 non ricaricato all'avvio

- forte sospetto da codice e benchmark;
- richiede test di bootstrap con corpus persistito;
- richiede test post-restart.

### C3 - GraphRetriever runtime stability

- documentazione incoerente con codice attuale;
- richiede test su tutte le chiamate `session.run(...)`;
- richiede test di ricerca con Neo4j disponibile e grafo popolato;
- richiede test di comportamento con grafo vuoto.

### C4 - OnlyOffice access model

- la documentazione storica parla di no-auth;
- il codice attuale usa firma/token;
- serve test esplicito per accesso senza token, token invalido, token scaduto, token valido.

### C5 - PDF rendering injection

- il rischio non va semplificato a "XSS classico";
- serve test su sanitizzazione e render output consentito/non consentito.

### C6 - LLM route selection

- i test indicano route `external_anonymized`;
- non assumere bug senza definire policy attesa;
- prima va chiarito il comportamento desiderato per ogni mode.

## Workstream D - Fix Execution Policy

### D1

Un fix per volta.

### D2

Ogni fix deve avere:

- branch logico;
- patch minima;
- test dedicato;
- rerun del ring minimo.

### D3

Se durante il fix emerge un secondo bug:

- registrarlo nel ledger;
- non correggerlo nello stesso changeset salvo shared root cause dimostrata.

## 9. Comandi e Flusso Esecutivo Consigliato

L'agente deve adattare i comandi al contesto, ma il flusso deve rimanere questo.

### Backend

1. Eseguire test mirati del difetto.
2. Eseguire il test di regressione storico se esiste.
3. Applicare patch.
4. Rieseguire test mirati.
5. Rieseguire ring backend minimo.

### Frontend

1. Eseguire test pagina/componente interessato.
2. Rieseguire test sanitizzazione/editor/router se la patch tocca flussi correlati.

### Multi-servizio

1. Rieseguire smoke test dei servizi toccati.
2. Verificare health/ready.
3. Verificare log di bootstrap e side effects.

## 10. Definition of Done per Singolo Difetto

Un difetto e' `Done` solo se:

- e' classificato A o D con evidenza finale;
- esiste prova pre-fix;
- esiste test o prova post-fix;
- il ring di non-regressione e' passato;
- la doc storica, se fuorviante, e' stata marcata o aggiornata;
- il ledger riporta stato finale e rischio residuo.

## 11. Anti-Pattern da Evitare

- correggere bug per memoria o intuizione senza riprodurli;
- fidarsi di un singolo Markdown come verita';
- fare cleanup o refactor nel mezzo di una patch di sicurezza;
- usare solo benchmark storici senza dati o fixture controllate;
- trattare issue di configurazione come bug di codice;
- chiudere un bug solo perche' "sembra giusto".

## 12. Deliverable Richiesti all'Agente

Prima di qualsiasi patch:

- `Evidence Ledger`
- `Markdown Claims Matrix`
- `Test Inventory Matrix`
- `Prioritized Defect Queue`

Dopo ogni patch:

- `Pre-fix evidence`
- `Patch rationale`
- `Post-fix evidence`
- `Regression ring result`

A fine ciclo:

- `Final defect closure report`
- `Known residual risks`
- `Docs to update`

## 13. Ordine Consigliato di Avvio del Lavoro

1. Costruire il ledger.
2. Mappare i test esistenti.
3. Verificare i claim piu' critici nei sorgenti.
4. Scegliere il primo difetto con massimo rapporto impatto/certezza.
5. Riprodurre.
6. Patch minima.
7. Certificare.
8. Passare al successivo.

## 14. Primo Sprint Operativo Consigliato per l'Agente

### Sprint Day 1

- completare ledger e matrice claim/test;
- verificare sorgenti per i candidati P0;
- eseguire i test storici esistenti;
- identificare quali candidati sono gia' coperti e quali no.

### Sprint Day 2

- costruire o rafforzare le prove di riproduzione per i primi 1-2 bug confermati;
- scegliere il primo fix minimo e applicarlo;
- far passare post-fix e ring minimo.

### Sprint Day 3

- chiudere il primo difetto con certificazione completa;
- aprire il secondo solo dopo stabilizzazione del primo;
- aggiornare il ledger e la lista delle fonti Markdown superate.

## 15. Nota Finale di Strategia

In TenderWriter il rischio maggiore non e' solo la presenza di bug: e' la compresenza di documentazione abbondante, fix storici, test gia' esistenti e moduli multi-servizio che rende facile correggere la cosa sbagliata o reintrodurre regressioni.

Per questo l'agente Codex GPT-5.4 xhigh deve comportarsi piu' come un `forensic maintainer` che come un semplice fixer:

- prima certifica lo stato reale;
- poi dimostra il difetto;
- poi corregge;
- infine prova che nulla di adiacente si sia rotto.

Questo e' il solo percorso compatibile con il vincolo attuale: **non possiamo introdurre regressioni**.
