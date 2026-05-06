# SCHEMA-01 - Schema Migration Readiness

Data: `2026-04-03`

## Obiettivo

Preparare una migrazione controllata del backend principale da bootstrap schema `create_all + ALTER TABLE IF NOT EXISTS` a migrazioni versionate, senza introdurre regressioni operative.

## Stato verificato del backend principale

- File chiave: `backend/app/db/database.py`
- Stato attuale:
  - usa Alembic su startup
  - `DB_SCHEMA_BOOTSTRAP_MODE=metadata_compat` resta disponibile solo come alias deprecato verso Alembic
- Conseguenza:
  - lo schema del backend principale e' ora governato da revisioni versionate
  - il bootstrap raw non e' piu' il percorso attivo

## Stato verificato delle dipendenze

- `backend/pyproject.toml` dichiara `alembic>=1.14.0`
- Nel backend principale risultano ora presenti:
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/README.md`
- `backend/app/db/migrations.py`
- `backend/migrations/versions/20260403_0001_backend_schema_baseline.py`
- Quindi Alembic e' la fonte di verita' dello schema del backend principale

## Riferimento interno gia' esistente nel repository

Il servizio `kpi-reason-engine` usa gia' un modello corretto di migrazioni:

- directory: `kpi-reason-engine/migrations`
- runner: `kpi-reason-engine/app/migrations.py`
- catena revisioni presente:
  - `20260315_0001`
  - `20260315_0002`
  - `20260315_0003`
  - `20260329_0004`
- runbook esplicito: `kpi-reason-engine/docs/runbook.md`

Questo e' importante perche' TenderWriter ha gia' un pattern interno da riusare, invece di inventarne uno nuovo.

## Rischi reali se si interviene male

- Rischio 1: introdurre una baseline Alembic non allineata allo schema realmente in uso nei DB esistenti
- Rischio 2: duplicare o perdere le colonne oggi create via `ALTER TABLE IF NOT EXISTS`
- Rischio 3: rompere lo startup locale/dev se il backend smette di creare tabelle prima che la pipeline migration sia pronta
- Rischio 4: creare divergenza tra ambienti "nuovi" e ambienti "storici"
- Rischio 5: introdurre coupling non testato tra startup FastAPI e bootstrap schema

## Decisione operativa

Non fare ancora la sostituzione del bootstrap runtime.

Prima serve una baseline di migrazione verificata, con replay su database "vuoto" e "gia' popolato", e con una finestra di compatibilita' temporanea.

## Piano zero-regressioni

### Fase 1 - Inventory congelato

Deliverable:
- snapshot dei modelli SQLAlchemy correnti del backend principale
- inventario delle tabelle/indici/constraint attesi
- inventario delle colonne oggi aggiunte via compatibilita' raw

Aggiornamento stato:
- creato helper ripetibile `backend/app/db/schema_inventory.py`
- creato test `backend/tests/test_schema_inventory.py` per certificare le colonne compat legacy nel metadata

Done when:
- esiste un documento o script di inventory ripetibile
- e' chiaro quali elementi devono entrare nella baseline Alembic iniziale

### Fase 2 - Scaffold Alembic senza cambiare startup

Deliverable:
- `backend/migrations/env.py`
- `backend/migrations/versions/`
- eventuale runner dedicato `backend/app/db/migrations.py`
- configurazione Alembic del backend principale

Vincolo:
- `init_db()` resta invariato in questa fase

Done when:
- Alembic puo' leggere il metadata del backend
- esiste un comando locale ripetibile per `upgrade head`

Aggiornamento stato:
- scaffold creato
- startup runtime ancora invariato
- manca ancora una baseline revision reale prima di poter parlare di `upgrade head` utile

### Fase 3 - Baseline revision allineata allo schema attuale

Deliverable:
- revisione iniziale che rappresenti lo schema reale atteso oggi
- revisione successiva che assorba in forma versionata le 4 compatibilita' raw attualmente in `database.py`

Nota:
- la baseline non deve essere "teorica"
- deve riflettere il deployed shape compatibile con gli ambienti esistenti

Done when:
- DB vuoto creato via Alembic produce lo stesso shape funzionale del bootstrap attuale
- DB preesistente non fallisce in upgrade

Aggiornamento stato:
- creata baseline revision `backend/migrations/versions/20260403_0001_backend_schema_baseline.py`
- la revision congela `BASELINE_TABLES` e un metadata snapshot locale alla revision
- la revision crea tabelle mancanti con `metadata.create_all(checkfirst=True)`
- la revision aggiunge anche le 4 colonne compat legacy se mancanti:
  - `users.is_active`
  - `users.is_verified`
  - `ai_gateway_targets.connection_method`
  - `ai_gateway_targets.api_key`
- copertura attuale:
  - test verde sulla presenza della revision
  - test verde sull'allineamento `BASELINE_TABLES <-> inventory`
- limite ancora aperto:
  - non e' ancora stato eseguito un replay live su database disposable PostgreSQL in questo step

### Fase 4 - Test ring pre-switch

Test minimi richiesti:
- database vuoto -> `upgrade head` -> startup app -> smoke green
- database storico simulato senza alcune colonne -> `upgrade head` -> smoke green
- database gia' allineato -> `upgrade head` idempotente
- startup app senza eseguire `create_all` -> route `/health` green

Done when:
- il ring passa in modo ripetibile in locale/CI

Aggiornamento stato:
- creato ring opt-in `backend/tests/test_schema_migration_live_replay.py`
- replay eseguito con esito verde su:
  - DB PostgreSQL vuoto
  - DB storico simulato con `users` e `ai_gateway_targets` privi delle colonne compat legacy
- risultato verificato:
  - `upgrade head` crea le tabelle baseline
  - `alembic_version = 20260403_0001`
  - le 4 colonne compat legacy vengono aggiunte

### Fase 5 - Switch controllato dello startup

Strategia suggerita:
- introdurre modalita' esplicita di bootstrap, per esempio:
  - `metadata_compat`
  - `alembic`
- default iniziale: mantenere comportamento attuale fino a prova completa
- poi invertire il default solo dopo test ring e validazione ambiente

Vincolo:
- evitare cambio "big bang"

Done when:
- l'ambiente target usa migrazioni versionate
- il fallback legacy e' disattivabile in modo esplicito

Aggiornamento stato:
- introdotto setting `DB_SCHEMA_BOOTSTRAP_MODE` nel backend principale
- modalita' attuali:
  - `alembic`
  - `metadata_compat` -> alias deprecato verso `alembic`
- default corrente: `alembic`
- `backend/app/db/database.py` ora puo' delegare esplicitamente a `run_migrations(database_url=settings.database_url)` senza cambiare il default
- fix applicato sul path async:
  - `init_db()` delega le migration a `asyncio.to_thread(...)`
  - questo evita il conflitto `asyncio.run()` dentro un event loop gia' attivo durante lo startup FastAPI
- test verde:
  - `backend/tests/test_schema_bootstrap_mode.py::test_init_db_supports_explicit_alembic_bootstrap_mode`
  - `backend/tests/test_schema_bootstrap_mode.py::test_init_db_metadata_compat_mode_delegates_to_alembic_for_backward_compatibility`
  - `backend/tests/test_schema_containerized_rollout.py::test_backend_one_off_container_bootstraps_via_alembic_mode`
  - `backend/tests/test_schema_containerized_rollout.py::test_backend_one_off_container_uses_alembic_deploy_default`
  - `backend/tests/test_schema_bootstrap_defaults.py::test_code_and_deploy_defaults_prefer_alembic`

Aggiornamento deploy wiring:
- `docker-compose.yml` espone ora:
  - `DB_SCHEMA_BOOTSTRAP_MODE: ${DB_SCHEMA_BOOTSTRAP_MODE:-alembic}`
- il service `backend` monta ora anche:
  - `./backend/migrations:/app/migrations`
  - `./backend/alembic.ini:/app/alembic.ini:ro`
- `.env.example` documenta `DB_SCHEMA_BOOTSTRAP_MODE=alembic`
- questo rende possibile validare `alembic` in one-off container senza rebuild distruttivi del servizio attivo

Aggiornamento rollout locale controllato:
- file attivo `.env` aggiornato con `DB_SCHEMA_BOOTSTRAP_MODE=alembic`
- backup creato: `.env.pre-alembic-rollout-2026-04-03.bak`
- `docker compose up -d --no-deps backend` eseguito con successo
- `docker compose up -d --force-recreate --no-deps backend` eseguito con successo dopo la rimozione del bootstrap raw
- verifiche live post-rollout:
  - `GET /health` verde
  - `GET /docs` verde
  - `GET /openapi.json` verde
  - login admin verde
  - `alembic_version = 20260403_0001`
  - log startup Alembic verde anche dopo recreate del backend
  - script manuale `backend/app/check_db_schema.py` verde con:
    - `BOOTSTRAP_MODE_CONFIG: alembic`
    - `ALEMBIC_VERSION_TABLE: true`
    - `ALEMBIC_VERSION: 20260403_0001`
    - `PUBLIC_TABLE_COUNT: 30`

### Fase 6 - Rimozione compatibilita' raw

Deliverable:
- eliminazione da `backend/app/db/database.py` di:
  - `create_all()`
  - `ALTER TABLE ... IF NOT EXISTS`

Vincolo:
- solo dopo che le migration Alembic sono diventate l'unica fonte di verita'

Done when:
- lo schema del backend principale e' governato solo da revisioni versionate

Aggiornamento stato:
- completata
- `init_db()` non contiene piu':
  - `create_all()`
  - `ALTER TABLE ... IF NOT EXISTS`
- `metadata_compat` non esegue piu' bootstrap raw; delega ad Alembic con warning di deprecazione
- certificazione:
  - `backend/tests/test_schema_migration_pre_fix.py::test_init_db_no_longer_bootstraps_schema_opportunistically`
  - `backend/tests/test_schema_containerized_rollout.py::test_backend_one_off_container_keeps_metadata_compat_as_alembic_alias`

## Sequenza consigliata per Codex

1. creare scaffold Alembic nel backend principale senza modificare `init_db()`
2. generare inventory e baseline revision
3. aggiungere test ring DB vuoto / DB storico simulato
4. introdurre switch di bootstrap
5. migrare il default a `alembic`
6. rimuovere bootstrap legacy

## Cose da non fare

- non rimpiazzare subito `create_all()` con Alembic nello stesso step
- non cancellare i raw `ALTER TABLE` prima di avere revisioni equivalenti
- non assumere che il DB reale coincida perfettamente col metadata corrente
- non usare una baseline autogenerata senza confronto con i campi compat legacy

## Prossimo passo concreto suggerito

Aprire un sotto-step dedicato:

`SCHEMA-01G - eventuale rimozione futura dell'alias metadata_compat`

Scaffold, baseline revision, replay live, deploy wiring, one-off container smoke, rollout locale e rimozione del bootstrap raw ora esistono; il prossimo step eventuale e' solo togliere l'alias `metadata_compat` quando non servira' piu' per rollback/troubleshooting.

### Checklist minima per attivazione controllata

1. Impostare `DB_SCHEMA_BOOTSTRAP_MODE=alembic` solo nell'ambiente target di prova.
2. Riavviare il solo service `backend`.
3. Verificare `GET /health` e i log startup.
4. Verificare la presenza di `alembic_version = 20260403_0001`.
5. Eseguire smoke funzionali minimi su login/admin/tenders.
6. Tenere rollback immediato riportando `DB_SCHEMA_BOOTSTRAP_MODE=metadata_compat`.

Stato checklist nel workspace locale:
- completata

### Verifica operativa rapida

Comando:

`docker exec tw-backend sh -lc "cd /app && PYTHONPATH=/app python app/check_db_schema.py"`

Segnali attesi:
- `BOOTSTRAP_MODE_CONFIG: alembic`
- `ALEMBIC_VERSION_TABLE: true`
- `ALEMBIC_VERSION: 20260403_0001`
