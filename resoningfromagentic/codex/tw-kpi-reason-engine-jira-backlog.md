# TenderWriter KPI Reason Engine - Epic, User Stories, Technical Tasks

Questo documento traduce l'analisi precedente in un backlog pronto per Jira o Linear.

Convention consigliata:
- Prefix issue key: `KRE`
- Labels comuni: `kpi-reason-engine`, `workflow`, `observability`, `admin-ux`, `markov`
- Campi utili: `Priority`, `Owner`, `Depends on`, `Acceptance Criteria`, `Done When`

## Epic Overview

| Epic ID | Titolo | Priorita | Obiettivo | Gap di specifica coperto |
|---|---|---|---|---|
| `KRE-EPIC-01` | Decision & Outcome Lifecycle | `P0` | Rendere espliciti go/no-bid ed esiti terminali | `S1`, `S13` |
| `KRE-EPIC-02` | Review Normalization & Draft Readiness | `P0` | Rendere misurabili review outcome e readiness del draft integrato | `S5`, `S6`, `S7` |
| `KRE-EPIC-03` | Submission Reliability & Clarifications | `P0/P1` | Modellare correttamente submission, ack/fail e chiarimenti post-submit | `S9`, `S10` |
| `KRE-EPIC-04` | KPI Engine & Markov Adoption | `P0/P1` | Ingerire i nuovi eventi nel dataset KPI e nella catena di transizione | dataset Markov reale |
| `KRE-EPIC-05` | Operational Refinements & Alerts | `P2` | Raffinare rework, gate e segnali di coordinamento | churn e alerting |

## `KRE-EPIC-01` - Decision & Outcome Lifecycle

Obiettivo:
Portare nel prodotto la parte iniziale e terminale della tua specifica, oggi ancora compressa in proxy o stati generici.

### Stories

| Story ID | Titolo | Priorita | Depends on |
|---|---|---|---|
| `KRE-ST-101` | Record Go / No-Bid Decision | `P0` | none |
| `KRE-ST-102` | Record Structured Terminal Outcomes | `P0` | `KRE-ST-101` |

#### `KRE-ST-101` - Record Go / No-Bid Decision

User story:
Come admin voglio registrare una decisione `go` o `no_bid` con motivazione, cosi il tender entra in un flusso osservabile e coerente con la specifica.

Acceptance criteria:
- Esiste un'azione admin esplicita per registrare `go` o `no_bid`.
- Ogni decisione salva `decided_at`, `decided_by`, `reason_code` e `notes`.
- La decisione pubblica l'evento `go_decision_recorded` oppure `no_bid_decision_recorded`.
- Il timeline admin mostra la decisione con provenance chiara.
- Il KPI engine puo distinguere `no_bid` da un generico `cancelled`.

#### `KRE-ST-102` - Record Structured Terminal Outcomes

User story:
Come admin voglio registrare in modo distinto `lost`, `excluded` e `withdrawn`, cosi il motore analitico non mescola fallimento competitivo, esclusione formale e ritiro strategico.

Acceptance criteria:
- L'admin puo registrare un outcome strutturato con reason taxonomy.
- `excluded` e `withdrawn` sono distinguibili nel modello dati e negli eventi.
- L'evento pubblicato e coerente con l'outcome selezionato.
- Il KPI engine classifica correttamente `S13` nei casi non competitivi.
- La retrospettiva analytics puo filtrare gli outcome per tipo.

### Technical Tasks

| Task ID | Titolo | Priorita | Depends on | Output atteso |
|---|---|---|---|---|
| `KRE-TK-101` | Create `tender_decisions` migration | `P0` | none | nuova tabella con decision payload strutturato |
| `KRE-TK-102` | Add `POST /tenders/{id}/decision` | `P0` | `KRE-TK-101` | endpoint e service `tender_lifecycle` |
| `KRE-TK-103` | Publish `go_decision_recorded` / `no_bid_decision_recorded` | `P0` | `KRE-TK-102` | domain events versionati |
| `KRE-TK-104` | Extend outcome model for `excluded` / `withdrawn` | `P0` | none | enum o outcome model esteso |
| `KRE-TK-105` | Add `POST /tenders/{id}/outcome` structured route | `P0` | `KRE-TK-104` | route dedicato per esiti terminali |
| `KRE-TK-106` | Add admin decision and outcome controls | `P0` | `KRE-TK-102`, `KRE-TK-105` | UX admin per decisione e outcome |
| `KRE-TK-107` | Map lifecycle events into KPI snapshots | `P0` | `KRE-TK-103`, `KRE-TK-105` | ingestion e classification coerente |

## `KRE-EPIC-02` - Review Normalization & Draft Readiness

Obiettivo:
Rendere robusto il cuore del loop operativo con segnali meno impliciti e piu direttamente leggibili da admin e KPI engine.

### Stories

| Story ID | Titolo | Priorita | Depends on |
|---|---|---|---|
| `KRE-ST-201` | Close Reviews With Explicit Outcomes | `P0` | none |
| `KRE-ST-202` | Emit Draft Integrated Ready Automatically | `P0` | `KRE-ST-201` |

#### `KRE-ST-201` - Close Reviews With Explicit Outcomes

User story:
Come reviewer/admin voglio chiudere una review come `approved` o `changes_requested`, cosi il sistema distingue chiaramente un avanzamento da un ritorno in rework.

Acceptance criteria:
- La chiusura review accetta solo outcome normalizzati.
- Viene emesso `review_approved` o `review_changes_requested`.
- La timeline mostra outcome esplicito e non ambiguo.
- Il KPI engine puo derivare `S5 -> S7` e `S5 -> S6` senza inferenze fragili.

#### `KRE-ST-202` - Emit Draft Integrated Ready Automatically

User story:
Come admin voglio che il sistema segnali quando il draft integrato e realmente pronto per il gate, cosi `S7` non resta solo inferito.

Acceptance criteria:
- Esiste una predicate formalizzata di readiness del draft.
- Quando la predicate diventa vera viene emesso `draft_integrated_ready`.
- L'evento non viene duplicato inutilmente.
- L'admin vede un badge o stato di readiness nel workspace.

### Technical Tasks

| Task ID | Titolo | Priorita | Depends on | Output atteso |
|---|---|---|---|---|
| `KRE-TK-201` | Normalize review completion contract | `P0` | none | outcome review normalizzati a livello API |
| `KRE-TK-202` | Publish explicit review outcome events | `P0` | `KRE-TK-201` | `review_approved` e `review_changes_requested` |
| `KRE-TK-203` | Implement draft readiness predicate | `P0` | none | funzione condivisa backend/workflow |
| `KRE-TK-204` | Publish `draft_integrated_ready` from workflow | `P0` | `KRE-TK-203` | emissione evento su transition point |
| `KRE-TK-205` | Add workspace readiness affordances | `P1` | `KRE-TK-204` | badge, timeline, summary panel |
| `KRE-TK-206` | Update KPI transition extraction for `S7` | `P0` | `KRE-TK-202`, `KRE-TK-204` | dataset transizioni piu pulito |

## `KRE-EPIC-03` - Submission Reliability & Clarifications

Obiettivo:
Chiudere i due buchi piu evidenti rispetto alla specifica estesa: affidabilita della submission e ciclo di chiarimenti post-submission.

### Stories

| Story ID | Titolo | Priorita | Depends on |
|---|---|---|---|
| `KRE-ST-301` | Manage Clarification Requests Post-Submission | `P0` | none |
| `KRE-ST-302` | Track Submission Acknowledgement and Failure | `P1` | none |

#### `KRE-ST-301` - Manage Clarification Requests Post-Submission

User story:
Come admin voglio registrare richieste di chiarimento e risposte inviate dopo la submission, cosi il sistema modella davvero `S10`.

Acceptance criteria:
- L'admin puo aprire una clarification request con deadline e summary.
- L'admin puo inviare la risposta e chiudere il ciclo.
- Vengono emessi `clarification_requested` e `clarification_submitted`.
- Il timeline admin mostra l'intero ciclo post-submit.
- Il KPI engine puo distinguere `S9` da `S10`.

#### `KRE-ST-302` - Track Submission Acknowledgement and Failure

User story:
Come admin voglio distinguere una submission inviata da una submission confermata o fallita, cosi il prodotto non considera `S9` come un punto sempre affidabile.

Acceptance criteria:
- Il sistema registra `submission_acknowledged` quando arriva conferma di invio.
- Il sistema registra `submission_failed` quando il canale di invio fallisce.
- L'admin vede reference id, channel e stato attuale dell'invio.
- Il KPI engine evita falsi positivi di submission riuscita.

### Technical Tasks

| Task ID | Titolo | Priorita | Depends on | Output atteso |
|---|---|---|---|---|
| `KRE-TK-301` | Create `submission_clarifications` migration | `P0` | none | persistence per ciclo chiarimenti |
| `KRE-TK-302` | Add clarification APIs | `P0` | `KRE-TK-301` | create/submit clarification routes |
| `KRE-TK-303` | Build admin clarification panel | `P0` | `KRE-TK-302` | UX post-submission completa |
| `KRE-TK-304` | Create `submission_attempts` migration | `P1` | none | tracciamento ack/fail per submission |
| `KRE-TK-305` | Publish `submission_acknowledged` / `submission_failed` | `P1` | `KRE-TK-304` | eventi submission affidabili |
| `KRE-TK-306` | Expose submission reliability in admin workspace | `P1` | `KRE-TK-305` | badge e reference di submission |
| `KRE-TK-307` | Map `S10` and submission reliability into KPI engine | `P0/P1` | `KRE-TK-302`, `KRE-TK-305` | supporto reale per `S10` e `S9` |

## `KRE-EPIC-04` - KPI Engine & Markov Adoption

Obiettivo:
Fare in modo che i nuovi eventi non restino solo funzionalita backend/UI, ma diventino dataset utile per KPI, diagnostics e primo Markov credibile.

### Stories

| Story ID | Titolo | Priorita | Depends on |
|---|---|---|---|
| `KRE-ST-401` | Show New Events in Timeline and Snapshots | `P0` | `KRE-EPIC-01`, `KRE-EPIC-02`, `KRE-EPIC-03` |
| `KRE-ST-402` | Use New Events in Transition Extraction | `P0/P1` | `KRE-ST-401` |

#### `KRE-ST-401` - Show New Events in Timeline and Snapshots

User story:
Come admin/analyst voglio vedere i nuovi eventi nel timeline e negli snapshot KPI, cosi posso leggere il flusso in modo spiegabile e auditabile.

Acceptance criteria:
- Ogni nuovo event type compare nel timeline admin.
- Gli snapshot KPI salvano provenance e payload minimo necessario.
- I nuovi eventi sono distinguibili tra osservati, derivati e semantici.

#### `KRE-ST-402` - Use New Events in Transition Extraction

User story:
Come analyst voglio che il motore di transizione usi i nuovi eventi per costruire un dataset Markov piu aderente alla specifica, cosi le probabilita si basano su storia osservata e non solo su proxy.

Acceptance criteria:
- `S1`, `S7`, `S10`, `S13` diventano piu osservabili.
- Le funzioni di transition extraction riconoscono i nuovi event type.
- Le analytics distinguono esiti competitivi da stop strategici o esclusioni formali.
- Esistono test di regressione sul mapping evento -> stato.

### Technical Tasks

| Task ID | Titolo | Priorita | Depends on | Output atteso |
|---|---|---|---|---|
| `KRE-TK-401` | Extend event schema contract and versioning | `P0` | none | schema unico aggiornato |
| `KRE-TK-402` | Update transition diagnostics for new event types | `P0` | `KRE-TK-401` | mapping eventi/stati esteso |
| `KRE-TK-403` | Update analytics and snapshot persistence | `P0` | `KRE-TK-401` | snapshot coerenti con nuovi payload |
| `KRE-TK-404` | Add provenance fields to admin payloads | `P1` | `KRE-TK-403` | source type, confidence, formula version |
| `KRE-TK-405` | Build regression test suite for event-to-state mapping | `P0` | `KRE-TK-402`, `KRE-TK-403` | test sul core loop e stati nuovi |
| `KRE-TK-406` | Prepare Markov-ready transition dataset export | `P1` | `KRE-TK-405` | estrazione pulita per calibrazione |

## `KRE-EPIC-05` - Operational Refinements & Alerts

Obiettivo:
Aggiungere i raffinamenti P2 che migliorano leggibilita e churn del processo senza bloccare il primo rilascio utile.

### Stories

| Story ID | Titolo | Priorita | Depends on |
|---|---|---|---|
| `KRE-ST-501` | Reopen Rework and Compliance Gate | `P2` | `KRE-EPIC-02` |
| `KRE-ST-502` | Surface Coordination Risk and Missed Rework Deadlines | `P2` | `KRE-EPIC-02` |

#### `KRE-ST-501` - Reopen Rework and Compliance Gate

User story:
Come admin voglio riaprire un rework o un gate quando emerge una criticita tardiva, cosi il timeline riflette il comportamento reale del team.

Acceptance criteria:
- Esiste una action `reopen` su rework e gate.
- Vengono emessi `rework_reopened` e `compliance_gate_reopened`.
- Il timeline mostra correttamente la riapertura.

#### `KRE-ST-502` - Surface Coordination Risk and Missed Rework Deadlines

User story:
Come admin voglio essere avvisato quando il coordinamento degrada o un rework sfora la deadline, cosi posso intervenire prima che il flusso collassi.

Acceptance criteria:
- Il sistema puo emettere `coordination_risk_raised` e `rework_deadline_missed`.
- Gli alert sono visibili nel workspace admin.
- Gli eventi non generano rumore eccessivo o duplicazioni incontrollate.

### Technical Tasks

| Task ID | Titolo | Priorita | Depends on | Output atteso |
|---|---|---|---|---|
| `KRE-TK-501` | Add rework reopen route and event | `P2` | none | supporto reopen rework |
| `KRE-TK-502` | Add compliance gate reopen route and event | `P2` | none | supporto reopen gate |
| `KRE-TK-503` | Implement overdue rework checker | `P2` | none | publisher `rework_deadline_missed` |
| `KRE-TK-504` | Implement coordination risk rule | `P2` | none | publisher `coordination_risk_raised` |
| `KRE-TK-505` | Add admin alert surfacing for P2 events | `P2` | `KRE-TK-503`, `KRE-TK-504` | cards/alerts nel workspace |

## Suggested Delivery Order

Sequenza consigliata:
1. `KRE-EPIC-01`
2. `KRE-EPIC-02`
3. `KRE-EPIC-04` per ingestion e test sui nuovi eventi introdotti
4. `KRE-EPIC-03`
5. `KRE-EPIC-05`

Motivo:
- `KRE-EPIC-01` chiude i buchi piu strutturali della catena teorica.
- `KRE-EPIC-02` pulisce il core loop piu osservabile.
- `KRE-EPIC-04` evita che i nuovi eventi restino inutilizzati dal reason engine.
- `KRE-EPIC-03` apre il post-submit, che e prezioso ma piu costoso.
- `KRE-EPIC-05` raffina il sistema dopo che la spina dorsale e stabile.

## Definition Of Done Trasversale

Ogni issue e considerata chiusa solo se:
- il domain event viene emesso e persistito correttamente;
- timeline admin e workspace mostrano il nuovo stato in modo leggibile;
- il KPI engine sa ingerire o ignorare esplicitamente l'evento;
- esistono test API e test di regressione analytics;
- il comportamento e documentato nel contratto KPI/eventi.
