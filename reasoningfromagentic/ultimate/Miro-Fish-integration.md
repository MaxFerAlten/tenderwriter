/home/tendermachine/tender/MiroFish/

/home/tendermachine/tender/tenderwriter/
# 

approfondisci : tenderwriter è un RAG evoluto per la gestione delle gare d'appalto, metre MiroFish è un progetto innovativo per RAG e scoprire in maniera predittiva, analizza entrambi e cerca ci capire se alcune idee implementative Mirofish possono anche essere applicate a tenderwriter Sto confrontando i due codebase/documenti per ricostruire: architettura, pipeline RAG, componenti distintive di MiroFish e quali parti siano trasferibili in TenderWriter senza forzature. Ho già un quadro: TenderWriter è un RAG verticale orientato a ingestion, requirement intelligence e compliance; MiroFish è invece un motore di simulazione predittiva sopra GraphRAG e agenti. Ora entro nei moduli per capire quali idee sono davvero trapiantabili e quali no. Thought for 2m 5s Sì: alcune idee di MiroFish sono applicabili a TenderWriter, ma non come “copia-incolla”. Le due architetture stanno su livelli diversi. TenderWriter oggi è soprattutto un RAG verticale operativo per il dominio gare: HybridRAG locale con dense retrieval su Qdrant, sparse su BM25 e knowledge graph retrieval, più una pipeline di ingestion che per i documenti tender estrae requirement, li materializza, li sincronizza nel grafo e aggiorna compliance/gate di osservabilità. MiroFish invece non è semplicemente un RAG: è un motore predittivo multi-agent. Parte da seed documentali, genera ontologia, costruisce GraphRAG su Zep, crea personas/agent profile, esegue simulazioni dual-platform con memoria temporale aggiornata in tempo reale, poi espone un ReportAgent e interazione con agenti simulati. La conclusione architetturale è questa: TenderWriter = motore di comprensione e produzione documentale per tender reali; MiroFish = sandbox di simulazione e previsione sopra un GraphRAG dinamico. Quindi MiroFish non va “messo dentro” TenderWriter come sostituto del RAG; va usato come fonte di pattern per costruire un layer superiore di rehearsal, scenario analysis e decision intelligence sopra il core TenderWriter. Le idee MiroFish più promettenti per TenderWriter sono queste. 1. Ontology-first ingestion MiroFish fa un passo esplicito di generazione ontologica prima della costruzione del grafo e del setup dell’ambiente simulativo. Questo è molto interessante per TenderWriter, che oggi ha una forte pipeline requirement-centric ma ancora guidata soprattutto da document type e extraction rules/LLM schemas. Portare in TenderWriter un livello ontologico esplicito significherebbe classificare ogni gara in domini e sottodomini stabili, ad esempio: requisiti amministrativi, economico-finanziari, tecnici, criteri premiali, clausole contrattuali, SLA, certificazioni, penalità, subappalto, RTI, avvalimento. Sarebbe utile sia per migliorare retrieval sia per dare struttura al requirement graph. 2. Temporal memory / event memory MiroFish aggiorna il graph con episodi prodotti dagli agenti durante la simulazione; il concetto chiave non è solo “grafo”, ma grafo che evolve nel tempo. TenderWriter ha già eventi e pipeline stages collegati a ingestion, requirements e compliance, ma può beneficiare molto di una memoria temporale più esplicita: quando un requirement è stato estratto, revisionato, consolidato, contestato, approvato, mappato a una sezione proposta, diventato a rischio, sbloccato o chiuso. Questo trasformerebbe il knowledge graph da statico supporto al retrieval a ledger semantico del ciclo di vita della gara. 3. ReportAgent come livello investigativo MiroFish non si ferma al report statico: il ReportAgent usa strumenti diversi per interrogare l’ambiente post-simulazione, inclusi quick search, graph traversal e interview virtuali. TenderWriter potrebbe applicare lo stesso pattern in modo molto concreto: un “Tender Intelligence Agent” capace non solo di rispondere a query RAG, ma di lanciare sotto-task distinti, per esempio: analisi rischi di esclusione, copertura requirement-to-section, lacune probatorie, dipendenze tra allegati, contraddizioni tra capitolato e disciplinare, impatti su scoring tecnico/economico. Questo sarebbe un salto da “chat sul corpus” a analisi strumentata del tender. 4. Scenario simulation / rehearsal Questa è l’idea più potente. MiroFish nasce per simulare futuri possibili. In TenderWriter la controparte naturale non è la simulazione social, ma la simulazione decisionale di gara: cosa succede se il requirement X resta senza evidenza; come cambia il profilo di rischio se sposto una capability da sezione A a sezione B; quali requisiti sono più esposti a contestazione; come reagirebbe una commissione “prudente”, “tecnica”, “formalista” o “orientata al prezzo”; quali sezioni della proposta aumentano la probabilità di punteggio alto. In altre parole: usare agenti non per imitare Twitter/Reddit, ma per rappresentare commissione, RUP, legale, procurement, auditor interno, competitor ipotetico, PM delivery. Questa è una trasposizione molto naturale dell’idea MiroFish dentro un dominio procurement. 5. Persona generation mirata MiroFish genera profili OASIS ricchi partendo dalle entità del grafo. In TenderWriter questo può diventare “stakeholder simulation”: profili sintetici di valutatori o reviewer, derivati dal tipo di gara, dalla PA, dalla categoria merceologica, dai criteri di aggiudicazione, dal lessico del bando e dallo storico interno. Non per fare folklore, ma per generare controlli differenziati: reviewer formalista; reviewer tecnico operativo; reviewer sicurezza/compliance; reviewer economico-finanziario. Ogni persona potrebbe leggere la proposta e produrre osservazioni diverse, migliorando la robustezza dell’offerta prima della consegna. 6. Persisted orchestration state MiroFish gestisce il progetto come oggetto persistente con stati chiari (CREATED, ONTOLOGY_GENERATED, GRAPH_BUILDING, GRAPH_COMPLETED) e conserva file, testo estratto, ontologia, graph metadata e configurazione. TenderWriter già ha osservabilità e task asincroni, ma un project-state più esplicito per l’intero “Tender Intelligence Workflow” renderebbe più robusti resume, recovery e UX operativa. Dove invece non copierei MiroFish. Primo, non porterei in TenderWriter il paradigma “dual-platform social simulation”. È ottimo per public opinion e storytelling predittivo, ma nel procurement è rumore architetturale. La semantica giusta non è “Twitter + Reddit”, ma semmai “fonti normative + bando + proposta + storico interno + review agents”. Secondo, non sostituirei il backbone attuale HybridRAG di TenderWriter con l’approccio Zep/MiroFish. TenderWriter ha già una pipeline molto coerente con il suo dominio: parse, requirement extraction, chunking, indexing, graph sync, compliance sync. Conviene arricchirla, non rimpiazzarla. Terzo, eviterei di partire da “migliaia di agenti”. Nel dominio gare il valore non nasce dal volume di agenti, ma dalla qualità dei ruoli simulati e dalle regole di decisione. Meglio 5-8 agenti specialistici ben progettati che un enjambre enorme. MiroFish punta a una digital world ad alta fedeltà; TenderWriter deve restare più sobrio e verificabile. La mia valutazione sintetica è questa: Applicabilità alta ontology-first requirement graph temporal event memory ReportAgent strumentato stakeholder/reviewer personas scenario rehearsal “what if” Applicabilità media multi-run comparative simulation explainable graph traversal in stile PanoramaSearch interactive interview agents per review interna Applicabilità bassa dual social-platform simulation large-scale swarm simulation sostituzione del backbone RAG attuale con Zep-centric architecture Se dovessi tradurlo in roadmap per TenderWriter, farei 3 fasi. Fase 1 — subito utile Aggiungere un layer ontologico sopra l’estrazione requirement e introdurre un event ledger temporale sul lifecycle dei requirement. Questo migliora subito retrieval, explainability e observability. Fase 2 — differenziante Costruire un Tender Intelligence Agent con tool separati: coverage analysis, evidence gap analysis, contradiction finder, graph path explainer, compliance risk scorer. Qui prendi il pattern ReportAgent di MiroFish e lo verticalizzi sul procurement. Fase 3 — innovativa Creare un Tender Rehearsal Mode: simulazione di una mini-commissione virtuale e di reviewer specialistici che leggono il tender package e la proposta, poi producono score, obiezioni, rischi e suggerimenti di revisione. Qui stai importando l’anima predittiva di MiroFish, ma incastonata in TenderWriter. In una frase finale: sì, MiroFish può dare a TenderWriter il salto da “RAG che capisce i bandi” a “motore che prova in anticipo l’esito della risposta alla gara”. Il punto giusto non è imitare la simulazione social di MiroFish, ma riutilizzarne i pattern di ontologia, memoria temporale, agenti di ruolo e report investigativo sopra il nucleo requirement/compliance già forte di TenderWriter. Se vuoi, nel prossimo passaggio ti preparo una mappa architetturale target TenderWriter + MiroFish ideas, con componenti, flussi e backlog implementativo prioritizzato.

2 allegati

Hai già esposto un'analisi eccellente e articolata nella tua query. Ho letto in profondità entrambi i codebase e posso ora confermare, correggere e approfondire ciascun punto con evidenza diretta dal codice.

---

## Architettura confermata dai sorgenti

**TenderWriter** è strutturato come un sistema multi-servizio: `tw-backend` (FastAPI, core RAG + CRUD), `tw-kpi-reason-engine` (microservizio analitico autonomo), `tw-anonymizer`, `tw-gateway`, `tw-ops-agent`, `llama-tender` e `llama-opencode` come istanze LLM separate. Il cuore RAG è `HybridRAGEngine` con tre canali paralleli: dense retrieval su Qdrant, sparse BM25, graph retrieval su Neo4j, poi RRF (Reciprocal Rank Fusion) e cross-encoder reranker. L'upload di un PDF tender non è semplicemente archiviazione: innesca parsing, chunking semantico, embedding, indicizzazione, estrazione requirement candidates, creazione `TenderRequirement`, sync compliance gate, e pubblicazione eventi di dominio (`tender.document.ingested`, `requirements.extracted`) consumati dal `kpi-reason-engine`.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=d9hAxMiuFYHzfOq2Ud8oTgbtuJE%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

**MiroFish** ha un ciclo di vita esplicito in 5 fasi: Graph Building (seed extraction + GraphRAG su Zep con memoria episodica), Environment Setup (ontology generation + persona generation OASIS), Simulation (dual-platform parallela Twitter/Reddit con temporal memory updates), Report Generation (ReportAgent con toolset: InsightForge, PanoramaSearch, QuickSearch, InterviewSubAgent), Deep Interaction (chat con singoli agenti simulati o con ReportAgent). Gli agenti hanno profili ricchi con `profession`, `bio`, `interestedtopics`, `activitylevel`, `sentimentbias`, `influenceweight`, `activehours`. Il graph espone nodi con `episodes` come campo nativo — la memoria episodica è struttura di primo livello nel grafo, non opzione.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

---

## Moduli trasferibili: analisi puntuale

## 1. Ontology-first ingestion

Dal codice MiroFish emerge che l'ontologia viene generata **prima** della costruzione del grafo e della setup dell'ambiente simulativo, come step esplicito e persistito. In TenderWriter la pipeline oggi parte da `document_type` + extraction rules LLM-guided senza un layer ontologico distinto. Il gap è reale: portare una tassonomia stabile di domini tender (requisiti amministrativi, economico-finanziari, tecnici, premiali, SLA, penali, subappalto, RTI, avvalimento) migliorerebbe sia il retrieval sia la struttura del requirement graph con un investimento basso e ritorno alto.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

## 2. Temporal/episodic memory come struttura di primo livello

In MiroFish gli `episodes` sono campi nativi sui nodi del graph — non metadata laterali. Il `GraphPanel.vue` li espone come sezione dedicata nel detail panel di ogni nodo. In TenderWriter invece il `kpi-reason-engine` ha già un event store append-only (`kpi_domain_events`) con `event_type`, `occurred_at`, `actor_id`, `payload_json`, ma questa ricchezza non risale ancora al knowledge graph del RAG core. **Il trapianto concreto**: fare in modo che ogni nodo del Neo4j tender graph esponga gli episodi del requirement lifecycle (estratto → revisionato → contestato → approvato → mappato → a rischio → chiuso), trasformando il grafo da indice di retrieval a **semantic ledger** della gara.

## 3. ReportAgent con toolset strumentato

MiroFish implementa un ReportAgent con quattro tool distinti: `InsightForge` (analisi profonda), `PanoramaSearch` (graph traversal), `QuickSearch` (ricerca rapida), `InterviewSubAgent` (interviste virtuali agli agenti). Questi tool sono visibili nel frontend Step5 come strumenti espliciti, non come "chat generica". TenderWriter ha già un pattern di chat sul corpus RAG, ma **non ha tool separati** per task specifici. La trasposizione naturale è un `TenderIntelligenceAgent` con:[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

- `CoverageAnalyzer`: requirement-to-section mapping gap
    
- `EvidenceAuditor`: lacune probatorie per ogni requisito high-priority
    
- `ContradictionFinder`: conflitti tra capitolato e disciplinare
    
- `ComplianceRiskScorer`: A4 del `kpi-reason-engine` surfacato come tool interattivo
    
- `GraphPathExplainer`: PanoramaSearch verticale sul grafo Neo4j tender
    

## 4. Persona generation → Stakeholder simulation

Il codice MiroFish mostra profili con `sentimentbias` (da -1.0 a +1.0), `influenceweight`, `stance` (probabile valori: pro/con/neutral), `activitylevel`. Questo schema è trasferibile quasi direttamente a reviewer sintetici per TenderWriter: un commissario "formalista" avrebbe `sentimentbias` vicino a 0, `stance: compliance`, skill set focalizzato su requisiti amministrativi; uno "tecnico" avrebbe `sentimentbias` positivo su innovazione, `stance: technical`. Il codebase MiroFish mostra come i profili siano generati LLM-guided a partire dal grafo — in TenderWriter il seed sarebbero il tipo di gara, la PA committente, la categoria merceologica e i criteri di aggiudicazione.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

## 5. Simulation state machine esplicita

MiroFish gestisce stati del progetto come oggetto persistito con ciclo `CREATED → ONTOLOGY_GENERATED → GRAPH_BUILDING → GRAPH_COMPLETED → SIMULATION_RUNNING → SIMULATION_DONE`. TenderWriter ha già un modello a stati molto più sofisticato nel `kpi-reason-engine` (S0–S13 + `Green/Amber/Red`), ma la **gestione del progetto di gara** come oggetto con state machine esplicita e resumable è ancora debole nel `tw-backend` core (oggi solo `draft / active / inprogress / submitted / won / lost / cancelled`). Il pattern di MiroFish rafforza l'argomento già presente nel piano `tw-kpi-reason-engine` per non rimpiazzare `TenderStatus` ma affiancarlo con lo stato analitico.

## 6. Dual-platform → non trasferibile come tale

Dal codice emerge chiaramente la dualità Twitter/Reddit con parametri separati `twitterconfig` e `redditconfig`, ciascuno con `recency_weight`, `popularity_weight`, `relevance_weight`, `viral_threshold`, `echo_chamber_strength`. Questo meccanismo non ha analogo utile in TenderWriter. La "dual-platform" che avrebbe senso nel procurement è **"dual-reader"**: proposta letta dalla commissione tecnica (peso su contenuto, coerenza, profondità) e dalla commissione economico-finanziaria (peso su prezzi, garanzie, costi nascosti) — ma questa è già una conseguenza della persona simulation, non una replica dell'algoritmo social.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

---

## Roadmap implementativa (con evidenza tecnica)

## Fase 1 — Quick wins con basso rischio di accoppiamento

|Componente|Pattern MiroFish|Implementazione TenderWriter|Effort|
|---|---|---|---|
|Ontology layer|Step pre-graph esplicito|Tassonomia stabile come enum/schema in `kpi-reason-engine`|Basso|
|Episode field su Neo4j nodes|`episodes` come array nativo|Aggiungere `lifecycle_events[]` su nodo `Requirement` in Neo4j|Medio|
|Domain event enrichment|Graph aggiornato da agenti|`tw-backend` già emette eventi; collegarli al graph Neo4j|Medio|

## Fase 2 — TenderIntelligenceAgent strumentato

Il ReportAgent di MiroFish ha un'architettura multi-tool con routing esplicito per tool. Lo stesso pattern può essere applicato come estensione di `HybridRAGEngine.query`: invece di un unico path RAG→LLM, introdurre **tool routing** in cui la query viene classificata e instradata al tool corretto (coverage analysis, evidence audit, contradiction detection, graph traversal). Questo è coerente con il routing `LLMRoute` già presente in TenderWriter.

## Fase 3 — Tender Rehearsal Mode

La Fase 3 è la più innovativa e anche la più costosa. Il codice MiroFish mostra come la simulazione sia orchestrata via `SimulationRunner` con `interview_all_agents` e `check_env_alive` per la gestione del ciclo di vita. In TenderWriter la controparte sarebbe un **Rehearsal Job** (asincrono, gestito da Celery già presente) che:[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

1. Istanzia N reviewer personas derivate dal tipo di gara
    
2. Fa leggere a ciascuno le sezioni della proposta (già chunked in Qdrant)
    
3. Raccoglie score, obiezioni, gap segnalati
    
4. Produce un `RehearsalReport` con distribuzione score, obiezioni per sezione, rischi di esclusione
    

Il `kpi-reason-engine` già espone `GET /v1/tenders/{id}/forecast` — questo endpoint è il luogo naturale dove surfacare anche l'output del Rehearsal.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=d9hAxMiuFYHzfOq2Ud8oTgbtuJE%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

---

## Sintesi finale

Il trapianto architetturalmente più pulito è il pattern **ReportAgent con tool distinti**: in MiroFish è già implementato come astrazione separata dal loop di simulazione, e in TenderWriter si può applicare sopra il RAG core esistente senza toccare la pipeline di ingestion. L'idea MiroFish più sottovalutata ma più impattante è invece la **memoria episodica come struttura di primo livello nel grafo**: portare `lifecycle_events[]` sui nodi Neo4j di TenderWriter trasforma il knowledge graph da indice statico a strumento di audit e previsione, e abilita sia il `kpi-reason-engine` (che oggi ragiona su eventi in DB separato) sia il ReportAgent futuro (che potrebbe fare graph traversal sul lifecycle reale dei requirement).[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md?AWSAccessKeyId=ASIA2F3EMEYE2XTZXCEB&Signature=RKs5KLzyTMvC9MzeYv6zDZX8rl4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEA8aCXVzLWVhc3QtMSJGMEQCIDmV%2BCUTadyYt0CiNGOH4OegdgedHHkzha3H50PDZWsuAiAf1T%2BbHJ8aBGrqUl9XsIDgT45zXSCmRKi8yG1Oq0iePir8BAjY%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMUkyXmFTU%2Fdz9YvanKtAE%2FRFUga0iPVrjrlVqp9artFXtvI%2FLsGC9DZKCb8yJd87JZMdHkDRm70yTty%2BkI0t6Jy2Os0s346vlSGSERAPVvufpZ7c05kicEtEltPlsCNhMy5N75irsaf1Tq6PiZufJ7nh8NnkvD76VzhX5peoeBkTDcfl2f0J1LhQmhcLfhgV02Dem95SyDMEXV1CVQ4QnNOIjJ2AGDPgSKdWem%2BW8nyK2OH20HOfsLi6OiT4PBZ0Yfv4dGfE7WEHm0LOE7TNSPStsHktWWRm1dIELebiN9qyPCbs1BR4UQa8iLdY0uVPMABg%2BIeCzeQnbtaAFNCZf14dS0OZrASDjF2EZUXFDvvm8F8ZApZaSzGukxsvXPyZl6perxPhG%2Fp3j2m%2B2ozRE21%2BQIg%2B0Qo9FLiPhiFsCw0G7jhIoPmStLYyjSDmrOO%2Bpt8hVwGWGDTLHaiY5z4O4u8S7PhnpdFAkZ%2FpRyO%2BVSPPJSNl4BQ%2F6%2BggEVgu6qbv0faBZrGHdTBapU69%2FnIwh3KyNa4WcsvmfZY2GdjXME3hYAEHV4HGK8jbSdCi6piZjs1DGVO252UQ49%2FpPUSBbaVgquFVdwNy2mZxB0MyjGji8xb5MX%2FDGZODtpl5Fry8ALoQb9Gq3pe7C60w7k%2B8P7cUPpohDYm0086qatF6jhE8stLzhAKzlyZaYRrrcmYkYQ8CbSvjOf2WJmgQTeUeXSS55hBxr0S%2BafXV5n41FrQ7J34LljBYKQuPEiNcvQWsyQQHXaS8OMr%2BtT0fjOgz8MUj9AE7RcuLzo5AvO0Lp1zDUjYnPBjqZATPIrxPSkPPKTAVTXO0RUoFVukliESaXfOmdqVnc3PHNDoDAJPkujaAGNH4JXyiwdwZ3ThMszqgS51QmnDo44AJvLNUjuNzke00JE%2B0jiflfozX%2FXHJFzfP4x6mCJTLcVOGxsCFMXpylNvdwZZQo7AP93ibgOx03qHs9jiWf3FlMm5DUpk4YAfrXOoiNUJvfCdgf7jKjbhSA0w%3D%3D&Expires=1776439797)

Preparato usando Claude Sonnet 4.6 Thinking

riesegui le analisi scoprendo di più

3 passaggi completati

Sì: approfondendo il materiale emergono **più segnali strutturali** che semplici bug isolati.  
Il quadro che ne esce è che TenderWriter sta maturando verso una piattaforma governata da workflow e osservabilità, mentre MiroFish resta più potente sul piano agentico ma ancora vicino a un’architettura da prototipo evoluto.

## Quadro emerso

|Progetto|Cosa appare più solido|Cosa mi preoccupa di più|
|---|---|---|
|TenderWriter|La pipeline requisiti ora include backfill dei grafi, rollout controllato della extraction v2, verifica “grounded” delle citazioni, export/evaluation del gold set e refresh automatico della compliance dopo ingest e sync Neo4j. [](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)|La complessità si è spostata dal bugfix al coordinamento tra estrazione, consolidamento, grafo, compliance, workflow operativo e analytics KPI, quindi il rischio principale diventa la coerenza end-to-end più che il singolo difetto locale. [](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)|
|MiroFish|Il cuore distintivo è il ReportAgent con tool InsightForge, PanoramaSearch, QuickSearch e InterviewAgents, integrato in un flusso a 5 step con simulazione, report e deep interaction. [](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)|Il backend usa thread, filesystem locale e polling/IPC file-based per task e simulazione, una combinazione che funziona ma scala male e aumenta il rischio di stato incoerente, recovery fragile e deploy single-node. [](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)|

## TenderWriter

La scoperta più interessante è che il progetto non sta solo “riparando bug”: sta costruendo un vero strato di governo del requirement graph, con backfill operativo, bucket di rollout per LLM v2, fallback euristico e verifica delle citazioni con score grounded.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)  
In più, la compliance non è trattata come un report statico ma come uno stato calcolato da requisiti, sezioni proposta, gate automatici e sincronizzazione verso il grafo, con test che coprono casi come OPEN, PASSED e FAILED in base a copertura e scadenze.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)  
La parte più delicata, però, è l’accoppiamento crescente tra ProposalSection, ContributionUnit, review, rework, gate ed eventi KPI: il codice mostra una macchina a stati sempre più ricca, quindi il prossimo rischio realistico è la divergenza tra stato operativo reale ed eventi derivati in scenari di retry, update concorrenti o transizioni atipiche.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)

## MiroFish

Qui la novità più forte è il livello di ambizione del motore post-simulazione: il ReportAgent genera outline e sezioni in stile ReACT, usa più strumenti di interrogazione del grafo e può perfino orchestrare interviste parallele agli agenti simulati.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)  
Allo stesso tempo, l’ossatura tecnica resta fragile: project/report/task sono persistiti su file JSON e testo locale, molte operazioni lunghe girano in thread daemon, e l’IPC della simulazione passa da cartelle commands/responses con polling su filesystem.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)  
C’è anche un rischio operativo nascosto nel fallback: quando la search API Zep fallisce, il sistema scende su local search con matching semplificato, quindi la qualità del retrieval può degradare silenziosamente proprio nei casi più interessanti dal punto di vista analitico.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)

## Priorità vere

Per TenderWriter la verifica che farei subito è una prova end-to-end “documento →→ extraction →→ consolidated requirements →→ Neo4j →→ compliance →→ KPI”, perché il codice mostra che i pezzi esistono già ma il valore dipende dalla coerenza dell’intera catena.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)  
Per MiroFish, invece, la priorità non è aggiungere feature agentiche ma irrobustire persistenza, job orchestration e recovery, perché oggi molte parti chiave dipendono da thread e storage locale più che da primitive affidabili di coda, stato e multi-tenant backend.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)  
In pratica, TenderWriter mi sembra vicino a una fase di hardening sistemico, mentre MiroFish mi sembra vicino a una fase di “platformization” necessaria per rendere sostenibile ciò che già sa fare bene.

Vuoi che trasformi queste nuove evidenze in una matrice **rischio / impatto / priorità / intervento** per entrambi i progetti?

Preparato usando Gemini 3.1 Pro Thinking

mi serve portare le idee migliori di mirofish in tenderwriter

L'intuizione è eccellente. Attualmente **TenderWriter** ha un'infrastruttura "enterprise" solida (Postgres, Neo4j reale, workflow a stati per la compliance, rollout controllato), mentre **MiroFish** possiede i pattern agentici avanzati (ReACT, multi-tool graph exploration, simulazione di scenari) ma su un'architettura fragile (thread, file IPC).

Portare il "cervello" di MiroFish sui binari di TenderWriter significa trasformare una piattaforma di gestione documentale in un **sistema agentico di redazione e validazione**.

Ecco i tre concetti chiave di MiroFish e come implementarli in TenderWriter con la tua architettura:

## 1. Dal `ReportAgent` al `ProposalWriterAgent` (ReACT Loop)

In MiroFish, il `ReportAgent` genera documenti complessi creando un outline e scrivendo le sezioni in un ciclo ReACT (Thought $\rightarrow$ Action $\rightarrow$ Observation) interrogando il grafo.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)

- **In TenderWriter:** Invece di far generare le sezioni della proposta con una singola chiamata LLM (RAG classico), puoi usare un `ProposalWriterAgent`. L'agente, prima di scrivere la `ProposalSection`, esplora il grafo dei requisiti usando i tool.
    
- **Implementazione:** Abbandona i thread daemon di MiroFish. Usa il tuo strato asincrono e mappa i task su code robuste. L'agente valuta la `ComplianceStatus` corrente e scrive il testo giustificando le scelte in base alle relazioni (`RequirementRelation`) estratte da Neo4j.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)
    

## 2. Strumenti di Esplorazione del Grafo (`InsightForge` e `PanoramaSearch`)

MiroFish dota l'LLM di tool per fare macro-statistiche (`PanoramaSearch`) o estrarre catene di concetti (`InsightForge`). TenderWriter finora popola il grafo Neo4j ma lo usa in modo passivo (RAG standard o retrieve by ID).

- **In TenderWriter:** Esponi al `kpi-reason-engine` e agli agenti di redazione dei tool specifici per il dominio gare:
    
    - `RequirementChainSearch`: Trova tutti i requisiti collegati a un nodo (es. un requisito tecnico che impatta una certificazione di compliance).
        
    - `CompliancePanorama`: Restituisce lo stato globale (Green/Amber/Red) e i colli di bottiglia bloccanti.
        
    - `ConflictDetector`: Cerca discrepanze (es. "La sezione tecnica promette X, ma il requisito legale Y lo vieta").
        

## 3. Dalle `InterviewAgents` ai `SimulatedEvaluators` (Red Teaming)

MiroFish istanzia "personas" con bias, ruoli e background, permettendo all'utente o al ReportAgent di intervistarli.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/c7044adf-7a62-4be1-983b-8515ccbd64e3/MiroFish.md)

- **In TenderWriter:** Puoi usare questo pattern per fare **Red Teaming sulla proposta**. Crea delle personas che simulano la commissione giudicatrice:
    
    - _Responsabile Acquisti:_ focalizzato sui requisiti amministrativi (Annex A, assicurazioni).
        
    - _Valutatore Tecnico:_ focalizzato sulle SLA e sulle architetture.
        
    - _Compliance Officer:_ focalizzato su GDPR e certificazioni.
        
- **Il Flusso:** Prima di inviare la `ProposalSection` in review al team umano (transizione a `IN_REVIEW` ), il sistema lancia le "interviste". L'LLM simula la commissione che fa domande critiche alla bozza della proposta. Le risposte e i gap evidenziati generano automaticamente delle `ReworkAction` se non superano una certa soglia.[](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/130566781/4394bb4b-628c-434c-9da8-50c80029e5e2/tenderwriter.md)
    

## Sintesi Architetturale per la Migrazione

| Pattern MiroFish             | Adattamento Architetturale in TenderWriter                                                         | Vantaggio                                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Zep Cloud API**            | Passaggio al tuo `GraphRetriever` basato su Neo4j reale (driver nativo).                           | Maggiore controllo su Cypher, data privacy enterprise, zero dipendenze da SaaS terzi.           |
| **File-based IPC / Polling** | Sfruttamento della tabella `ContributionUnit` / `ReviewCycle` come macchina a stati asincrona.     | Robustezza, concorrenza gestita a livello DB, eliminazione dei file lock.                       |
| **Agent Prompting via JSON** | Integrazione con la tua pipeline `requirementextractionv2` e il sistema di rollout deterministico. | Tracciabilità di ogni decisione agentica, fall-back euristico nativo in caso di fallimento LLM. |

Da quale di questi tre pilastri vorresti partire per definire il design di dettaglio? (Es. L'architettura del Proposal Writer, i Tool di Neo4j per l'LLM, o i Simulated Evaluators?)

**Sì, le idee migliori di MiroFish possono (e dovrebbero) essere portate in TenderWriter.**

Hai già un’architettura enterprise solida e matura (Postgres + Neo4j reale + Qdrant + Celery + kpi-reason-engine + workflow di requirement/consolidamento/review/gate). MiroFish ha invece il “cervello predittivo” e agentico che manca a TenderWriter: ontology-first, memoria episodica nativa nel grafo, ReportAgent con tool orchestrati, generazione di personas e simulazione di scenari (“rehearsal”).

Non si tratta di copiare codice (l’IPC file-based e i thread daemon di MiroFish sono fragili e non scalano), ma di **trapiantare i pattern concettuali** sopra la tua infrastruttura già robusta.

### Confronto rapido (dal codice reale)

|Aspetto|**TenderWriter** (attuale)|**MiroFish**|**Valore trasferibile**|
|---|---|---|---|
|**Core**|Hybrid RAG (Qdrant dense + BM25 + Neo4j graph) + requirement extraction v2 + compliance sync|GraphRAG su Zep + ontology generation + multi-agent simulation (OASIS)|Alto|
|**Memoria**|Eventi in DB + snapshot KPI|Episodi come campo nativo sui nodi del grafo|**Molto alto**|
|**Generazione output**|LLM call singola per sezione proposta|**ReportAgent ReACT** con outline + tool calls|**Alto**|
|**Intelligenza**|Retrieval + compliance scoring|**InsightForge / PanoramaSearch / InterviewAgents**|**Alto**|
|**Simulazione**|Nessuna|Dual-platform + temporal memory updates|Medio-alto (ma verticalizzato)|
|**Persone**|Utenti reali + ruoli RBAC|**OASIS personas** con bias, stance, activity|Alto (per red-teaming)|
|**Orchestrazione**|Celery + stati su DB (ContributionUnit, ReviewCycle, Gate)|Thread + IPC file-based + project state JSON|**Basso** (usa già il tuo)|

**Conclusione tecnica**: TenderWriter è un **RAG operativo verticale** per gare reali. MiroFish è un **motore predittivo orizzontale** sopra GraphRAG + swarm. Il trasferimento perfetto è usare MiroFish come “cervello di foresight” sopra il “corpo enterprise” di TenderWriter.

### Le 3 idee più potenti da portare (con implementazione concreta)

1. **ProposalWriterAgent (ReACT Loop) – PILASTRO 1 (consigliato come primo)** Oggi in TenderWriter una sezione della proposta è generata con una singola chiamata LLM + RAG. **Da MiroFish**: ReportAgent crea outline → scrive sezione → chiama tool → osserva → ripete (ReACT). **Come farlo in TenderWriter**:
    - Crea un nuovo servizio proposal_writer_agent.py (simile a report_agent.py di MiroFish).
    - Usa il tuo GraphRetriever esistente come tool principale.
    - Aggiungi tool specifici:
        - RequirementChainSearch (Cypher su Neo4j)
        - CompliancePanorama (stato Green/Amber/Red + bottlenecks dal kpi-reason-engine)
        - ConflictDetector
        - EvidenceAuditor
    - Il loop ReACT diventa un task Celery generate_section_with_agent che scrive la ProposalSection solo dopo aver verificato coverage e assenza di contraddizioni.
    - **Vantaggio**: ogni sezione avrà citazioni grounded + ragionamento esplicito visibile all’utente.
2. **Tool di esplorazione grafo (InsightForge + PanoramaSearch)** In MiroFish sono tool espliciti del ReportAgent. **In TenderWriter** puoi esporli direttamente dal tuo GraphRetriever (già presente) e dal kpi-reason-engine:
    - panorama_search → query aggregata su tutti i nodi Requirement + stato compliance.
    - insight_forge → chain traversal su RequirementRelation (dipendenze, conflitti, parent/child).
    - Integra con il frontend nel nuovo pannello “Tender Intelligence” (simile a Step5 di MiroFish).
3. **Simulated Evaluators (Red Teaming) – PILASTRO 3** **Da MiroFish**: OASIS personas con sentiment bias, stance, influence weight. **In TenderWriter**: crea 4-6 reviewer sintetici derivati dal bando (es. “Commissario formalista”, “Valutatore tecnico”, “Compliance Officer”).
    - Prima della transizione DRAFT_READY → IN_REVIEW lancia un job asincrono che fa “intervistare” la bozza della proposta.
    - Ogni evaluator restituisce score + obiezioni + gap.
    - Genera automaticamente ReworkRecord se lo score medio < soglia.
    - Questo è il vero “rehearsal” predittivo: non simuli Twitter, ma simuli la commissione giudicatrice.

### Roadmap pratica (3 fasi, bassa frizione)

**Fase 1 (2-3 settimane) – ProposalWriterAgent** Parti da qui. È il valore più immediato e usa già tutto ciò che hai (Neo4j, Celery, GraphRetriever). Implementa il ReACT loop + 3 tool base. Risultato: generazione sezione proposta diventa “intelligente” invece di “one-shot”.

**Fase 2 (3-4 settimane) – Tool di grafo + Episode Memory** Aggiungi lifecycle_events[] come proprietà nativa sui nodi Requirement in Neo4j (come gli episodes di MiroFish). Espandi i tool del ProposalWriterAgent.

**Fase 3 (4-6 settimane) – Simulated Evaluators + Rehearsal Mode** Crea le personas + job di red-teaming. Aggiungi un nuovo bottone “Simula Commissione” nel frontend.

### Risposta alla tua domanda finale

**Ti consiglio di partire dal PILASTRO 1: l’architettura del ProposalWriterAgent.**

È il più concreto, dà valore immediato al flusso di redazione (che è il core di TenderWriter), riutilizza al 90% il codice esistente e ti permette di validare subito il pattern ReACT + tool prima di investire su red-teaming o memoria episodica.

Se vuoi, nel prossimo messaggio ti preparo:

- Lo schema esatto delle classi (ProposalWriterAgent, ToolRegistry, ReACT loop)
- Il prompt template per il ReACT
- L’integrazione con Celery + stato su ProposalSection

Dimmi solo: “Vai con il design dettagliato del ProposalWriterAgent” e partiamo.

Vuoi invece prima la matrice di rischio/impatto di tutto il trasferimento? O preferisci partire dal red-teaming?

Ho validato direttamente sui sorgenti le tesi principali dell'analisi e sono quasi tutte confermate. Ora ti presento la validazione puntuale + il piano d'azione prioritizzato.

## Validazione delle tesi (evidence-based)

|#|Tesi|Verdetto|Evidenza nel codice|
|---|---|---|---|
|1|TW ha HybridRAG (dense Qdrant + BM25 + Neo4j graph) con RRF + cross-encoder|✅ **Confermato**|`backend/app/rag/__init__.py` dichiara esplicitamente i tre canali; log runtime mostrano inizializzazione Qdrant + Neo4j|
|2|MF ha ReportAgent con InsightForge/PanoramaSearch/QuickSearch/InterviewAgents|✅ **Confermato**|`services/report_agent.py` + Step5 UI mostrano i 4 tool come astrazioni di primo livello|
|3|MF ha ontology generation come step esplicito PRIMA del graph|✅ **Confermato**|`ProjectStatus` enum: `CREATED → ONTOLOGY_GENERATED → GRAPH_BUILDING → GRAPH_COMPLETED`; `OntologyGenerator` è una classe dedicata|
|4|MF ha `episodes` come campo nativo sui nodi del grafo|✅ **Confermato**|`GraphPanel.vue` espone `selectedItem.data.episodes` come sezione dedicata del detail panel|
|5|MF usa IPC file-based + polling + thread daemon (fragile)|✅ **Confermato**|`SimulationIPCClient` scrive JSON in `ipc_commands/`, fa polling su `ipc_responses/` con `poll_interval=0.5s`|
|6|TW ha già Celery + kpi-reason-engine come microservizio autonomo|✅ **Confermato**|`backend/app/celery.py` + cartella `kpi-reason-engine/` con package e spec dedicati|
|7|TW ha requirement_extraction_v2 con rollout deterministico|✅ **Confermato**|`requirement_extraction_v2.py` (schema v1) + `requirement_rollout.py` (bucket hashing) + gold set export|
|8|TW ha state machine ricca (ContributionUnit, ReviewCycle, ReworkAction)|✅ **Confermato**|`ContributionUnitStatus`, `ReviewCycleStatus`, relationship SQLAlchemy tutti presenti|
|9|MF OASIS personas hanno profession/bio/interested_topics/persona + activity_level|✅ **Confermato**|`OasisAgentProfile` dataclass con tutti i campi; `sentiment_bias`/`influence_weight` sono più nella narrativa che in struct formali|
|10|MF ReportAgent usa pattern ReACT con outline + iterazione|✅ **Confermato**|i18n chiavi `reactThought`, `reactGenerateSection`, `outlinePlanComplete` + log `planning_complete`|

**Una correzione all'analisi originale**: i campi `sentiment_bias`, `influence_weight`, `stance` citati dall'analisi non compaiono come attributi strutturati della dataclass `OasisAgentProfile` — appaiono più come concetti di design che come schema consolidato. Questo **rinforza** la raccomandazione: non copiare lo schema MF as-is, ma progettare uno schema pulito specifico per il dominio gare (es. `ReviewerPersona` con `focus_area`, `strictness`, `priority_weights`).

## Le idee che superano il test di realtà

Dopo la validazione, le idee si riordinano così per **rapporto valore/rischio**:

**🟢 Alta applicabilità, basso rischio di accoppiamento**

1. **Ontology layer pre-estrazione** — riutilizzi già il bucket rollout di `requirement_extraction_v2`; basta un enum/schema stabile di domini gara
2. **Tool-routed Intelligence Agent** — il pattern ReACT di MF è già un'astrazione pulita, trapiantabile come nuovo servizio parallelo senza toccare HybridRAG

**🟡 Alta applicabilità, rischio medio (richiede design)** 3. **Lifecycle events nativi sui nodi Neo4j** — concettualmente forte, ma serve decidere se sono proprietà di nodo (array) o relazioni versionate; impatta migration script 4. **Simulated Evaluators / Rehearsal Mode** — altissimo valore di business, ma richiede 4-6 settimane e un prompt-engineering serio per evitare "feedback generico"

**🔴 Sconsigliati** 5. Dual-platform simulation — rumore architetturale nel procurement 6. Sostituzione di HybridRAG con Zep — Zep è un'API esterna SaaS, TW ha ragioni valide per restare self-hosted (privacy PA) 7. Large-scale swarm — nel dominio gare 5-8 ruoli ben modellati battono 1000 agenti

## Piano d'azione prioritizzato

Ti propongo una roadmap a **3 sprint** (≈9 settimane) con decision gates espliciti. Uso la terminologia che ho trovato nel tuo codice (ContributionUnit, kpi-reason-engine, requirement_rollout) per minimizzare l'impedance mismatch.

### Sprint 1 — Ontology Layer + Tool Foundation (≈3 settimane)

**Obiettivo**: dare a TW un vocabolario stabile e i primi tool interrogabili, senza toccare la pipeline di ingestion.

1. **Ontologia gare come schema versionato**
    - Crea `backend/app/ontology/tender_ontology.py` con tassonomia: `AMMINISTRATIVO`, `ECONOMICO_FINANZIARIO`, `TECNICO`, `PREMIALE`, `CLAUSOLE_CONTRATTUALI`, `SLA`, `CERTIFICAZIONI`, `PENALITA`, `SUBAPPALTO`, `RTI`, `AVVALIMENTO`
    - Aggiungi campo `ontology_domain` su `TenderRequirement` (nullable in prima fase)
    - Estendi `requirement_extraction_v2_json_schema` per emettere questo campo
    - Sfrutta il **rollout bucket esistente** per canarycare la v2.1 solo su una % di tender
    - Metriche gate: precisione classificazione ≥ 85% sul gold set → solo allora si promuove a 100%
2. **ToolRegistry embrionale sul HybridRAGEngine**
    - Nuovo modulo `backend/app/intelligence/tools/` con tre tool base:
        - `CoverageAnalyzer`: requirement → sezioni proposta (usa già `ContributionUnit`)
        - `EvidenceAuditor`: requisiti high-priority senza evidence attachment
        - `GraphPathExplainer`: sfrutta Neo4j via il `GraphRetriever` già esistente
    - Espone un unico endpoint `/v1/intelligence/tools/{tool_name}` che restituisce JSON strutturato
    - **Non è ancora ReACT** — sono function calls discrete. Serve come API surface per lo sprint 2.

**Deliverable**: ontologia + 3 tool invocabili isolatamente + test coverage. Zero rischio di regressione su RAG o ingestion.

### Sprint 2 — TenderIntelligenceAgent (≈3 settimane)

**Obiettivo**: trapiantare il pattern ReACT di ReportAgent, ma sobrio.

1. **Agent ReACT sopra il ToolRegistry**
    - `backend/app/intelligence/tender_intelligence_agent.py`
    - Loop: `Thought → ToolCall → Observation → [iter]` con max 5 iterazioni e budget token esplicito
    - Routing iniziale tramite LLM classifier su 4 intent: `coverage_check`, `risk_assessment`, `contradiction_hunt`, `general_qa` (fallback su HybridRAG standard)
    - Logging strutturato di ogni iterazione in `intelligence_agent_runs` table (per audit e debug, sullo stesso pattern di `kpi_domain_events`)
2. **Lifecycle events nativi su Neo4j — fase preparatoria**
    - Migration `20260XXX_requirement_lifecycle_events.py`: aggiunge proprietà `lifecycle_events` (list of JSON) sul label `Requirement`
    - Consumer Celery che ascolta i topic già emessi da `tw-backend` (`requirements.extracted`, `requirements.consolidated`, `requirements.approved`...) e li proietta sul nodo Neo4j corrispondente
    - **Non richiede riscrittura del KPI event store**: è una proiezione lateral, non una sostituzione
3. **Frontend**: pannello "Tender Intelligence" con i 4 tool esposti come pulsanti + text area libera che invoca l'agent completo

**Deliverable**: un agente strumentato che fa cose che il RAG attuale non può fare (es. "dove manca evidence per i requisiti premiali?"). Valore immediato per chi scrive l'offerta.

**Decision gate**: se l'adozione dei tool è < 20% in 2 settimane di beta interna → fermati e rivedi UX prima di investire su Sprint 3.

### Sprint 3 — Rehearsal Mode (≈3 settimane, condizionato)

**Obiettivo**: l'idea più ambiziosa, da affrontare solo dopo aver validato 1 e 2.

1. **Schema `ReviewerPersona`** (non copiare OASIS)
    - Campi: `focus_area` (enum dall'ontologia), `strictness` (1-5), `priority_weights` (dict domain→weight), `mandate` (prompt template), `seed_rules` (lista di must-check)
    - 5 personas di default derivate dal bando: Formalista, Tecnico, Compliance Officer, Economico-Finanziario, RUP simulato
    - Generator LLM-guided che inizializza i `priority_weights` dai criteri di aggiudicazione letti dal bando
2. **Rehearsal Job asincrono** (Celery task, non thread come MF)
    - Input: `tender_id` + versione `ProposalSection` snapshot
    - Ogni persona legge le sezioni via Qdrant retrieval mirato sul proprio `focus_area`
    - Output: `RehearsalReport` con per-persona `score (0-100)`, `objections[]`, `gap_findings[]`
    - Genera automaticamente `ReworkAction` suggerite se score medio < soglia configurabile
3. **Integrazione con forecast endpoint**
    - `GET /v1/tenders/{id}/forecast` del `kpi-reason-engine` include un nuovo blocco `rehearsal_summary`
    - Frontend: pulsante "Simula Commissione" prima di `DRAFT_READY → IN_REVIEW`

**Deliverable**: red-teaming automatico prima della consegna. È qui che TenderWriter smette di essere "un RAG che aiuta a scrivere" e diventa "un sistema che prova in anticipo l'esito".

## Rischi trasversali e mitigazioni

Tre cose su cui insisterei indipendentemente dallo sprint:

Il **rischio principale non è tecnico ma di coerenza end-to-end**: dal codice si vede che la macchina a stati TW è già ricca (ContributionUnit, ReviewCycle, Gate, compliance events, KPI events) e il nuovo agent rischia di emettere azioni che divergono dallo stato reale. Mitigazione: ogni `ReworkAction` generata da agent deve passare per lo stesso domain service usato dagli utenti umani, mai scrivere direttamente su DB.

Il **rischio "feedback generico" sulle personas** è concreto. Se i prompt non sono calibrati sui criteri del bando specifico, le obiezioni saranno banalità. Mitigazione: ogni persona riceve in input un _riassunto strutturato del bando_ generato dal Sprint 1 (ontologia + criteri aggiudicazione), non il testo raw.

Il **costo LLM del Rehearsal Mode** può esplodere (5 personas × 8 sezioni × ReACT loop = molte chiamate). Mitigazione: caching aggressivo delle risposte per `(section_version_hash, persona_id)` e limite di 3 iterazioni ReACT per persona.

---

Se vuoi, il prossimo step naturale è: **ti preparo il design dettagliato dello Sprint 1** (schema ontologia + interfacce dei 3 tool + piano migration) così che tu abbia qualcosa di immediatamente implementabile. Dimmi se procedo con questo o se preferisci partire dal design di un altro sprint.

Entro nei punti più operativi: cosa importare davvero in TenderWriter, dove agganciarlo nel codebase attuale, e quale sequenza evita regressioni architetturali.

Ho confermato due cose strutturali: MiroFish ha davvero pattern forti ma anche parti fragili; TenderWriter ha già quasi tutti i “punti d’aggancio” per importarli bene senza riscrivere il backbone.

Thought for 1m 18s

Proseguo sul piano più utile: **come innestare davvero MiroFish dentro TenderWriter** senza rompere il core.

La lettura dei sorgenti conferma che MiroFish ha tre pattern forti da salvare: workflow esplicito di progetto con ontologia prima del grafo, tool interattivi del ReportAgent, e simulazione/interview orchestrata; ma conferma anche che l’orchestrazione è fragile perché usa IPC via filesystem, polling e stato locale di progetto.

TenderWriter, al contrario, ha già il terreno giusto: entità operative forti come `ContributionUnit`, `ReviewCycle`, `ReworkAction`, `ComplianceGate`; un catalogo eventi canonici; separazione tra `tw-backend` e `tw-kpi-reason-engine`; KPI/forecast; e una macchina analitica S0..S13 pensata proprio per lifecycle e decision support.

Quindi la tesi ora è più netta:

**non devi portare MiroFish come prodotto, devi portarlo come pattern agentico sopra i mattoni enterprise di TenderWriter.**

## Quello che conviene importare per primo

Le quattro idee più forti sono:

**1. Ontology-first layer**  
MiroFish esplicita `CREATED -> ONTOLOGY_GENERATED -> GRAPH_BUILDING -> GRAPH_COMPLETED`, quindi tratta l’ontologia come artefatto di primo livello e non come side effect.  
In TenderWriter questa idea si sposa bene con requirement extraction, graph backfill, compliance e KPI: serve un livello tassonomico stabile sopra i requirement.

**2. ReportAgent tool-driven**  
MiroFish espone chiaramente 4 strumenti: `InsightForge`, `PanoramaSearch`, `QuickSearch`, `InterviewSubAgent`, anche lato UI.  
Questa è l’idea più trasferibile in assoluto: in TenderWriter puoi avere un agente che non “chiacchiera”, ma usa tool specializzati per coverage, evidence, contradiction, graph path.

**3. Episodic / lifecycle memory**  
MiroFish ha una logica di memoria viva nel grafo e un’interazione continua con il mondo simulato. Anche se il dettaglio `episodes` non conviene copiarlo tale e quale, il principio è validissimo: il grafo non deve essere solo retrieval, ma anche storia operativa.  
TenderWriter ha già gli eventi canonici e l’outbox: è il posto perfetto per proiettare il lifecycle dei requirement sul grafo.

**4. Simulated evaluators**  
MiroFish usa interviste e agent profiles per raccogliere punti di vista dal mondo simulato. TenderWriter può trasformare questo pattern in una simulazione della commissione e dei reviewer interni.

---

## Quello che non devi importare

Non importerei:

- IPC file-based, polling, env status su file, command/response directories. È il contrario della direzione architetturale di TenderWriter.
- dual-platform simulation in stile Twitter/Reddit. Nel procurement è rumore.
- swarm massivo di agenti. Nel dominio gare contano 5-8 reviewer forti, non centinaia di agenti deboli.

---

## Architettura target: come diventerebbe TenderWriter

Io la imposterei così.

### Livello 1: core attuale, invariato

Resta il backbone esistente:

- ingestion documenti
- extraction requirement
- consolidamento / review / graph sync
- compliance
- eventi operativi
- KPI engine
- forecast

Questo perché è già coerente con le entità operative e col catalogo eventi di TenderWriter.

### Livello 2: intelligence layer nuovo

Sopra il core aggiungi un nuovo strato:

- `TenderOntologyService`
- `TenderToolRegistry`
- `TenderIntelligenceAgent`
- `GraphLifecycleProjector`
- `ReviewerPersonaService`
- `TenderRehearsalService`

Questo è il trapianto vero di MiroFish.

---

# 1) TenderOntologyService

Qui prendi l’idea di MiroFish “ontology before simulation” e la rendi procurement-native.

## Obiettivo

Ogni `TenderRequirement` deve avere almeno:

- `domain`
- `subdomain`
- `criticality`
- `evaluation_axis`
- `evidence_type`
- `owner_role`

## Esempio di domini

- amministrativo
- economico_finanziario
- tecnico
- premiale
- compliance
- contrattuale
- sicurezza
- organizzativo
- documentale

## Dove agganciarlo

Dentro la pipeline già vicina a `requirement_extraction_v2` / `requirement_review` / `requirement_graph_backfill`, non dentro la chat. TenderWriter ha già abbastanza infrastruttura per farlo bene.

## Scelta importante

Non userei un’ontologia “open world” troppo accademica.  
Partirei con un **catalogo chiuso versionato**, per esempio:

- `ontology_version`
- `domain_code`
- `subdomain_code`
- `mapping_confidence`

Così il rollout è verificabile e non destabilizza il sistema.

---

# 2) TenderToolRegistry

Questo è il cuore del trapianto del ReportAgent.

MiroFish mostra che il valore non è “un LLM che risponde”, ma “un LLM che sa scegliere strumenti diversi”.

## Tool minimi da introdurre in TenderWriter

### `CoverageAnalyzer`

Input:

- tender_id
- proposal_id o proposal_section_id

Output:

- requirement coperti
- requirement non coperti
- coverage per dominio
- coverage per criticità

Questo usa direttamente il modello operativo di TenderWriter, dove contributi, review e rework sono espliciti.

### `EvidenceAuditor`

Input:

- set di requirement
- allegati / contenuti associati

Output:

- requirement con evidence sufficiente
- requirement con evidence debole
- requirement senza evidence

### `ContradictionFinder`

Input:

- requirement consolidati
- sezioni di proposta
- eventuali allegati

Output:

- conflitti semantici
- claim non supportati
- mismatch tra promessa tecnica e vincolo contrattuale

### `CompliancePanorama`

Questo è il corrispettivo di `PanoramaSearch`, ma in verticale procurement.  
Non cerca “propagazione narrativa”, cerca il quadro sintetico del tender:

- gate aperti
- gate falliti
- rework bloccanti
- richiesta contributi scadute
- punti di rischio A4

TenderWriter ha già KPI qualitativi/operativi e classi Green/Amber/Red: quindi questo tool ha una base oggettiva già definita.

### `GraphPathExplainer`

Serve a rispondere a domande come:

- “Perché questo requisito è considerato critico?”
- “Qual è la catena che collega il requisito X alla sezione Y e al gate Z?”
- “Da quali eventi operativi deriva questo rischio?”

Questa è la versione TenderWriter di `InsightForge`.

---

# 3) TenderIntelligenceAgent

Questo è il “ReportAgent trapiantato”.

## Non deve fare

- chat generica
- answer synthesis banale
- secondo RAG parallelo

## Deve fare

Orchestrare i tool e costruire un ragionamento verificabile.

### Pattern

`Question -> classify intent -> choose tool(s) -> collect evidence -> synthesize answer`

### Intent suggeriti

- `coverage_check`
- `evidence_audit`
- `risk_assessment`
- `contradiction_hunt`
- `graph_explain`
- `rehearsal_precheck`

### Perché funziona bene in TenderWriter

Perché il progetto ha già:

- backend transazionale
- eventi
- KPI engine
- modelli operativi
- grafo
- workflow di review

Quindi l’agente non inventa lo stato: lo legge.

## Effetto pratico

TenderWriter smette di essere solo:  
“dammi una risposta sul bando”

e diventa:  
“dimmi dove rischio di perdere punti, su quali sezioni, per quali motivi, e con quale evidenza”.

---

# 4) GraphLifecycleProjector

Questa è la parte più sottovalutata e secondo me la più strategica.

TenderWriter possiede già eventi canonici come:

- `requirements_extracted`
- `proposal_section_updated`
- `contribution_request_created`
- `contribution_review_completed`
- `rework_requested`
- `rework_resolved`
- `compliance_gate_passed`
- `compliance_gate_failed`

Oggi questi eventi servono soprattutto al KPI engine.  
La mossa giusta è **proiettarli anche nel knowledge graph**, per rendere il grafo leggibile in chiave storica.

## Modello suggerito

Per ogni `Requirement` nel grafo:

- `current_status`
- `last_event_type`
- `last_event_at`
- `risk_level`
- `coverage_status`
- `review_state`
- `gate_state`

e in più una relazione/event log collegata tipo:

- `(:Requirement)-[:HAS_LIFECYCLE_EVENT]->(:RequirementEvent)`

Invece di mettere tutto in un array JSON sul nodo, preferisco un modello a nodi-evento o almeno una proiezione ibrida:

- snapshot sintetico sul nodo
- dettaglio storico in nodi evento o tabella correlata

Perché?  
Perché TenderWriter ha già una forte cultura outbox/event-driven; il dettaglio cronologico sarà utile a forecast, audit ed explainability.

---

# 5) ReviewerPersonaService

Qui prendi l’idea OASIS di MiroFish ma la ripulisci.

## Errore da evitare

Non creare personas “romanzate”.

## Scelta corretta

Creare reviewer sintetici con parametri decisionali chiari.

### Esempio di schema

`ReviewerPersona`

- `name`
- `role_type`
- `focus_domains[]`
- `strictness`
- `risk_aversion`
- `scoring_weights`
- `mandatory_checks[]`
- `prompt_profile`
- `active`

### Personas iniziali

- `FormalistaAmministrativo`
- `ValutatoreTecnico`
- `ComplianceOfficer`
- `EconomicoFinanziario`
- `RUPSimulato`
- `DeliveryManagerCritico`

Queste personas non servono a “fare scena”.  
Servono a produrre:

- obiezioni differenziate
- punteggi divergenti
- rework mirati
- suggerimenti di miglioramento

---

# 6) TenderRehearsalService

Questa è la vera eredità predittiva di MiroFish.

MiroFish usa interviste e strumenti post-simulazione per esplorare mondi alternativi. TenderWriter deve fare la stessa cosa, ma su un oggetto molto più concreto: **la proposta di gara prima della consegna**.

## Funzionamento

Input:

- tender_id
- proposal_snapshot_id
- set di reviewer personas

Processo:

1. ogni persona legge il tender package
2. ogni persona legge la proposta o la singola sezione
3. ogni persona formula:
    - score
    - objections
    - gaps
    - critical findings
4. il sistema aggrega tutto in un `RehearsalReport`

Output:

- score medio
- score per persona
- obiezioni per sezione
- requisiti a rischio
- sezioni da rifare
- probabili cause di bocciatura o perdita punteggio

## Dove si integra

Subito prima di:

- `DRAFT_READY`
- `IN_REVIEW`
- `GATE APPROVAL`
- `SUBMISSION`

TenderWriter ha già stati, review e rework: quindi il rehearsal non vive a parte, ma alimenta il workflow reale.

---

## Ordine giusto di implementazione

Qui serve disciplina.

### Wave 1

**Ontology + ToolRegistry + Coverage/Evidence/CompliancePanorama**

Perché:

- basso rischio
- alto valore
- nessuna dipendenza da agent loop complessi

### Wave 2

**TenderIntelligenceAgent + GraphLifecycleProjector**

Perché:

- massimizza explainability
- usa dati già presenti
- rende il sistema più investigativo

### Wave 3

**ReviewerPersonaService + TenderRehearsalService**

Perché:

- è il salto più innovativo
- richiede prompt design serio
- va costruito dopo che i tool producono segnali affidabili

---

## Dove lo aggancerei nel codebase TenderWriter

### Backend

Nuovi moduli probabili:

- `backend/app/intelligence/ontology.py`
- `backend/app/intelligence/tool_registry.py`
- `backend/app/intelligence/tools/coverage_analyzer.py`
- `backend/app/intelligence/tools/evidence_auditor.py`
- `backend/app/intelligence/tools/compliance_panorama.py`
- `backend/app/intelligence/tools/graph_path_explainer.py`
- `backend/app/intelligence/agent.py`
- `backend/app/intelligence/reviewer_personas.py`
- `backend/app/intelligence/rehearsal.py`

### API

- `POST /api/intelligence/query`
- `POST /api/intelligence/rehearsal`
- `GET /api/intelligence/rehearsal/{id}`
- `GET /api/intelligence/tender/{id}/panorama`

### KPI integration

Estendere il forecast e la diagnostica per includere:

- `rehearsal_summary`
- `coverage_risk`
- `evidence_risk`
- `reviewer_divergence`

Il forecast endpoint nel mondo KPI è già previsto come capability del servizio, quindi è un punto naturale di integrazione.

### Frontend

Nuove viste/pannelli:

- `Tender Intelligence`
- `Coverage & Evidence`
- `Simula Commissione`
- `Perché questo tender è Amber/Red?`

---

## Decisione architetturale più importante

La scelta chiave è questa:

**il “motore MiroFish” in TenderWriter non deve possedere lo stato. Deve leggerlo, interpretarlo e proporre azioni.**

Lo stato canonico resta in:

- Postgres / backend
- KPI reason engine
- grafo Neo4j come proiezione controllata

Questo evita il problema classico dei sistemi agentici: creare una seconda verità.

---

## La mia raccomandazione finale

Se l’obiettivo è “portare le idee migliori di MiroFish in TenderWriter”, la sequenza migliore è:

**1. Tool-driven intelligence**  
**2. Lifecycle memory nel grafo**  
**3. Proposal/Review rehearsal**

In termini di valore business, il vero salto è questo:

- prima: TenderWriter capisce il bando e aiuta a scrivere
- dopo: TenderWriter capisce il bando, aiuta a scrivere, e **simula in anticipo come verrà giudicata l’offerta**

Questa è esattamente la parte più preziosa di MiroFish, ma finalmente messa sopra un’architettura che può reggerla.

Nel prossimo passaggio posso andare su uno di questi due livelli:  
**A)** design tecnico dettagliato dei nuovi moduli Python/FastAPI/Celery  
oppure **B)** backlog implementativo sprint-by-sprint con priorità, dipendenze e rischio.


Vado sul livello operativo: design tecnico e backlog, ancorandoli ai punti d’aggancio reali dei due codebase così da evitare una proposta “teorica”.

Thought for 1m 6s

Perfetto. Vado con una proposta **implementabile**: design tecnico target + backlog ordinato per introdurre in TenderWriter le idee migliori di MiroFish, senza importarne le fragilità.

Il punto fermo è questo: MiroFish nasce come motore di simulazione e “rehearsal” in 5 fasi — Graph Building, Environment Setup, Simulation, Report Generation, Deep Interaction — con ReportAgent dotato di 4 tool espliciti e workflow di progetto persistito (`created`, `ontology_generated`, `graph_building`, `graph_completed`). TenderWriter, invece, ha già un backbone enterprise con `ContributionUnit`, `ReviewCycle`, `ReworkAction`, `ComplianceGate`, outbox eventi verso `tw-kpi-reason-engine`, responsabilità chiare tra `tw-backend` e servizio KPI, e capacità di forecast/read-only analytics. Quindi il trapianto corretto è: **pattern agentici di MiroFish sopra il dominio operativo di TenderWriter**.

## Architettura target

Propongo 5 nuovi blocchi nel `tw-backend`, più una proiezione sul grafo e un arricchimento del `tw-kpi-reason-engine`.

`TenderOntologyService`  
Produce una tassonomia stabile per requirement e sezioni. Non sostituisce `requirement_extraction_v2`, la arricchisce. L’output minimo non deve essere narrativo ma strutturato: `domain`, `subdomain`, `criticality`, `evidence_type`, `owner_role`, `evaluation_axis`, `ontology_version`. Questo innesta in TenderWriter il pattern di MiroFish “ontology before graph”, ma lo rende controllabile via rollout e gold-set, coerentemente con l’orientamento già presente verso modelli versionati, forecast progressivo e backfill marcato.

`TenderToolRegistry`  
È il cuore del trapianto del ReportAgent. In MiroFish il valore non è la chat, ma il fatto che il ReportAgent possa usare `InsightForge`, `PanoramaSearch`, `QuickSearch` e `InterviewSubAgent` come primitive di primo livello, persino esposte in UI. In TenderWriter questi diventano tool verticali di procurement: `CoverageAnalyzer`, `EvidenceAuditor`, `CompliancePanorama`, `GraphPathExplainer`, `ContradictionFinder`.

`TenderIntelligenceAgent`  
È l’equivalente del ReportAgent, ma non genera un report su un mondo simulato: interroga il tender reale e il suo workflow. Deve classificare l’intent, scegliere i tool, raccogliere evidenze e sintetizzare una risposta verificabile. Non deve possedere stato; deve leggere Postgres, Neo4j e KPI engine, perché in TenderWriter la “single source of truth” è già una preoccupazione esplicita e la UI admin è stata voluta senza override analitico diretto.

`GraphLifecycleProjector`  
TenderWriter ha già un catalogo eventi canonici e un pattern outbox verso `tw-kpi-reason-engine`, inclusi eventi come `requirements_extracted`, `proposal_section_updated`, `contribution_request_created`, `contribution_review_completed`, `rework_requested`, `rework_resolved`, `compliance_gate_opened`, `compliance_gate_passed`, `compliance_gate_failed`, `sla_breached`. La mossa giusta è proiettare anche questi eventi nel grafo dei requirement. Così importi da MiroFish il valore della memoria dinamica, ma usando l’infrastruttura eventi di TenderWriter invece di IPC file-based.

`ReviewerPersonaService` + `TenderRehearsalService`  
Questa è la versione TenderWriter della simulazione MiroFish. Non Twitter/Reddit, ma reviewer sintetici: formalista amministrativo, tecnico, compliance officer, economico-finanziario, RUP simulato. Il loro output non è folklore: score, obiezioni, gap, cause di rischio esclusione/perdita punteggio. Questo si integra naturalmente con `ReviewCycle`, `ReworkAction`, `ComplianceGate` e forecast.

---

## Package design consigliato

Nel backend introdurrei questa struttura:

backend/app/intelligence/  
  __init__.py  
  ontology.py  
  schemas.py  
  tool_registry.py  
  agent.py  
  rehearsal.py  
  personas.py  
  lifecycle_projector.py  
  tools/  
    __init__.py  
    coverage_analyzer.py  
    evidence_auditor.py  
    compliance_panorama.py  
    graph_path_explainer.py  
    contradiction_finder.py

Nel KPI engine aggiungerei solo il minimo:

kpi-reason-engine/app/  
  rehearsal_contract.py  
  rehearsal_analytics.py

e nel frontend:

frontend/src/features/intelligence/  
  TenderIntelligencePanel.tsx  
  RehearsalPanel.tsx  
  hooks/useTenderIntelligence.ts  
  hooks/useRehearsal.ts

Questa scelta è coerente con la separazione già voluta tra `tw-backend` come BFF transazionale e `tw-kpi-reason-engine` come motore di scoring, stato, diagnostica e forecast read-only.

---

## Contratti dati minimi

### 1. Ontology tag sul requirement

Da aggiungere a `TenderRequirement` o equivalente modello strutturato:

{  
  "ontology_domain": "compliance",  
  "ontology_subdomain": "certificazioni",  
  "criticality": "high",  
  "evidence_type": "documentary_proof",  
  "owner_role": "legal",  
  "evaluation_axis": "mandatory",  
  "ontology_version": "tw-ontology-v1"  
}

### 2. Snapshot lifecycle sul grafo

Non metterei tutto in un array JSON sul nodo. Farei doppio livello:

Sul nodo `Requirement`:

{  
  "current_status": "reviewed",  
  "coverage_status": "partial",  
  "gate_state": "open",  
  "risk_level": "amber",  
  "last_event_type": "rework_requested",  
  "last_event_at": "2026-04-17T10:15:00Z"  
}

E in più una relazione:

(:Requirement)-[:HAS_LIFECYCLE_EVENT]->(:RequirementEvent)

con payload esteso dell’evento.

Questo è più robusto di un semplice array, più queryable, e si allinea meglio al catalogo eventi già esplicito di TenderWriter.

### 3. Reviewer persona

{  
  "persona_id": "formalista_amministrativo",  
  "role_type": "reviewer",  
  "focus_domains": ["amministrativo", "compliance"],  
  "strictness": 5,  
  "risk_aversion": 5,  
  "scoring_weights": {  
    "mandatory_coverage": 0.35,  
    "evidence_depth": 0.30,  
    "formal_consistency": 0.25,  
    "innovation": 0.10  
  },  
  "mandatory_checks": [  
    "signed_annexes",  
    "required_certifications",  
    "no_contradictions_with_tender_terms"  
  ],  
  "prompt_profile": "..."  
}

Non copierei OASIS as-is. In MiroFish i profili sono ricchi e utili, ma in TenderWriter la cosa giusta è un profilo **decisionale**, non narrativo.

---

## Tool design

### CoverageAnalyzer

Legge requirement strutturati, sezioni proposta, contributi e mapping. Deve rispondere a domande del tipo: “quali requirement high priority non hanno copertura?”  
Ha senso perché TenderWriter definisce `ContributionUnit` come vero atomo operativo, collegabile a sezioni, allegati, testo e review.

### EvidenceAuditor

Misura profondità probatoria. È il corrispettivo operativo del KPI A3 “evidence depth”. Serve sia all’agente sia al rehearsal.

### CompliancePanorama

È la versione procurement di `PanoramaSearch`: ricostruisce il quadro globale del tender, ma in termini di KPI, gate, richieste aperte, rework bloccanti e forecast. Il KPI engine è già pensato per snapshot, diagnostica, transizioni e forecast.

### GraphPathExplainer

Prende un requirement, una sezione o un finding e ricostruisce la catena: requisito → contributo → review → rework → gate → rischio. È la cosa più vicina a `InsightForge`, ma grounded sul dominio reale.

### ContradictionFinder

Confronta:

- requirement consolidati
- sezione proposta
- evidence allegata
- eventuali vincoli contrattuali/compliance

Output:

- contraddizione normativa
- promessa tecnica non provata
- copertura apparente ma non valida

---

## Agent loop

Il loop deve essere sobrio. Non farei un ReACT “aperto”.

1. classify_intent  
2. choose_tools(max 3)  
3. execute_tools  
4. merge evidence  
5. synthesize answer  
6. optionally create recommended actions

Con limiti:

- max 3 tool call per query
- max 2 iterazioni correttive
- budget token fisso
- log strutturato per run

Questo evita che il nuovo agente diventi una macchina opaca o costosa.

API consigliata:

POST /api/intelligence/query  
POST /api/intelligence/tools/{tool_name}  
GET  /api/intelligence/tenders/{id}/panorama  
POST /api/intelligence/rehearsals  
GET  /api/intelligence/rehearsals/{id}

Il risultato di `query` deve essere sempre strutturato:

{  
  "intent": "coverage_check",  
  "tools_used": ["CoverageAnalyzer", "CompliancePanorama"],  
  "answer": "...",  
  "findings": [...],  
  "recommended_actions": [...],  
  "provenance": {...}  
}

---

## Rehearsal mode

Qui c’è il vero salto di valore.

MiroFish si presenta esplicitamente come “rehearsal laboratory for decision-makers” e usa simulazione + report + deep interaction per esplorare scenari. In TenderWriter questa filosofia va verticalizzata sulla gara: **provare l’offerta prima della consegna**.

### Input

- `tender_id`
- `proposal_id` o `proposal_snapshot_id`
- personas selezionate
- modalità: `full`, `section`, `pre_gate`

### Processo

1. carica requirement + sezioni + evidence + stato workflow
2. per ogni persona:
    - recupera solo il contesto rilevante per focus domain
    - valuta score
    - formula obiezioni
    - evidenzia gap
3. aggrega
4. produce `RehearsalReport`
5. opzionalmente genera `recommended_rework_actions`

### Output

{  
  "overall_score": 71,  
  "health_projection": "amber",  
  "persona_scores": [  
    {"persona_id": "formalista_amministrativo", "score": 62},  
    {"persona_id": "valutatore_tecnico", "score": 79}  
  ],  
  "section_findings": [...],  
  "requirement_gaps": [...],  
  "recommended_reworks": [...]  
}

### Integrazione workflow

Il rehearsal deve agganciarsi ai passaggi dove il tender è davvero sensibile:

- prima di `IN_REVIEW`
- prima di aprire/chiudere gate importanti
- prima di `SUBMITTED`

Non sostituisce review umana, ma la anticipa e la rende più mirata.

---

## Backlog ordinato

### Wave 1 — 2/3 settimane

Obiettivo: importare il 60% del valore MiroFish con il 20% del rischio.

Da fare:

- `TenderOntologyService`
- schema ontology v1
- `TenderToolRegistry`
- tool: `CoverageAnalyzer`, `EvidenceAuditor`, `CompliancePanorama`
- endpoint base intelligence
- pannello FE “Tender Intelligence”

Done when:

- requirement e sezioni hanno tagging ontologico minimo
- l’utente può lanciare 3 analisi strutturate su un tender
- niente modifica al workflow esistente

Dipendenze:

- requirement extraction v2
- graph backfill
- KPI endpoints snapshot/diagnostics/forecast

### Wave 2 — 3 settimane

Obiettivo: rendere TenderWriter investigativo.

Da fare:

- `TenderIntelligenceAgent`
- `GraphPathExplainer`
- `ContradictionFinder`
- `GraphLifecycleProjector`
- proiezione eventi → grafo

Done when:

- una domanda complessa usa tool multipli
- il grafo mostra anche stato/lifecycle
- una risposta può spiegare “perché” un rischio esiste

Dipendenze:

- catalogo eventi canonici attivo
- outbox stabile
- mapping requirement↔section↔contribution

### Wave 3 — 4/6 settimane

Obiettivo: portare la parte più distintiva di MiroFish.

Da fare:

- `ReviewerPersonaService`
- `TenderRehearsalService`
- `RehearsalReport`
- UI “Simula Commissione”
- integrazione forecast/rehearsal

Done when:

- il sistema produce score e obiezioni per persona
- può suggerire rework strutturati
- il forecast include anche segnali di rehearsal

---

## Rischi da gestire

Il rischio principale non è tecnico ma di **seconda fonte di verità**. TenderWriter ha già scelto di non introdurre override diretti nel flusso analitico; va mantenuta la stessa disciplina anche con agent e rehearsal. Il nuovo layer deve leggere, spiegare e suggerire, non governare in autonomia lo stato canonico.

Il secondo rischio è di fare personas troppo “LLM-style” e poco utili. Se i reviewer non sono ancorati a requirement, gates, evidence e scoring weights, produrranno feedback generico.

Il terzo rischio è il costo. Il rehearsal va fatto con caching su snapshot proposta/persona e con un massimo ristretto di iterazioni.

---

## La mia raccomandazione netta

Partirei così:

**prima ToolRegistry, poi IntelligenceAgent, poi Rehearsal.**

Perché è la sequenza che:

- sfrutta meglio i confini già stabiliti tra backend e KPI engine,
- usa davvero gli atomi operativi già presenti (`ContributionUnit`, `ReviewCycle`, `ReworkAction`, `ComplianceGate`),
- e importa il meglio di MiroFish — tool espliciti, memoria dinamica, rehearsal — senza ereditare polling, filesystem IPC o simulazione social.

Il prossimo passo più utile è il **design dettagliato della Wave 1**, con:

- schema Python/Pydantic dei nuovi oggetti,
- firma dei 3 tool,
- payload API,
- piano migration DB/grafo,
- criteri di test.

Posso partire subito da quello.

si

Sto ricostruendo il design Wave 1 sui punti d’aggancio reali: requirement extraction, servizi requirement/compliance, forecast/KPI e i moduli MiroFish che ispirano tool e ontologia.

Thought for 51s

Perfetto. Ti propongo la **Wave 1 concreta**: importare da MiroFish due idee ad altissimo rendimento e basso rischio:

- **ontology-first enrichment**
- **tool-driven intelligence**, senza ancora introdurre agent loop complesso o rehearsal

La scelta è coerente con i due codebase: MiroFish espone già workflow esplicito con stato `created → ontology_generated → graph_building → graph_completed` e mette al centro i 4 tool del ReportAgent (`InsightForge`, `PanoramaSearch`, `QuickSearch`, `InterviewSubAgent`), mentre TenderWriter ha già il dominio operativo forte, il catalogo eventi, i KPI A1/A3/A4 e le entità `ContributionUnit`, `ReviewCycle`, `ReworkAction`, `ComplianceGate` su cui costruire strumenti verticali.

## Obiettivo della Wave 1

Alla fine della Wave 1 TenderWriter deve saper fare tre cose nuove:

1. classificare ogni requirement in una tassonomia stabile di gara;
2. eseguire analisi strutturate su un tender, senza passare da chat generica;
3. restituire segnali utili a proposal writer, compliance e forecast, ma **senza creare una seconda fonte di verità**, che il progetto esplicitamente vuole evitare.

## Cosa entra e cosa resta fuori

Entra:

- `TenderOntologyService`
- `TenderToolRegistry`
- 3 tool: `CoverageAnalyzer`, `EvidenceAuditor`, `CompliancePanorama`
- API intelligence minimali
- FE panel minimale

Resta fuori per ora:

- agent ReACT completo
- reviewer personas
- rehearsal mode
- lifecycle projection sul grafo

Questa separazione è importante: MiroFish mostra che i tool hanno valore autonomo già prima della simulazione profonda, mentre la sua orchestrazione IPC file-based è esattamente la parte da **non** importare.

---

## Design tecnico Wave 1

### 1. Nuovo package

backend/app/intelligence/  
  __init__.py  
  schemas.py  
  ontology.py  
  tool_registry.py  
  tools/  
    __init__.py  
    coverage_analyzer.py  
    evidence_auditor.py  
    compliance_panorama.py

Non toccherei ancora `backend/app/rag/engine.py` come punto di orchestrazione principale. In Wave 1 questi tool devono vivere come capability indipendenti invocabili via API.

---

## 2. Schema ontologico

### File

`backend/app/intelligence/schemas.py`

from __future__ import annotations  
from enum import Enum  
from pydantic import BaseModel, Field  
from typing import Literal  
  
class OntologyDomain(str, Enum):  
    AMMINISTRATIVO = "amministrativo"  
    ECONOMICO_FINANZIARIO = "economico_finanziario"  
    TECNICO = "tecnico"  
    PREMIALE = "premiale"  
    COMPLIANCE = "compliance"  
    CONTRATTUALE = "contrattuale"  
    SICUREZZA = "sicurezza"  
    ORGANIZZATIVO = "organizzativo"  
    DOCUMENTALE = "documentale"  
    ALTRO = "altro"  
  
class RequirementOntologyTag(BaseModel):  
    ontology_domain: OntologyDomain  
    ontology_subdomain: str = Field(min_length=2, max_length=80)  
    criticality: Literal["high", "medium", "low"] = "medium"  
    evidence_type: Literal[  
        "documentary_proof",  
        "narrative_claim",  
        "certification",  
        "financial_statement",  
        "organizational_plan",  
        "technical_attachment",  
        "mixed",  
    ] = "documentary_proof"  
    owner_role: Literal[  
        "legal", "finance", "technical", "bid_manager", "security", "operations", "unknown"  
    ] = "unknown"  
    evaluation_axis: Literal["mandatory", "scored", "supporting", "informational"] = "mandatory"  
    ontology_version: str = "tw-ontology-v1"  
    mapping_confidence: float = Field(ge=0.0, le=1.0, default=0.8)

### Motivo

TenderWriter ha già requirement strutturati, review state, graph state, metadata e rollout/versioning della extraction v2; quindi l’ontologia deve essere **un’estensione compatibile**, non una seconda estrazione parallela.

---

## 3. `TenderOntologyService`

### File

`backend/app/intelligence/ontology.py`

### Responsabilità

- derivare il tag ontologico da requirement già estratti;
- farlo in modo deterministico o semi-deterministico;
- scrivere il risultato in `metadata_json` del requirement nella prima iterazione.

### Strategia

Farei due livelli:

**Step A — regole deterministiche**  
Keyword/rule mapping:

- “certificazione”, “ISO”, “GDPR”, “DPO” → `compliance`
- “fatturato”, “bilancio”, “capacità economica” → `economico_finanziario`
- “SLA”, “uptime”, “tempi di intervento” → `tecnico`
- “allegato”, “istanza”, “dichiarazione” → `documentale`
- “penale”, “risoluzione”, “clausola” → `contrattuale`

**Step B — fallback LLM opzionale**  
Solo se la regola non arriva a una soglia minima.

### Persistenza

Nella Wave 1 non farei migration SQL su tabella requirement se non serve.  
Scriverei in `metadata_json` così:

{  
  "ontology": {  
    "ontology_domain": "compliance",  
    "ontology_subdomain": "certificazioni",  
    "criticality": "high",  
    "evidence_type": "certification",  
    "owner_role": "legal",  
    "evaluation_axis": "mandatory",  
    "ontology_version": "tw-ontology-v1",  
    "mapping_confidence": 0.91  
  }  
}

Questo minimizza il rischio e si allinea al fatto che TenderWriter usa già `metadata_json` su requirement e relation.

---

## 4. Hook nella pipeline esistente

Il punto di aggancio migliore è subito **dopo** `requirement_extraction_v2` e **prima** delle funzioni che usano i requirement per review/backfill/export.

Ordine consigliato:

document ingest  
→ requirement_extraction_v2  
→ requirement verification  
→ ontology tagging  
→ consolidation/review  
→ graph backfill/sync  
→ compliance sync

Questa scelta è coerente con il fatto che:

- `requirements_extracted` è già evento canonico;
- A1/A3/A4 già dipendono dalla qualità strutturale dei requirement;
- il forecast del KPI engine consuma segnali di coverage, evidence e compliance.

---

## 5. ToolRegistry

### File

`backend/app/intelligence/tool_registry.py`

from __future__ import annotations  
from collections.abc import Callable  
from typing import Any  
  
class TenderToolRegistry:  
    def __init__(self) -> None:  
        self._tools: dict[str, Callable[..., Any]] = {}  
  
    def register(self, name: str, tool: Callable[..., Any]) -> None:  
        self._tools[name] = tool  
  
    def get(self, name: str) -> Callable[..., Any]:  
        return self._tools[name]  
  
    def list_tools(self) -> list[str]:  
        return sorted(self._tools.keys())

### Registrazione iniziale

- `coverage_analyzer`
- `evidence_auditor`
- `compliance_panorama`

Questa è la trasposizione minima del pattern MiroFish “tool-first” senza ancora introdurre il ReportAgent completo.

---

## 6. Tool 1 — CoverageAnalyzer

### Scopo

Risponde a:

- quali requirement non sono coperti?
- quali requirement ad alta priorità sono solo parzialmente coperti?
- quale dominio ontologico è scoperto?

### Input

{  
  "tender_id": 123,  
  "proposal_id": 77  
}

### Output

{  
  "summary": {  
    "total_requirements": 42,  
    "fully_covered": 18,  
    "partially_covered": 11,  
    "uncovered": 13,  
    "high_priority_uncovered": 5  
  },  
  "by_domain": [  
    {  
      "domain": "compliance",  
      "total": 8,  
      "covered": 3,  
      "partial": 2,  
      "uncovered": 3  
    }  
  ],  
  "gaps": [  
    {  
      "requirement_id": 991,  
      "summary": "...",  
      "priority": "high",  
      "ontology_domain": "compliance",  
      "mapped_section_id": null,  
      "coverage_status": "uncovered"  
    }  
  ]  
}

### Implementazione

Usa i requirement strutturati e lo stesso modello che nel frontend oggi riassume `fully_addressed / partially_addressed / not_addressed` e `mapped/unmapped`. Quindi il tool non inventa una semantica nuova: la formalizza come API server-side.

---

## 7. Tool 2 — EvidenceAuditor

### Scopo

È il primo vero ponte con A3.

Il glossario KPI fissa A3 come “evidence depth score”, quindi il tool deve misurare **profondità probatoria**, non solo presenza testo.

### Input

{  
  "tender_id": 123,  
  "proposal_id": 77,  
  "only_high_priority": true  
}

### Output

{  
  "summary": {  
    "requirements_checked": 15,  
    "strong_evidence": 4,  
    "weak_evidence": 6,  
    "missing_evidence": 5  
  },  
  "findings": [  
    {  
      "requirement_id": 102,  
      "summary": "Provide signed annex",  
      "priority": "high",  
      "evidence_status": "missing",  
      "expected_evidence_type": "documentary_proof",  
      "owner_role": "legal"  
    }  
  ]  
}

### Regole Wave 1

- `strong`: citation/evidence presente e coerente col tipo atteso
- `weak`: solo claim narrativo o mapping sezione senza prova
- `missing`: niente allegato/prova/citazione

Anche qui: niente LLM in prima battuta.  
Prima sfrutta requirement, sezioni, metadati, allegati e mapping.

---

## 8. Tool 3 — CompliancePanorama

### Scopo

È la versione TenderWriter di `PanoramaSearch`, ma grounded su KPI e workflow.

### Input

{  
  "tender_id": 123  
}

### Output

{  
  "health": "amber",  
  "analytical_phase": "S8",  
  "auto_gate_status": "open",  
  "summary": {  
    "failed_gates": 1,  
    "open_gates": 2,  
    "blocking_reworks": 3,  
    "unresolved_requirements": 9,  
    "high_priority_unresolved": 4  
  },  
  "top_risks": [  
    {  
      "code": "failed_gate",  
      "severity": "critical",  
      "summary": "1 failed compliance gate is still reflected in telemetry."  
    }  
  ]  
}

### Implementazione

Questo tool deve chiamare il `kpi_reason_engine` o il servizio proxy già presente nel backend, non ricalcolare tutto localmente.  
La logica esiste già:

- health classes green/amber/red
- A4 risk
- unresolved requirements
- failed/open compliance gates
- analytical phases S0..S13

---

## 9. API design

### Nuovo router

`backend/app/api/intelligence.py`

### Endpoint

GET  /api/intelligence/tools  
POST /api/intelligence/tools/coverage-analyzer  
POST /api/intelligence/tools/evidence-auditor  
POST /api/intelligence/tools/compliance-panorama

### Response envelope

Uniforme:

{  
  "tool": "coverage-analyzer",  
  "status": "ok",  
  "result": {...}  
}

In Wave 1 eviterei `/query` generico.  
Prima fai tool espliciti. Il router agentico arriva dopo.

---

## 10. Frontend Wave 1

Nuovo pannello nella zona observability / operational workspace.

### Componenti

- `TenderIntelligencePanel.tsx`
- 3 card/tool buttons
- tender selector
- render JSON/results strutturati

### UX minima

- bottone “Coverage”
- bottone “Evidence”
- bottone “Compliance panorama”

Questo segue l’idea MiroFish “interactive tools” ma resta sobrio.

---

## 11. Testing

### Unit test

- ontology keyword mapping
- tool registry registration/dispatch
- coverage summary correctness
- evidence classification correctness
- compliance panorama contract transformation

### Integration test

- ingest tender → requirements structured → ontology tags present
- compliance panorama returns gate/health snapshot
- coverage analyzer aligns with existing requirement summary logic

### Regression test chiave

Verificare che il nuovo layer **non modifichi**:

- workflow tender
- status proposal
- stato gate
- stato review

Il progetto è esplicito sul principio “niente seconda fonte di verità”, quindi questo va testato, non solo dichiarato.

---

## 12. Acceptance criteria

Wave 1 è finita quando:

- almeno l’85% dei requirement estratti riceve un `ontology_domain` valorizzato;
- i 3 tool restituiscono output stabile e testato;
- `CoverageAnalyzer` e `CompliancePanorama` coincidono con i segnali già visibili in observability;
- nessun tool scrive stato operativo;
- il frontend espone i 3 strumenti su un tender reale.

---

## 13. Backlog esecutivo

### Sprint 1A

- creare package `app/intelligence`
- definire schema ontologico
- implementare `TenderOntologyService`
- hook post-extraction
- test unitari mapping

### Sprint 1B

- implementare `TenderToolRegistry`
- implementare `CoverageAnalyzer`
- implementare `EvidenceAuditor`
- API router intelligence
- test integrazione

### Sprint 1C

- implementare `CompliancePanorama`
- collegamento backend → KPI service
- pannello FE minimale
- test end-to-end

---

## Scelta architetturale chiave

La decisione più importante della Wave 1 è questa:

**i tool leggono lo stato canonico, non lo generano.**

Questa disciplina:

- rispetta l’architettura target TenderWriter,
- evita di ereditare il modello fragile di MiroFish basato su polling e stato locale,
- e prepara il terreno alla Wave 2, dove introdurrai l’agente vero.

Il passo successivo più utile è il **design dettagliato della Wave 2**: `TenderIntelligenceAgent`, `GraphPathExplainer`, `ContradictionFinder` e modello di proiezione lifecycle nel grafo.

si

Ora scendo sulla Wave 2: agente, tool avanzati e projection del lifecycle nel grafo. È qui che TenderWriter comincia davvero a ereditare il “cervello” di MiroFish.

Thought for 23s

Perfetto. La **Wave 2** è il punto in cui TenderWriter smette di avere solo “tool utili” e inizia ad avere un vero **strato di intelligence orchestrata**.

In MiroFish il salto avviene quando il ReportAgent non si limita a cercare dati, ma usa strumenti distinti per fare attribution, graph traversal, quick retrieval e interview su individui simulati; inoltre il workflow complessivo è pensato come sequenza `Graph Build → Env Setup → Simulation → Report → Interaction`. In TenderWriter esiste già il terreno per replicare quel salto in modo più robusto: workflow operativi, eventi canonici, entità di review/rework/gate e un motore KPI separato con snapshot, diagnostica, transizioni e forecast.

La Wave 2, quindi, ha quattro deliverable veri:

- `TenderIntelligenceAgent`
- `GraphPathExplainer`
- `ContradictionFinder`
- `GraphLifecycleProjector`

## Obiettivo della Wave 2

Alla fine della Wave 2 il sistema deve saper rispondere a domande del tipo:

- “Perché questo tender è Amber?”
- “Qual è la catena che porta da un requirement fragile a un gate aperto?”
- “Quali promesse della proposta sono in conflitto con requirement o evidence?”
- “Quali eventi operativi hanno creato il rischio attuale?”

Questa direzione è coerente con la UX/semantica già prevista in TenderWriter: drilldown di compliance, timeline delle transizioni, lettura dei bottleneck, diagnostica e forecast, senza introdurre override diretti dello stato analitico.

---

## 1. `TenderIntelligenceAgent`

Questo è il trapianto principale del ReportAgent di MiroFish, ma in versione procurement-native.

### Cosa fa

Non calcola KPI, non aggiorna workflow, non apre gate.  
Legge:

- requirement consolidati e loro stato,
- sezioni proposta,
- `ContributionUnit`,
- `ReviewCycle`,
- `ReworkAction`,
- `ComplianceGate`,
- snapshot/diagnostics/forecast del KPI engine,
- proiezione lifecycle nel grafo.

TenderWriter ha già il modello operativo necessario per questo tipo di lettura: `ContributionUnit` come deliverable logico, `ReviewCycle` come iterazione di review, `ReworkAction` come follow-up strutturato e `ComplianceGate` come checkpoint formale.

### Struttura consigliata

backend/app/intelligence/  
  agent.py  
  prompts.py  
  result_models.py

### Modello di esecuzione

Non farei un ReACT libero e lungo.  
Userei un loop controllato:

1. classify_intent  
2. select_tools(max 3)  
3. run_tools  
4. merge_findings  
5. synthesize_answer  
6. optionally emit recommended_actions (read-only suggestions)

### Intent iniziali

class IntelligenceIntent(str, Enum):  
    COVERAGE_CHECK = "coverage_check"  
    EVIDENCE_AUDIT = "evidence_audit"  
    RISK_EXPLANATION = "risk_explanation"  
    CONTRADICTION_HUNT = "contradiction_hunt"  
    GRAPH_EXPLAIN = "graph_explain"  
    COMPLIANCE_SUMMARY = "compliance_summary"

### Contratto di output

class IntelligenceResponse(BaseModel):  
    intent: IntelligenceIntent  
    tools_used: list[str]  
    answer: str  
    findings: list[dict[str, Any]] = []  
    recommended_actions: list[dict[str, Any]] = []  
    provenance: dict[str, Any] = {}

### Regola chiave

`recommended_actions` non devono mai scrivere direttamente su DB.  
Questo è essenziale perché la documentazione TenderWriter insiste sul fatto che UI e layer analitico non introducano una seconda fonte di verità del workflow.

---

## 2. `GraphPathExplainer`

Questo è il corrispettivo verticale di `InsightForge` e, in parte, di `PanoramaSearch`.

In MiroFish `PanoramaSearch` è descritto come BFS graph-based per ricostruire propagazione/topologia dei flussi, mentre `InsightForge` punta a una forma di deep attribution tra semi di realtà, memoria globale/locale e stato della simulazione. In TenderWriter non devi spiegare “la propagazione narrativa”: devi spiegare la **catena operativa e semantica del rischio**.

### Domande target

- perché questo requirement è classificato come fragile?
- perché il gate automatico è aperto?
- come si arriva da una sezione proposta a un finding di compliance?
- quale review/rework ha impattato questo contribution unit?

### Fonte dati

Il tool deve comporre:

- requirement SQL/consolidati,
- relazioni requirement graph,
- mappature sezione↔requirement,
- gate automatico,
- stati operativi di contribution/review/rework,
- eventi canonici proiettati sul grafo.

Il lato FE già possiede una semantica minima di requirement summary (`fullyAddressed`, `partiallyAddressed`, `notAddressed`, `mapped`, `unmapped`) e la nozione di auto compliance gate “Auto compliance readiness”, con narrativa di blocco. Wave 2 deve portare questa logica sul server e arricchirla con explainability.

### API interna

class GraphExplainRequest(BaseModel):  
    tender_id: int  
    requirement_id: int | None = None  
    proposal_section_id: int | None = None  
    compliance_gate_id: int | None = None  
    max_hops: int = 4

### Output

class GraphExplainResponse(BaseModel):  
    anchor_type: str  
    anchor_id: int | str  
    narrative: str  
    path_nodes: list[dict[str, Any]]  
    path_edges: list[dict[str, Any]]  
    supporting_events: list[dict[str, Any]]

### Query model

Non serve subito una BFS generica “universale”.  
Per Wave 2 conviene una BFS a grafo tipizzato con nodi:

- `Tender`
- `Requirement`
- `ProposalSection`
- `ContributionUnit`
- `ReviewCycle`
- `ReworkAction`
- `ComplianceGate`
- `RequirementEvent`

e archi mirati:

- `HAS_REQUIREMENT`
- `ADDRESSED_BY_SECTION`
- `BACKED_BY_CONTRIBUTION`
- `REVIEWED_IN`
- `TRIGGERED_REWORK`
- `BLOCKED_BY_GATE`
- `HAS_LIFECYCLE_EVENT`

---

## 3. `ContradictionFinder`

Questo tool non esiste così in MiroFish, ma è una derivazione naturale del suo pattern multi-tool: usare retrieval + graph + interview/reasoning per rilevare incoerenze.

### Cosa deve trovare

Tre famiglie di conflitto:

**A. Conflitto requirement ↔ proposta**  
La proposta promette qualcosa che il requirement non supporta o addirittura contraddice.

**B. Conflitto proposta ↔ evidence**  
La sezione dichiara una capability, ma non c’è prova coerente del tipo atteso.

**C. Conflitto requirement ↔ requirement**  
Due requirement consolidati o relazioni materializzate puntano in direzioni incompatibili.

TenderWriter ha già requirement, relation graph foundation, gold-set/export/evaluation e backfill di requirement graph: quindi il posto giusto per introdurre questo tool è sopra quella base, non come pura NLP stateless.

### Design file

backend/app/intelligence/tools/contradiction_finder.py

### Richiesta

class ContradictionFinderRequest(BaseModel):  
    tender_id: int  
    proposal_id: int | None = None  
    section_ids: list[int] = []  
    include_requirement_requirement_conflicts: bool = True

### Risposta

class ContradictionFinding(BaseModel):  
    contradiction_type: Literal[  
        "requirement_vs_proposal",  
        "proposal_vs_evidence",  
        "requirement_vs_requirement",  
    ]  
    severity: Literal["high", "medium", "low"]  
    summary: str  
    source_refs: list[str]  
    involved_entities: list[dict[str, Any]]

### Strategia Wave 2

Farei motore ibrido in 3 passaggi:

1. **pre-filter strutturato**  
    seleziona solo requirement high/mandatory, sezioni mappate, evidence deboli o mancanti;
2. **candidate generation**  
    usa overlap lessicale + relation graph + ontology domain;
3. **verifica LLM mirata**  
    solo sui candidati ad alta probabilità.

Così eviti costi eccessivi e falsi positivi rumorosi.

---

## 4. `GraphLifecycleProjector`

Questa è la parte più strategica della Wave 2.

TenderWriter ha già un catalogo di eventi canonici molto ricco, tra cui:  
`tender_document_ingested`, `requirements_extracted`, `proposal_section_updated`, `contribution_request_created`, `contribution_received`, `contribution_review_completed`, `rework_requested`, `rework_resolved`, `compliance_gate_opened`, `compliance_gate_passed`, `compliance_gate_failed`, `sla_breached`. Inoltre il motore KPI è esplicitamente pensato per ingestione eventi, replay/backfill e query read-only di snapshot/diagnostics/transitions/forecast.

In MiroFish il valore della memoria sta nel fatto che il grafo viene aggiornato “in real time” e che ReportAgent e UI leggono memoria attiva/storica. In TenderWriter non conviene inventare un secondo memory system: conviene **proiettare gli eventi canonici nel grafo requirement**.

### Design consigliato

Sul nodo `Requirement` metti solo snapshot sintetico:

{  
  "current_status": "partially_addressed",  
  "coverage_status": "partial",  
  "risk_level": "amber",  
  "gate_state": "open",  
  "last_event_type": "rework_requested",  
  "last_event_at": "2026-04-17T12:45:00Z"  
}

Il dettaglio storico lo metti in nodi evento:

(:Requirement)-[:HAS_LIFECYCLE_EVENT]->(:RequirementEvent)

### RequirementEvent

class RequirementEventProjection(BaseModel):  
    external_event_id: str  
    tender_id: int  
    requirement_id: int  
    event_type: str  
    occurred_at: datetime  
    payload_json: dict[str, Any]  
    actor_id: int | None = None

### Perché questa scelta è migliore di un array JSON

- è queryable in Neo4j;
- supporta path explain;
- allinea il grafo al modello di replay/backfill già caro al KPI engine;
- evita di perdere granularità storica.

### Sorgenti per la proiezione

Le due fonti principali sono:

- eventi outbox backend;
- eventi/workflow locali generati dalle transizioni sezione→contribution→review→rework.

Il codice operativo mostra chiaramente che approvazione review, richiesta modifiche e rework risolto sono già modellati come eventi distinti durante la sync del workflow sezioni/contribution.

---

## 5. Integrazione con Neo4j

TenderWriter ha già sync requirement→graph e Neo4j è già presente/attivo nel runtime. La funzione `sync_tender_requirements_to_graph` esiste già per rispecchiare requirement SQL in nodi `Requirement` Neo4j. Wave 2 deve estenderla, non bypassarla.

### Nuove responsabilità del grafo

- upsert snapshot requirement enrichito
- upsert relazioni requirement→section / requirement→gate / requirement→contribution dove disponibili
- append requirement lifecycle events
- supporto a explain path queries

### Nuovo modulo consigliato

backend/app/intelligence/lifecycle_projector.py

### Metodi chiave

async def project_requirement_event(...)  
async def refresh_requirement_snapshot(...)  
async def explain_requirement_path(...)

---

## 6. API Wave 2

Aggiungerei questi endpoint:

POST /api/intelligence/query  
POST /api/intelligence/tools/graph-path-explainer  
POST /api/intelligence/tools/contradiction-finder  
GET  /api/intelligence/tenders/{tender_id}/lifecycle-summary

### `POST /api/intelligence/query`

Questo è il primo endpoint “agentico”.

Input:

{  
  "tender_id": 123,  
  "question": "Perché il tender è ancora amber?",  
  "context": {  
    "proposal_id": 77  
  }  
}

Output:

{  
  "intent": "risk_explanation",  
  "tools_used": ["compliance_panorama", "graph_path_explainer"],  
  "answer": "...",  
  "findings": [...],  
  "recommended_actions": [...],  
  "provenance": {...}  
}

### Regola importante

L’agent endpoint deve restare **read-only**.  
Al massimo produce `recommended_actions`, non `executed_actions`.

---

## 7. Logging e audit

Il nuovo layer deve essere osservabile.  
MiroFish ha molta ricchezza funzionale, ma meno robustezza architetturale; TenderWriter deve fare il contrario: importare la ricchezza, mantenendo audit e controllo.

Creerei una tabella o store minimo:

class IntelligenceAgentRun(BaseModel):  
    run_id: str  
    tender_id: int  
    question: str  
    intent: str  
    tools_used: list[str]  
    started_at: datetime  
    completed_at: datetime | None  
    status: str  
    result_summary: str | None

E, opzionalmente, `IntelligenceToolCallLog`.

Questo serve a:

- audit funzionale,
- debugging,
- controllo costo/latency,
- evaluation futura.

---

## 8. Frontend Wave 2

Wave 1 aveva bottoni tool.  
Wave 2 aggiunge due capacità:

**A. Ask Tender Intelligence**  
Una casella domanda libera che chiama `/api/intelligence/query`.

**B. Explain This Risk**  
Da snapshot/diagnostics/timeline puoi cliccare un finding o un gate e lanciare `GraphPathExplainer`.

Questa UX è molto vicina al valore di MiroFish step 5, ma senza copiare la semantica “chatta con individui simulati”; prima porti la conversazione col sistema reale.

---

## 9. Testing Wave 2

### Unit

- intent classifier routing
- tool selection limits
- graph path assembly
- contradiction candidate generation
- event projection normalization

### Integration

- requirement updated → event projected → graph snapshot refreshed
- intelligence query “why amber” → usa `compliance_panorama` + `graph_path_explainer`
- contradiction finder rileva mismatch proposal/evidence in fixture controllata

### Acceptance tests

Tre scenari minimi:

**Scenario 1**  
Tender con auto compliance gate aperto e requirement non coperti.  
L’agent deve spiegare il rischio e indicare almeno una azione consigliata coerente.

**Scenario 2**  
Tender con review chiusa male e rework aperto.  
Il grafo deve mostrare `last_event_type = rework_requested` e path explain deve includere review→rework.

**Scenario 3**  
Tender con sezione proposta che afferma una capability senza evidence coerente.  
`ContradictionFinder` deve restituire almeno un finding `proposal_vs_evidence`.

---

## 10. Backlog esecutivo Wave 2

### Sprint 2A

- creare `agent.py`
- introdurre `POST /api/intelligence/query`
- integrare tool Wave 1 nel router agentico
- logging base runs

### Sprint 2B

- implementare `GraphPathExplainer`
- aggiungere endpoint dedicato
- query Cypher per chain minima

### Sprint 2C

- implementare `GraphLifecycleProjector`
- collegare catalogo eventi canonici
- refresh snapshot requirement nel grafo

### Sprint 2D

- implementare `ContradictionFinder`
- FE “Explain this risk”
- test end-to-end completi

---

## Decisione architetturale più importante della Wave 2

È questa:

**il lifecycle non vive in un nuovo motore di memoria; vive come proiezione leggibile del dominio operativo esistente.**

Questo è il punto dove TenderWriter supera davvero MiroFish:

- prende il meglio della memoria dinamica e del reasoning tool-driven,
- ma lo appoggia su eventi canonici, replay, backfill, snapshot e forecast già previsti dal KPI reason engine.

Il prossimo passo naturale è la **Wave 3 dettagliata**: `ReviewerPersonaService`, `TenderRehearsalService`, modello `RehearsalReport`, integrazione con `forecast` e collegamento a `ReworkAction`.

si

Cerco adesso i punti più utili per la Wave 3: dove MiroFish modella personas/simulazione/report e dove TenderWriter modella review, rework, forecast e compliance, così il design resta ancorato al codice reale.

Thought for 53s

Perfetto. La **Wave 3** è quella che porta davvero in TenderWriter la parte più distintiva di MiroFish: non più solo tool e explainability, ma **rehearsal predittivo**.

MiroFish si definisce esplicitamente un “rehearsal laboratory for decision-makers”, organizza il workflow in 5 fasi, genera personas nella fase di environment setup e usa anche interviste batch agli agenti per raccogliere punti di vista multipli.  
TenderWriter, dal canto suo, ha già il dominio giusto per assorbire questa idea in modo molto più robusto: workflow review/rework/gate esplicito, forecast con scenari `submit_on_time`, `extended_rework`, `pause_or_stop`, e principio forte di UI osservativa senza override diretto dello stato analitico.

Quindi la Wave 3 deve fare una cosa sola, ma molto bene:

**simulare in anticipo come verrà giudicata la proposta, usando reviewer sintetici coerenti col dominio gara e integrando i risultati nel loop reale di review/rework/forecast.**

---

# Obiettivo della Wave 3

Alla fine della Wave 3 TenderWriter deve poter fare questo:

- selezionare o generare 4–6 reviewer personas;
- far valutare a ciascuna persona una proposta o singole sezioni;
- produrre un `RehearsalReport` con score, obiezioni, gap e rischi;
- tradurre i finding in `recommended_reworks`;
- arricchire il forecast e la lettura del tender senza mai mutare direttamente lo stato operativo.

Questa scelta è coerente con MiroFish, che usa personas/agent profiles e interview multi-agent, ma è anche coerente con TenderWriter, dove review e rework sono già oggetti formali del dominio e non semplici annotazioni.

---

# 1) `ReviewerPersonaService`

Questa è la controparte TenderWriter dell’`OasisAgentProfile`.

In MiroFish il profilo agente contiene campi come `user_id`, `user_name`, `name`, `bio`, `persona`, oltre a attributi opzionali come `profession`, `interested_topics`, `source_entity_uuid`, `source_entity_type`. Questo è ottimo come ispirazione, ma in TenderWriter non serve una persona “socialmente realistica”: serve una persona **decisionalmente utile**.

## Design consigliato

class ReviewerPersona(BaseModel):  
    persona_id: str  
    display_name: str  
    reviewer_type: Literal[  
        "formalista_amministrativo",  
        "valutatore_tecnico",  
        "compliance_officer",  
        "economico_finanziario",  
        "rup_simulato",  
        "delivery_manager_critico",  
    ]  
    focus_domains: list[str]  
    strictness: int  # 1..5  
    risk_aversion: int  # 1..5  
    scoring_weights: dict[str, float]  
    mandatory_checks: list[str]  
    prompt_profile: str  
    source_hint: dict[str, Any] = {}  
    version: str = "tw-reviewer-v1"

## Personas iniziali

Io partirei con 5:

- `formalista_amministrativo`
- `valutatore_tecnico`
- `compliance_officer`
- `economico_finanziario`
- `rup_simulato`

Non partirei con generazione LLM pura.  
Farei prima un catalogo deterministico versionato, eventualmente arricchito con hint derivati dal tender:

- categoria merceologica,
- presenza di SLA,
- peso dei criteri tecnici,
- natura dei requirement mandatory/scored,
- evidenze richieste.

## Sede del codice

backend/app/intelligence/personas.py  
backend/app/intelligence/persona_catalog.py

---

# 2) `TenderRehearsalService`

Questo è il cuore della Wave 3.

In MiroFish il valore del sistema è proprio il “what if”: creare un mondo simulato, far interagire agenti e poi interrogare il risultato con ReportAgent e InterviewAgents. In TenderWriter il “mondo” non è un social graph, ma un tender reale con requirements, sezioni, contribution, review, rework e gate.

## Compito del servizio

Dato un `tender_id` e una proposta o snapshot di proposta:

1. carica il contesto rilevante;
2. seleziona i reviewer;
3. fa valutare il materiale a ciascun reviewer;
4. aggrega i risultati;
5. produce un report di rehearsal;
6. propone rework.

## File

backend/app/intelligence/rehearsal.py  
backend/app/intelligence/rehearsal_runner.py  
backend/app/intelligence/rehearsal_prompts.py

## Input

class RehearsalRequest(BaseModel):  
    tender_id: int  
    proposal_id: int  
    proposal_section_ids: list[int] = []  
    persona_ids: list[str] = []  
    mode: Literal["full", "section", "pre_gate"] = "full"  
    include_forecast_context: bool = True

## Output

class RehearsalReport(BaseModel):  
    rehearsal_id: str  
    tender_id: int  
    proposal_id: int  
    mode: str  
    overall_score: float  
    health_projection: Literal["green", "amber", "red"]  
    persona_scores: list[dict[str, Any]]  
    section_findings: list[dict[str, Any]]  
    requirement_gaps: list[dict[str, Any]]  
    contradiction_findings: list[dict[str, Any]]  
    evidence_findings: list[dict[str, Any]]  
    recommended_reworks: list[dict[str, Any]]  
    generated_at: datetime  
    version: str = "tw-rehearsal-v1"

---

# 3) Pipeline del rehearsal

La pipeline migliore è questa:

load tender context  
→ load ontology + requirements + proposal sections  
→ load operational context (review, rework, gates, KPI snapshot, forecast)  
→ select personas  
→ persona evaluation loop  
→ aggregate findings  
→ derive recommended_reworks  
→ persist report  
→ optionally enrich forecast view

## Contesto da leggere

Il rehearsal deve leggere almeno:

- requirement consolidati e loro coverage;
- sezioni proposta;
- `ContributionUnit` e `ReviewCycle`;
- rework aperti/risolti;
- gate aperti/falliti;
- KPI snapshot / diagnostics / forecast.

Questo si sposa con il modello TenderWriter dove:

- la review approvata/changes requested è distinta,
- il loop `S5 -> S6` è esplicito,
- il gate automatico è parte dell’osservabilità reale,
- il forecast è già una capability di primo livello.

---

# 4) Persona evaluation loop

Non farei un agent swarm.  
Farei un loop semplice e controllato:

for persona in personas:  
    build persona-specific context  
    run focused evaluation  
    collect:  
      - score  
      - objections  
      - requirement gaps  
      - weak evidence  
      - contradictions  
      - questions to ask before submission

## Regole di valutazione

### Formalista amministrativo

Pesa di più:

- mandatory coverage
- allegati / evidenze
- coerenza formale
- assenza di omissioni

### Valutatore tecnico

Pesa di più:

- solidità soluzione
- chiarezza architetturale
- SLA / continuità operativa
- supporto probatorio tecnico

### Compliance officer

Pesa di più:

- certificazioni
- obblighi normativi
- contraddizioni con requirement/gate

### Economico-finanziario

Pesa di più:

- sostenibilità della proposta
- elementi economici/garanzie
- rischio di claims non sostenibili

### RUP simulato

Pesa di più:

- readiness complessiva
- punti di blocco
- affidabilità generale del pacchetto

---

# 5) Come usare i tool delle Wave 1 e 2 dentro il rehearsal

Il rehearsal non deve inventare i finding da zero.

Ogni reviewer deve usare gli strumenti già introdotti:

- `CoverageAnalyzer`
- `EvidenceAuditor`
- `CompliancePanorama`
- `GraphPathExplainer`
- `ContradictionFinder`

Questo è esattamente il punto in cui il design diventa elegante:  
la Wave 3 non crea un nuovo motore isolato, ma **orchestra** le capability già costruite in Wave 1 e 2.

## Strategia consigliata

Per ogni reviewer:

1. filtra requirement e sezioni in base a `focus_domains`;
2. richiama i tool già disponibili;
3. usa LLM solo per:
    - scoring finale,
    - formulazione obiezioni,
    - spiegazione sintetica.

Così il rehearsal resta grounded e non puramente generativo.

---

# 6) `recommended_reworks`

Questo è il punto di contatto con il workflow reale.

TenderWriter modella già `ReworkAction` come entità esplicita, anche blocking, con severity e loop chiaro verso review. Inoltre il flusso operativo genera `rework_requested` e `rework_resolved` in modo formalizzato.

La Wave 3 deve quindi produrre:

class RecommendedRework(BaseModel):  
    scope_type: Literal["proposal_section", "requirement", "evidence", "gate"]  
    scope_id: int | str  
    severity: Literal["high", "medium", "low"]  
    blocking: bool  
    rationale: str  
    suggested_owner_role: str | None = None  
    source_persona_id: str

## Regola fondamentale

Questi sono **suggerimenti**.  
Non vanno tradotti automaticamente in `ReworkAction` persistenti senza conferma.

Questo è perfettamente coerente con la filosofia TenderWriter:

- osservabilità forte,
- admin cockpit reale,
- niente override analitico diretto.

---

# 7) Integrazione con forecast

Questo è il punto più interessante dal punto di vista predittivo.

TenderWriter ha già forecast progressivo e scenari:

- `submit_on_time`
- `extended_rework`
- `pause_or_stop`

La Wave 3 non deve sostituire il forecast KPI.  
Deve **arricchirlo** con un blocco rehearsal.

## Proposta di contratto

Nel payload del forecast aggiungerei:

{  
  "rehearsal_summary": {  
    "last_rehearsal_at": "2026-04-17T18:40:00Z",  
    "overall_score": 71,  
    "persona_divergence": 0.28,  
    "blocking_findings": 3,  
    "high_severity_rework_suggestions": 2,  
    "health_projection": "amber"  
  }  
}

## Uso nel motore

Il KPI engine non deve cambiare formula di base subito.  
In prima iterazione, il rehearsal deve entrare come:

- segnale accessorio nel dashboard,
- spiegazione aggiuntiva del forecast,
- opzionale fattore correttivo low-weight.

Per esempio:

- molte obiezioni ad alta severità → aumenta peso di `extended_rework`
- reviewer molto divergenti → segnala instabilità del draft

---

# 8) Persistenza Wave 3

Aggiungerei due nuove tabelle:

### `rehearsal_runs`

- `id`
- `tender_id`
- `proposal_id`
- `mode`
- `status`
- `requested_by`
- `started_at`
- `completed_at`
- `report_json`
- `version`

### `rehearsal_persona_results`

- `id`
- `rehearsal_run_id`
- `persona_id`
- `score`
- `findings_json`
- `questions_json`

Questo è molto meglio di replicare il modello MiroFish basato su project files, polling e stato su filesystem. MiroFish funziona, ma il suo lato fragile è proprio l’orchestrazione locale.

---

# 9) Esecuzione asincrona

Il rehearsal va eseguito come job asincrono del backend TenderWriter, non come processo separato con IPC file-based.

## Perché

MiroFish usa `SimulationIPCClient` e `SimulationIPCServer` via cartelle `ipc_commands` / `ipc_responses`, con polling ogni 0.5 secondi. Questo è precisamente il pattern da non importare.

## In TenderWriter

Usa Celery / task backend già presenti nel sistema per:

- avviare il rehearsal,
- monitorarne stato,
- leggere il report finale.

API:

POST /api/intelligence/rehearsals  
GET  /api/intelligence/rehearsals/{id}

---

# 10) UI Wave 3

La UI minima deve avere 3 aree:

### A. Pulsante “Simula Commissione”

Posizionato vicino a:

- review readiness
- compliance readiness
- forecast

### B. Rehearsal summary panel

Mostra:

- overall score
- score per reviewer
- top objections
- blocking suggestions

### C. Suggested reworks

Lista actionable:

- scope
- severity
- blocking
- rationale
- reviewer origine

E, opzionalmente:

- “crea rework” come azione manuale confermata.

Questa UX è coerente con il cockpit admin e con la timeline/summary panel che già è parte della visione osservativa-operativa di TenderWriter.

---

# 11) Testing Wave 3

## Unit

- persona catalog loading
- score aggregation
- rework recommendation synthesis
- forecast enrichment mapping

## Integration

- rehearsal run su tender con gate aperto
- persona technical reviewer trova gap SLA
- persona compliance reviewer trova evidence mancante
- report contiene recommended reworks coerenti

## Acceptance scenarios

### Scenario R1

Proposal quasi pronta ma con 2 requirement high uncovered.  
Atteso:

- score medio basso/moderato
- reviewer formalista segnala missing mandatory coverage
- `recommended_reworks` include almeno un fix blocking

### Scenario R2

Proposal forte tecnicamente ma debole lato evidence/compliance.  
Atteso:

- valutatore tecnico score alto
- compliance officer score basso
- alta `persona_divergence`

### Scenario R3

Tender già in loop rework.  
Atteso:

- rehearsal aumenta probabilità `extended_rework`
- il report non scrive rework automatici
- l’admin può convertirli manualmente

---

# 12) Backlog esecutivo Wave 3

### Sprint 3A

- `ReviewerPersonaService`
- catalogo reviewer v1
- prompt templates persona-specifici

### Sprint 3B

- `TenderRehearsalService`
- orchestrazione per persona
- `RehearsalReport`

### Sprint 3C

- persistenza `rehearsal_runs`
- endpoint create/status
- FE “Simula Commissione”

### Sprint 3D

- integrazione con forecast
- mapping `recommended_reworks`
- test end-to-end

---

# Decisione architetturale più importante della Wave 3

È questa:

**il rehearsal deve produrre pressione decisionale, non mutazione automatica del workflow.**

Quindi:

- può spiegare,
- può suggerire,
- può segnalare rischio,
- può proporre rework,

ma non deve:

- aprire automaticamente gate,
- chiudere review,
- creare rework persistenti senza conferma,
- alterare lo stato forecast come fonte primaria.

Questo conserva il principio più sano già esplicito in TenderWriter: il sistema deve restare auditabile e coerente coi fatti operativi, non con decisioni opache di un layer agentico.

## Sintesi finale

La Wave 3 è il momento in cui TenderWriter importa davvero “l’anima” di MiroFish:

- personas,
- multi-view evaluation,
- zero-risk rehearsal,
- pre-judgment simulation.

Ma lo fa in modo migliore di MiroFish perché:

- usa workflow enterprise già modellato,
- usa forecast e KPI già presenti,
- evita IPC file-based,
- evita stato duplicato,
- integra review e rework in modo governato.

Il passo successivo più utile è uno di questi due:  
**A)** schema SQLAlchemy/FastAPI completo per `rehearsal_runs`, `rehearsal_persona_results`, endpoint e payload  
oppure **B)** backlog finale unificato Wave 1+2+3 con dipendenze, rischi e ordine di rollout.

a e b in sequenza

Raccolgo ora i riferimenti precisi per fissare schema, endpoint e rollout sulla base del codice reale: modelli review/rework/gate/forecast di TenderWriter e profili/simulazione/report di MiroFish.

Thought for 58s

Perfetto. Vado in sequenza.

# A) Schema completo Wave 3: SQLAlchemy, FastAPI, task e payload

La proposta qui sotto assume due vincoli architetturali che i sorgenti rendono molto chiari: in MiroFish le personas e il rehearsal sono concetti centrali del workflow, ma l’orchestrazione usa stato progetto locale e IPC su filesystem; in TenderWriter, invece, workflow, eventi, review/rework/gate e forecast sono già entità canoniche e il layer analitico deve restare osservativo, senza diventare una seconda fonte di verità.

## 1. Nuove tabelle SQLAlchemy

File consigliato: `backend/app/models/rehearsal.py`

### Enum

from __future__ import annotations  
  
import enum  
from sqlalchemy import (  
    Column, Integer, String, DateTime, ForeignKey, Float, Text, Enum, Boolean, func  
)  
from sqlalchemy.dialects.postgresql import JSONB  
from sqlalchemy.orm import relationship  
  
from app.db.database import Base  
  
  
class RehearsalRunStatus(str, enum.Enum):  
    PENDING = "pending"  
    RUNNING = "running"  
    COMPLETED = "completed"  
    FAILED = "failed"  
    CANCELLED = "cancelled"  
  
  
class RehearsalMode(str, enum.Enum):  
    FULL = "full"  
    SECTION = "section"  
    PRE_GATE = "pre_gate"  
  
  
class RehearsalRecommendationStatus(str, enum.Enum):  
    PROPOSED = "proposed"  
    ACCEPTED = "accepted"  
    DISMISSED = "dismissed"

### `RehearsalRun`

class RehearsalRun(Base):  
    __tablename__ = "rehearsal_runs"  
  
    id = Column(Integer, primary_key=True, index=True)  
    tender_id = Column(Integer, ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True)  
    proposal_id = Column(Integer, ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, index=True)  
  
    mode = Column(Enum(RehearsalMode), nullable=False, default=RehearsalMode.FULL, index=True)  
    status = Column(Enum(RehearsalRunStatus), nullable=False, default=RehearsalRunStatus.PENDING, index=True)  
  
    requested_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  
    started_at = Column(DateTime(timezone=True), nullable=True)  
    completed_at = Column(DateTime(timezone=True), nullable=True)  
  
    overall_score = Column(Float, nullable=True)  
    health_projection = Column(String(20), nullable=True)  # green/amber/red  
    persona_divergence = Column(Float, nullable=True)  
  
    context_snapshot_json = Column(JSONB, nullable=False, default=dict)  
    report_json = Column(JSONB, nullable=True)  
    error_message = Column(Text, nullable=True)  
  
    version = Column(String(40), nullable=False, default="tw-rehearsal-v1")  
    created_at = Column(DateTime(timezone=True), server_default=func.now())  
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())  
  
    tender = relationship("Tender")  
    proposal = relationship("Proposal")  
    requested_by_user = relationship("User", foreign_keys=[requested_by])

### `RehearsalPersonaResult`

class RehearsalPersonaResult(Base):  
    __tablename__ = "rehearsal_persona_results"  
  
    id = Column(Integer, primary_key=True, index=True)  
    rehearsal_run_id = Column(Integer, ForeignKey("rehearsal_runs.id", ondelete="CASCADE"), nullable=False, index=True)  
  
    persona_id = Column(String(80), nullable=False, index=True)  
    display_name = Column(String(120), nullable=False)  
    reviewer_type = Column(String(80), nullable=False)  
  
    score = Column(Float, nullable=True)  
    blocking_findings_count = Column(Integer, nullable=False, default=0)  
    high_severity_findings_count = Column(Integer, nullable=False, default=0)  
  
    findings_json = Column(JSONB, nullable=False, default=list)  
    questions_json = Column(JSONB, nullable=False, default=list)  
    metrics_json = Column(JSONB, nullable=False, default=dict)  
  
    created_at = Column(DateTime(timezone=True), server_default=func.now())  
  
    rehearsal_run = relationship("RehearsalRun")

### `RehearsalRecommendation`

class RehearsalRecommendation(Base):  
    __tablename__ = "rehearsal_recommendations"  
  
    id = Column(Integer, primary_key=True, index=True)  
    rehearsal_run_id = Column(Integer, ForeignKey("rehearsal_runs.id", ondelete="CASCADE"), nullable=False, index=True)  
  
    scope_type = Column(String(40), nullable=False)   # proposal_section, requirement, evidence, gate  
    scope_id = Column(String(80), nullable=False)  
    severity = Column(String(20), nullable=False, default="medium")  
    is_blocking = Column(Boolean, nullable=False, default=False)  
  
    rationale = Column(Text, nullable=False)  
    suggested_owner_role = Column(String(80), nullable=True)  
    source_persona_id = Column(String(80), nullable=False)  
  
    status = Column(  
        Enum(RehearsalRecommendationStatus),  
        nullable=False,  
        default=RehearsalRecommendationStatus.PROPOSED,  
        index=True,  
    )  
  
    linked_rework_action_id = Column(  
        Integer,  
        ForeignKey("rework_actions.id", ondelete="SET NULL"),  
        nullable=True,  
    )  
  
    created_at = Column(DateTime(timezone=True), server_default=func.now())  
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())  
  
    rehearsal_run = relationship("RehearsalRun")  
    linked_rework_action = relationship("ReworkAction")

Queste tabelle sono coerenti con il dominio operativo reale di TenderWriter, che già modella `ContributionUnit`, `ReviewCycle`, `ReworkAction` e `ComplianceGate`, e con l’idea che il rehearsal debba proporre pressione decisionale senza mutare automaticamente il workflow.

## 2. Migrazione Alembic

Nome suggerito:  
`backend/migrations/versions/20260417_0011_add_rehearsal_tables.py`

Operazioni:

- create `rehearsal_runs`
- create `rehearsal_persona_results`
- create `rehearsal_recommendations`
- indici:
    - `(tender_id, created_at desc)` su `rehearsal_runs`
    - `(proposal_id, created_at desc)` su `rehearsal_runs`
    - `(rehearsal_run_id, persona_id)` su `rehearsal_persona_results`
    - `(rehearsal_run_id, status)` su `rehearsal_recommendations`

Non creerei ancora una tabella `reviewer_personas`: nella prima iterazione il catalogo può vivere in codice versionato. È più coerente con la richiesta di partire con personas deterministiche e con il modello MiroFish, dove i profili esistono come artefatti generati/serializzati, non come master data SQL centrale.

## 3. Pydantic / contratti API

File: `backend/app/intelligence/schemas.py`

from __future__ import annotations  
from datetime import datetime  
from pydantic import BaseModel, Field  
from typing import Any, Literal  
  
  
class RehearsalCreateRequest(BaseModel):  
    tender_id: int  
    proposal_id: int  
    proposal_section_ids: list[int] = Field(default_factory=list)  
    persona_ids: list[str] = Field(default_factory=list)  
    mode: Literal["full", "section", "pre_gate"] = "full"  
    include_forecast_context: bool = True  
  
  
class PersonaFinding(BaseModel):  
    category: Literal[  
        "coverage_gap",  
        "weak_evidence",  
        "contradiction",  
        "clarity_issue",  
        "compliance_risk",  
        "delivery_risk",  
    ]  
    severity: Literal["high", "medium", "low"]  
    summary: str  
    scope_type: Literal["proposal_section", "requirement", "evidence", "gate"]  
    scope_id: str  
    supporting_refs: list[str] = Field(default_factory=list)  
  
  
class PersonaQuestion(BaseModel):  
    question: str  
    rationale: str | None = None  
  
  
class PersonaEvaluationResponse(BaseModel):  
    persona_id: str  
    display_name: str  
    reviewer_type: str  
    score: float  
    findings: list[PersonaFinding] = Field(default_factory=list)  
    questions: list[PersonaQuestion] = Field(default_factory=list)  
    metrics: dict[str, Any] = Field(default_factory=dict)  
  
  
class RehearsalRecommendationResponse(BaseModel):  
    id: int | None = None  
    scope_type: str  
    scope_id: str  
    severity: str  
    is_blocking: bool  
    rationale: str  
    suggested_owner_role: str | None = None  
    source_persona_id: str  
    status: str = "proposed"  
    linked_rework_action_id: int | None = None  
  
  
class RehearsalRunResponse(BaseModel):  
    id: int  
    tender_id: int  
    proposal_id: int  
    mode: str  
    status: str  
    overall_score: float | None = None  
    health_projection: str | None = None  
    persona_divergence: float | None = None  
    started_at: datetime | None = None  
    completed_at: datetime | None = None  
    report_json: dict[str, Any] | None = None  
    error_message: str | None = None  
    version: str

## 4. Catalogo personas

File: `backend/app/intelligence/personas.py`

from __future__ import annotations  
from dataclasses import dataclass, field  
  
@dataclass(frozen=True)  
class ReviewerPersona:  
    persona_id: str  
    display_name: str  
    reviewer_type: str  
    focus_domains: list[str]  
    strictness: int  
    risk_aversion: int  
    scoring_weights: dict[str, float]  
    mandatory_checks: list[str] = field(default_factory=list)  
    prompt_profile: str = ""  
    version: str = "tw-reviewer-v1"

Catalogo v1:

PERSONA_CATALOG: dict[str, ReviewerPersona] = {  
    "formalista_amministrativo": ReviewerPersona(  
        persona_id="formalista_amministrativo",  
        display_name="Formalista amministrativo",  
        reviewer_type="formalista_amministrativo",  
        focus_domains=["amministrativo", "documentale", "compliance"],  
        strictness=5,  
        risk_aversion=5,  
        scoring_weights={  
            "mandatory_coverage": 0.35,  
            "evidence_depth": 0.30,  
            "formal_consistency": 0.25,  
            "innovation": 0.10,  
        },  
        mandatory_checks=[  
            "signed_annexes",  
            "required_certifications",  
            "no_missing_documents",  
        ],  
        prompt_profile="Valuta come un commissario formalista..."  
    ),  
    "valutatore_tecnico": ReviewerPersona(  
        persona_id="valutatore_tecnico",  
        display_name="Valutatore tecnico",  
        reviewer_type="valutatore_tecnico",  
        focus_domains=["tecnico", "sla", "organizzativo"],  
        strictness=4,  
        risk_aversion=3,  
        scoring_weights={  
            "technical_strength": 0.35,  
            "service_levels": 0.25,  
            "delivery_feasibility": 0.25,  
            "evidence_depth": 0.15,  
        },  
        prompt_profile="Valuta come un reviewer tecnico..."  
    ),  
    # compliance_officer, economico_finanziario, rup_simulato...  
}

Questo approccio prende da MiroFish il concetto di persona/profilo, ma evita di copiare direttamente un profilo OASIS nato per un mondo simulato social. In MiroFish i profili includono campi come `bio`, `persona`, `profession`, `interested_topics`, `source_entity_uuid` e `source_entity_type`; in TenderWriter è più utile un profilo focalizzato su pesi decisionali e controlli obbligatori.

## 5. Servizio rehearsal

File: `backend/app/intelligence/rehearsal.py`

from __future__ import annotations  
from statistics import mean, pstdev  
from typing import Any  
  
class TenderRehearsalService:  
    def __init__(self, tool_registry, intelligence_agent, kpi_client):  
        self.tool_registry = tool_registry  
        self.intelligence_agent = intelligence_agent  
        self.kpi_client = kpi_client  
  
    async def run_rehearsal(  
        self,  
        db,  
        *,  
        tender_id: int,  
        proposal_id: int,  
        proposal_section_ids: list[int],  
        personas: list,  
        mode: str,  
        include_forecast_context: bool,  
    ) -> dict[str, Any]:  
        context = await self._load_context(  
            db,  
            tender_id=tender_id,  
            proposal_id=proposal_id,  
            proposal_section_ids=proposal_section_ids,  
            include_forecast_context=include_forecast_context,  
        )  
  
        persona_results = []  
        for persona in personas:  
            result = await self._evaluate_with_persona(context=context, persona=persona)  
            persona_results.append(result)  
  
        overall_score = mean([r["score"] for r in persona_results]) if persona_results else 0.0  
        persona_divergence = pstdev([r["score"] for r in persona_results]) if len(persona_results) > 1 else 0.0  
  
        recommended_reworks = self._derive_recommendations(persona_results)  
  
        return {  
            "overall_score": overall_score,  
            "health_projection": self._map_score_to_health(overall_score),  
            "persona_divergence": persona_divergence,  
            "persona_results": persona_results,  
            "recommended_reworks": recommended_reworks,  
            "summary": self._build_summary(persona_results, recommended_reworks),  
        }

### Punto chiave

Dentro `_evaluate_with_persona`, il servizio deve **riusare** i tool delle Wave 1 e 2:

- `coverage_analyzer`
- `evidence_auditor`
- `compliance_panorama`
- `graph_path_explainer`
- `contradiction_finder`

Così il rehearsal non crea verità nuove: orchestra segnali già grounded su requirement, workflow, KPI e grafo. Questo è il modo corretto di importare il pattern MiroFish “multi-agent + rich tools” senza ereditarne la fragilità di orchestrazione locale.

## 6. Celery task

TenderWriter ha già task asincroni e Celery configurato con Redis broker/backend; quindi il rehearsal va eseguito come job backend, non come env simulato separato.

File: `backend/app/tasks.py`

@celery_app.task(name="app.tasks.run_rehearsal_task", bind=True)  
def run_rehearsal_task(self, rehearsal_run_id: int) -> dict:  
    import asyncio  
    return asyncio.run(_run_rehearsal_async(rehearsal_run_id))  
  
  
async def _run_rehearsal_async(rehearsal_run_id: int) -> dict:  
    async with async_session_factory() as db:  
        run = await db.get(RehearsalRun, rehearsal_run_id)  
        if run is None:  
            raise ValueError(f"Rehearsal run {rehearsal_run_id} not found")  
  
        run.status = RehearsalRunStatus.RUNNING  
        run.started_at = datetime.now(timezone.utc)  
        await db.flush()  
  
        try:  
            service = build_tender_rehearsal_service()  
            payload = await service.run_rehearsal(  
                db,  
                tender_id=run.tender_id,  
                proposal_id=run.proposal_id,  
                proposal_section_ids=run.context_snapshot_json.get("proposal_section_ids", []),  
                personas=resolve_personas(run.context_snapshot_json),  
                mode=run.mode.value,  
                include_forecast_context=bool(run.context_snapshot_json.get("include_forecast_context", True)),  
            )  
  
            run.status = RehearsalRunStatus.COMPLETED  
            run.completed_at = datetime.now(timezone.utc)  
            run.overall_score = payload["overall_score"]  
            run.health_projection = payload["health_projection"]  
            run.persona_divergence = payload["persona_divergence"]  
            run.report_json = payload  
  
            # persist persona results + recommendations  
            ...  
            await db.commit()  
            return {"rehearsal_run_id": rehearsal_run_id, "status": "completed"}  
  
        except Exception as exc:  
            run.status = RehearsalRunStatus.FAILED  
            run.completed_at = datetime.now(timezone.utc)  
            run.error_message = str(exc)  
            await db.commit()  
            raise

Questo è esattamente il punto in cui TenderWriter fa meglio di MiroFish: MiroFish usa `SimulationIPCClient` con `ipc_commands`, `ipc_responses` e polling con `poll_interval=0.5`; qui invece sfrutti la coda asincrona già esistente e i modelli transazionali.

## 7. Router FastAPI

File: `backend/app/api/intelligence.py`

from fastapi import APIRouter, Depends, HTTPException, status  
from sqlalchemy.ext.asyncio import AsyncSession  
from app.api.auth import get_current_user, UserResponse  
from app.db.database import get_db  
from app.models import RehearsalRun  
from app.intelligence.schemas import RehearsalCreateRequest, RehearsalRunResponse  
from app.tasks import run_rehearsal_task  
  
router = APIRouter()  
  
@router.post("/rehearsals", response_model=RehearsalRunResponse, status_code=202)  
async def create_rehearsal(  
    request: RehearsalCreateRequest,  
    current_user: UserResponse = Depends(get_current_user),  
    db: AsyncSession = Depends(get_db),  
):  
    run = RehearsalRun(  
        tender_id=request.tender_id,  
        proposal_id=request.proposal_id,  
        mode=request.mode,  
        status="pending",  
        requested_by=current_user.id,  
        context_snapshot_json={  
            "proposal_section_ids": request.proposal_section_ids,  
            "persona_ids": request.persona_ids,  
            "include_forecast_context": request.include_forecast_context,  
        },  
    )  
    db.add(run)  
    await db.flush()  
    await db.refresh(run)  
  
    task = run_rehearsal_task.delay(run.id)  
  
    return RehearsalRunResponse(  
        id=run.id,  
        tender_id=run.tender_id,  
        proposal_id=run.proposal_id,  
        mode=run.mode.value if hasattr(run.mode, "value") else str(run.mode),  
        status=run.status.value if hasattr(run.status, "value") else str(run.status),  
        version=run.version,  
    )  
  
@router.get("/rehearsals/{rehearsal_id}", response_model=RehearsalRunResponse)  
async def get_rehearsal(  
    rehearsal_id: int,  
    current_user: UserResponse = Depends(get_current_user),  
    db: AsyncSession = Depends(get_db),  
):  
    run = await db.get(RehearsalRun, rehearsal_id)  
    if not run:  
        raise HTTPException(status_code=404, detail="Rehearsal not found")  
    return RehearsalRunResponse(  
        id=run.id,  
        tender_id=run.tender_id,  
        proposal_id=run.proposal_id,  
        mode=run.mode.value if hasattr(run.mode, "value") else str(run.mode),  
        status=run.status.value if hasattr(run.status, "value") else str(run.status),  
        overall_score=run.overall_score,  
        health_projection=run.health_projection,  
        persona_divergence=run.persona_divergence,  
        started_at=run.started_at,  
        completed_at=run.completed_at,  
        report_json=run.report_json,  
        error_message=run.error_message,  
        version=run.version,  
    )

### Endpoint aggiuntivo utile

`POST /api/intelligence/rehearsals/{id}/recommendations/{rec_id}/accept`

Questo endpoint, se usato, **non** deve modificare automaticamente review/gate/forecast. Deve solo consentire la conversione manuale di una recommendation in `ReworkAction`, coerentemente con l’architettura osservativa di TenderWriter.

## 8. Mapping manuale recommendation → ReworkAction

Quando un admin decide di accettare una recommendation:

1. legge `RehearsalRecommendation`
2. crea una `ReworkAction`
3. collega `linked_rework_action_id`
4. aggiorna lo stato recommendation da `proposed` a `accepted`

Questo è coerente con il fatto che `ReworkAction` è già un oggetto di dominio con `severity` e `is_blocking`, e che il workflow sezione-driven già apre il rework quando la review non è approvata.

---

# B) Backlog unificato Wave 1 + 2 + 3, con dipendenze, rischi e rollout

La logica complessiva deve seguire la maturità reale dei due progetti: MiroFish è forte su ontologia, personas, report tools e rehearsal, ma fragile su persistenza/orchestrazione; TenderWriter è forte su dominio operativo, eventi, KPI, forecast e workflow review/rework/gate. Il rollout corretto è quindi: **prima enrichment e strumenti grounded, poi agente, poi rehearsal**.

## Wave 1 — Ontology + Tool Foundation

### Deliverable

- `TenderOntologyService`
- `TenderToolRegistry`
- `CoverageAnalyzer`
- `EvidenceAuditor`
- `CompliancePanorama`
- router `/api/intelligence/tools/*`
- FE panel base “Tender Intelligence”

### Dipendenze

- requirement extraction v2
- requirement review/consolidation
- KPI service snapshot/diagnostics/forecast
- mapping requirement↔section già disponibile lato observability

### Rischi

- ontology troppo “accademica” e poco utile
- evidence scoring troppo generico
- duplicazione di logica già presente solo in FE

### Mitigazioni

- ontologia chiusa versionata
- regole deterministiche prima del fallback LLM
- validazione su gold-set requirement/evaluation già esistente

### Exit criteria

- > 85% requirement con tag ontologico
    
- 3 tool stabili su tender reali
- zero scritture di stato operativo

## Wave 2 — Agent + Explainability + Lifecycle Graph

### Deliverable

- `TenderIntelligenceAgent`
- `GraphPathExplainer`
- `ContradictionFinder`
- `GraphLifecycleProjector`
- `/api/intelligence/query`
- FE “Explain this risk”

### Dipendenze

- Wave 1 completata
- Neo4j sync requirement stabile
- catalogo eventi canonici outbox attivo
- accesso KPI engine per forecast/diagnostics

### Rischi

- agente troppo opaco o costoso
- explain path troppo complesso/rumoroso
- contraddiction finder con falsi positivi

### Mitigazioni

- max 3 tool per query
- BFS tipizzata, non generica
- pre-filter strutturato + verifica LLM solo sui candidati forti

### Exit criteria

- risposte “why amber?” grounded
- path explain leggibile
- almeno un finding di contraddizione su fixture reale

## Wave 3 — Personas + Rehearsal + Forecast Enrichment

### Deliverable

- `ReviewerPersonaService`
- `TenderRehearsalService`
- tabelle `rehearsal_runs`, `rehearsal_persona_results`, `rehearsal_recommendations`
- API create/status rehearsal
- FE “Simula Commissione”
- forecast enrichment con `rehearsal_summary`

### Dipendenze

- Wave 1 e 2 complete
- tool grounded già disponibili
- query forecast già stabilizzate
- workflow review/rework/gate già usato da utenti veri

### Rischi

- reviewer troppo generici
- costo LLM alto
- tentazione di auto-mutare workflow

### Mitigazioni

- catalogo personas deterministiche v1
- caching per snapshot/persona
- recommendation solo manualmente convertibili in `ReworkAction`

### Exit criteria

- rehearsal su tender reale con 4–5 reviewer
- score aggregato + divergenza reviewer
- recommendations convertibili manualmente
- nessun auto-update di gate/review/rework

---

## Sequenza di rollout consigliata

### Fase 0 — hardening preparatorio

Prima di Wave 1:

- chiudere allineamento requirement↔proposal section
- controllare qualità API KPI snapshot/forecast
- verificare Neo4j requirement sync

### Fase 1 — internal beta

Abilitare solo per utenti/admin interni:

- ontology tag
- CoverageAnalyzer
- EvidenceAuditor
- CompliancePanorama

### Fase 2 — guided beta

Abilitare:

- `/api/intelligence/query`
- explain risk
- contradiction finder  
    su pochi tender campione

### Fase 3 — controlled rehearsal

Abilitare rehearsal:

- solo su tender “non submitted”
- solo manual trigger
- solo report read-only
- conversione recommendation→rework solo via conferma admin

Questa sequenza segue esattamente il principio TenderWriter “massimizzare utilità senza introdurre una seconda fonte di verità del workflow”, mentre importa da MiroFish il lato più prezioso: rehearsal e multi-view reasoning, ma senza swarm/IPC/social simulation.

## Matrice rischio / impatto

|Blocco|Impatto|Rischio|Priorità|
|---|---|---|---|
|Ontology service|alto|basso|P1|
|Coverage/Evidence/Compliance tools|alto|basso|P1|
|Intelligence agent|molto alto|medio|P1|
|Graph lifecycle projector|molto alto|medio|P1|
|Contradiction finder|alto|medio|P2|
|Reviewer personas v1|alto|basso|P2|
|Rehearsal service|molto alto|medio/alto|P2|
|Forecast enrichment|medio/alto|medio|P3|

## Decisione finale di programma

La sequenza giusta non è “costruire subito la simulazione”, ma:

**1. strumenti grounded**  
**2. agente che li orchestra**  
**3. rehearsal che riusa gli strumenti**  
**4. forecast arricchito dal rehearsal**

Così TenderWriter eredita da MiroFish la parte più forte — ontologia, tool-rich reasoning, personas, rehearsal — ma resta allineato alla sua architettura reale: dominio transazionale nel backend, analytics/forecast nel KPI engine, stato canonico gestito da eventi e workflow, nessuna mutazione opaca lato UI/AI.

Il prossimo passo più utile è trasformare questo in un **piano implementativo file-per-file**, con elenco preciso dei file nuovi/modificati e ordine delle PR.

si

Sto fissando adesso il piano in termini di file reali da toccare e ordine delle PR, così il trasferimento MiroFish → TenderWriter diventa un programma eseguibile e non solo architettura.

Thought for 56s

Perfetto. Ti lascio un **piano file-per-file** e poi l’**ordine delle PR**.

Il criterio guida è semplice: MiroFish va importato per i suoi pattern forti — workflow a fasi, ReportAgent con tool ricchi, personas/rehearsal — ma non per la sua orchestrazione fragile via stato locale e IPC su filesystem. TenderWriter, invece, ha già il dominio operativo giusto: review, rework, gate e forecast con scenari `submit_on_time`, `extended_rework`, `pause_or_stop`.

---

## A. Piano implementativo file-per-file

## PR 1 — Fondazione `intelligence/` + ontologia

### Nuovi file

`backend/app/intelligence/__init__.py`  
Espone il package nuovo.

`backend/app/intelligence/schemas.py`  
Metti qui:

- `RequirementOntologyTag`
- request/response dei tool Wave 1
- enum minimi per domini e criticità

`backend/app/intelligence/ontology.py`  
Contiene `TenderOntologyService`:

- mapping deterministico keyword/rule based
- eventuale fallback LLM in seconda battuta
- funzione `tag_requirement(requirement) -> RequirementOntologyTag`

### File esistenti da modificare

`backend/app/services/requirement_extraction_v2.py`  
Aggiungi il passaggio di enrichment ontologico dopo parsing/verifica, senza cambiare il contratto base della extraction. La extraction v2 esiste già come punto strutturato con schema e candidate normalizzati, quindi è il posto corretto per attaccare l’ontologia.

`backend/app/services/requirement_verification.py` oppure `requirement_review.py`  
Solo se vuoi validare che il tag ontologico venga propagato nei requirement approvati.

`backend/tests/test_requirement_extraction_v2.py`  
Aggiungi casi di tagging ontologico.

`backend/tests/test_requirement_review.py`  
Verifica che il metadata ontologico sopravviva al passaggio di review.

### Nessuna migration in questa PR

Nella prima iterazione salva l’ontologia in `metadata_json` dei requirement, non introdurre ancora colonne dedicate.

---

## PR 2 — Tool registry + tool base

### Nuovi file

`backend/app/intelligence/tool_registry.py`  
Registry semplice dei tool.

`backend/app/intelligence/tools/__init__.py`

`backend/app/intelligence/tools/coverage_analyzer.py`  
Legge requirement + mapping sezione/contribution e restituisce:

- covered
- partial
- uncovered
- high priority uncovered

Questo si appoggia bene alla logica già presente nella workbench/observability che distingue requirement coperti, parziali, non coperti e mappati/non mappati.

`backend/app/intelligence/tools/evidence_auditor.py`  
Legge requirement, evidence allegata e metadata.  
Scopo: classificare `strong / weak / missing`.

`backend/app/intelligence/tools/compliance_panorama.py`  
Fa da adapter verso il KPI reason engine:

- snapshot
- diagnostics
- forecast summary
- gate pressure

### File esistenti da modificare

`backend/app/services/kpi_reason_engine.py`  
Aggiungi helper leggibili dal nuovo layer intelligence, senza spostare la logica KPI qui.

`backend/tests/test_compliance_observability.py`  
Aggiungi test di allineamento tra panorama e stato compliance osservato.

`backend/tests/test_kpi_reason_engine.py`  
Aggiungi test contract lato adapter.

---

## PR 3 — Router API Intelligence Wave 1

### Nuovi file

`backend/app/api/intelligence.py`  
Endpoint:

- `GET /api/intelligence/tools`
- `POST /api/intelligence/tools/coverage-analyzer`
- `POST /api/intelligence/tools/evidence-auditor`
- `POST /api/intelligence/tools/compliance-panorama`

### File esistenti da modificare

`backend/app/main.py`  
Registra il router.

`backend/app/api/__init__.py`  
Se mantieni pattern di export router centralizzato.

`frontend/src/api/client.ts`  
Nuovi client methods:

- `runCoverageAnalyzer`
- `runEvidenceAuditor`
- `runCompliancePanorama`

`frontend/src/features/intelligence/TenderIntelligencePanel.tsx`  
Nuovo pannello minimale.

`frontend/src/router/lazyRoutes.tsx` o pagina contenitore observability  
Aggiungi la route o pannello incorporato.

### Test

`backend/tests/test_main_route_registration.py`  
Verifica router.

`frontend/src/api/client.test.ts`  
Contract FE.

---

## PR 4 — Agent orchestration Wave 2

### Nuovi file

`backend/app/intelligence/agent.py`  
`TenderIntelligenceAgent` con loop controllato:

- classify intent
- select tools
- execute tools
- synthesize answer

`backend/app/intelligence/prompts.py`  
Prompt classifier e synth prompt.

`backend/app/intelligence/result_models.py`  
Response strutturate.

### File esistenti da modificare

`backend/app/intelligence/tool_registry.py`  
Supporto a metadata tool e limiti di esecuzione.

`backend/app/api/intelligence.py`  
Aggiungi:

- `POST /api/intelligence/query`

`frontend/src/features/intelligence/TenderIntelligencePanel.tsx`  
Aggiungi casella domanda libera.

### Test

`backend/tests/test_intelligence_agent.py`  
Nuovo file:

- routing intent
- max 3 tools
- no write side effects

Questa PR è il vero trapianto del pattern ReportAgent tool-driven di MiroFish, ma ancorato a uno strato backend già transazionale. MiroFish espone `InsightForge`, `PanoramaSearch`, `QuickSearch`, `InterviewAgents`; qui tu inizi con una versione tender-native e controllata.

---

## PR 5 — Graph explain + contradiction finder

### Nuovi file

`backend/app/intelligence/tools/graph_path_explainer.py`  
Tool explain path:

- requirement → section → contribution → review/rework/gate

`backend/app/intelligence/tools/contradiction_finder.py`  
Rileva:

- requirement vs proposal
- proposal vs evidence
- requirement vs requirement

### File esistenti da modificare

`backend/app/api/intelligence.py`  
Nuovi endpoint:

- `POST /api/intelligence/tools/graph-path-explainer`
- `POST /api/intelligence/tools/contradiction-finder`

`frontend/src/features/intelligence/TenderIntelligencePanel.tsx`  
Render dei finding spiegabili.

### Test

`backend/tests/test_requirement_relation_review.py`  
`backend/tests/test_requirement_graph_backfill.py`  
oppure nuovo  
`backend/tests/test_contradiction_finder.py`

Questa PR sfrutta il fatto che TenderWriter ha già requirement graph foundation, review/relation foundation e backfill dei grafi requirement.

---

## PR 6 — Lifecycle projection nel grafo

### Nuovi file

`backend/app/intelligence/lifecycle_projector.py`  
Responsabilità:

- proiettare eventi canonici su snapshot requirement nel grafo
- creare `RequirementEvent` o equivalente struttura di projection

### File esistenti da modificare

`backend/app/services/tender_requirements.py`  
Estendere sync requirement→graph.

`backend/app/services/operational_workflow.py`  
Aggiungere hook/emit per projection update quando review/rework cambiano.

`backend/app/services/kpi_reason_engine.py`  
Se serve esporre helper per leggere eventi/stato utili alla projection.

### Nuova migration

`backend/migrations/versions/202604XX_0011_requirement_lifecycle_projection.py`

Qui puoi:

- aggiungere eventuale stato SQL di supporto se necessario
- oppure solo segnare nuove strutture di sync lato application layer

### Test

`backend/tests/test_operational_workflow.py`  
Verifica che review/rework generino eventi coerenti.

Il motivo tecnico è forte: TenderWriter ha già eventi come `review_approved`, `review_changes_requested`, `rework_resolved`, ecc., nati dal workflow sezione→contribution→review/rework; quindi proiettarli sul grafo è naturale.

---

## PR 7 — Personas catalog + rehearsal schema

### Nuovi file

`backend/app/intelligence/personas.py`  
Dataclass/model `ReviewerPersona`.

`backend/app/intelligence/persona_catalog.py`  
Catalogo iniziale:

- formalista_amministrativo
- valutatore_tecnico
- compliance_officer
- economico_finanziario
- rup_simulato

`backend/app/intelligence/rehearsal_prompts.py`  
Prompt persona-specifici.

### Nuovi modelli

`backend/app/models/rehearsal.py`  
Con:

- `RehearsalRun`
- `RehearsalPersonaResult`
- `RehearsalRecommendation`

### File esistenti da modificare

`backend/app/models/__init__.py`  
Esporta i nuovi modelli.

### Nuova migration

`backend/migrations/versions/202604XX_0012_add_rehearsal_tables.py`

### Test

`backend/tests/test_rehearsal_models.py`  
`backend/tests/test_persona_catalog.py`

Questa PR prende da MiroFish il concetto di persona/profilo, ma lo rifonda in chiave procurement: in MiroFish i profili includono `bio`, `persona`, `profession`, `interested_topics`; in TenderWriter conviene usare pesi decisionali e controlli obbligatori.

---

## PR 8 — Rehearsal service + Celery task

### Nuovi file

`backend/app/intelligence/rehearsal.py`  
`TenderRehearsalService`

`backend/app/intelligence/rehearsal_runner.py`  
Se vuoi separare orchestration da scoring/aggregation.

### File esistenti da modificare

`backend/app/tasks.py`  
Aggiungi `run_rehearsal_task`.

`backend/app/api/intelligence.py`  
Aggiungi:

- `POST /api/intelligence/rehearsals`
- `GET /api/intelligence/rehearsals/{id}`

`backend/app/celery.py`  
Se serve includere il nuovo task.

### Test

`backend/tests/test_rehearsal_api.py`  
`backend/tests/test_rehearsal_service.py`

Questa PR è dove TenderWriter supera MiroFish sul piano infrastrutturale: MiroFish usa `SimulationIPCClient` con `ipc_commands`, `ipc_responses` e polling; qui tutto passa su Celery/Redis e modelli persistiti.

---

## PR 9 — Conversione manuale recommendation → ReworkAction

### File esistenti da modificare

`backend/app/api/intelligence.py`  
Aggiungi endpoint:

- `POST /api/intelligence/rehearsals/{id}/recommendations/{rec_id}/accept`
- `POST /api/intelligence/rehearsals/{id}/recommendations/{rec_id}/dismiss`

`backend/app/services/operational_workflow.py`  
Helper per creare `ReworkAction` dal recommendation payload.

`frontend/src/features/intelligence/RehearsalPanel.tsx`  
Bottoni:

- “Create rework”
- “Dismiss recommendation”

### Test

`backend/tests/test_operational_workflow.py`  
`backend/tests/test_rehearsal_api.py`

Qui la regola è rigida: il rehearsal **non** apre automaticamente rework. Propone. L’utente conferma. Questo è perfettamente coerente con il modello TenderWriter di workflow osservabile e governato.

---

## PR 10 — Forecast enrichment

### File esistenti da modificare

`kpi-reason-engine/app/forecasting.py`  
Aggiungi supporto a `rehearsal_summary` come segnale accessorio.

`kpi-reason-engine/app/schemas.py`  
Estendi lo schema di response forecast.

`backend/app/services/kpi_reason_engine.py`  
Propaga il blocco rehearsal.

`frontend/src/features/observability/views/ForecastTab.tsx`  
Render del blocco `rehearsal_summary`.

### Test

`kpi-reason-engine/tests/test_api.py`  
`kpi-reason-engine/tests/test_runtime_metrics.py`  
`backend/tests/test_kpi_reason_engine.py`

Questa PR è giustificata perché il forecast esistente è già costruito attorno a `submit_on_time`, `extended_rework`, `pause_or_stop`, e usa fase corrente, transizioni recenti, KPI driver, deadline pressure e blocker pressure. Il rehearsal deve entrare come arricchimento, non come sostituzione della formula.

---

# B) Ordine delle PR, dipendenze e rollout

## Sequenza consigliata

### PR 1

**Fondazione `intelligence/` + ontologia**  
Perché è il punto meno rischioso e massimizza compatibilità con extraction/review.

### PR 2

**Tool registry + tool Wave 1**  
Porta subito valore misurabile agli utenti interni.

### PR 3

**API + FE Wave 1**  
Solo quando i tool backend sono stabili.

### PR 4

**Agent orchestration**  
Entra solo dopo che i tool hanno contratti chiari.

### PR 5

**Graph explain + contradiction finder**  
Qui il sistema comincia a dare vero valore investigativo.

### PR 6

**Lifecycle projection nel grafo**  
Va dopo PR 4/5, così sai già quali explain path servono davvero.

### PR 7

**Personas + rehearsal schema**  
Prepari il terreno senza ancora lanciare il loop.

### PR 8

**Rehearsal service + task + API**  
Prima internal beta.

### PR 9

**Recommendation → Rework manuale**  
Solo dopo aver verificato qualità dei recommendation.

### PR 10

**Forecast enrichment**  
Ultima, perché dipende dalla qualità reale del rehearsal.

---

## Dipendenze esplicite

### Wave 1 dipende da

- `requirement_extraction_v2`
- requirement review/consolidation
- KPI adapter base

### Wave 2 dipende da

- Wave 1 completa
- requirement graph sync stabile
- workflow review/rework affidabile
- evento canonico coerente

### Wave 3 dipende da

- Wave 2 completa
- tool grounded stabili
- forecast già affidabile
- utenti interni che usano davvero review/rework/gate

---

## Rischi e gate per PR

### PR 1–3

Rischio basso  
Gate:

- nessuna regressione su extraction/review
- tool read-only
- FE mostra risultati coerenti col backend

### PR 4–6

Rischio medio  
Gate:

- agent usa max 3 tool
- graph explain leggibile
- contradiction findings non rumorosi

### PR 7–10

Rischio medio/alto  
Gate:

- personas non generiche
- rehearsal utile su tender reali
- nessuna mutazione automatica del workflow
- forecast arricchito ma non destabilizzato

---

## Rollout ambientale

### Step 1 — internal only

Abilita:

- ontologia
- coverage/evidence/compliance tools
- niente `/query` aperto a tutti

### Step 2 — guided beta

Abilita:

- intelligence query
- graph explain
- contradiction finder  
    su pochi tender pilota

### Step 3 — rehearsal beta

Abilita:

- create rehearsal
- report read-only
- nessuna conversione automatica a rework

### Step 4 — controlled production

Abilita:

- accept recommendation → create rework
- forecast enrichment  
    solo dopo metriche di qualità sufficienti

---

## Metriche di successo

### Wave 1

- % requirement con ontologia valorizzata
- tempo medio tool response
- % tool result giudicati utili dagli utenti

### Wave 2

- % query intelligence risolte con 1–2 tool
- explain path judged correct
- contradiction precision su gold/sample set

### Wave 3

- % rehearsal con almeno 1 finding utile
- divergenza tra reviewer come segnale, non rumore
- % recommendation trasformate in rework
- impatto su riduzione di blocker aperti prima del gate

---

## Decisione finale

Se vuoi farlo bene, il programma va eseguito così:

**PR 1 → 2 → 3** per dare strumenti solidi.  
**PR 4 → 5 → 6** per costruire il “cervello” investigativo.  
**PR 7 → 8 → 9 → 10** per importare davvero la parte MiroFish di personas e rehearsal, ma con la governance TenderWriter.

È la sequenza che prende il meglio di MiroFish — ontology-first, tool-rich reasoning, personas, rehearsal — e lo incastra sopra:

- workflow review/rework/gate già attivo,
- KPI/forecast già modellato,
- architettura backend già asincrona e persistita, invece di polling/IPC locale.

Nel prossimo passaggio posso trasformare questo piano in una **checklist PR-by-PR pronta da dare a Codex/Claude**, con per ogni PR:

- titolo,
- file da creare/modificare,
- acceptance criteria,
- test da scrivere.

si

Sto raccogliendo i riferimenti puntuali per ogni PR, così la checklist finale sia direttamente eseguibile e ancorata al codice reale.

Thought for 52s

Perfetto. Ti lascio una checklist **PR-by-PR**, pensata per essere data direttamente a Codex/Claude.

La sequenza segue due vincoli emersi dal codice: MiroFish vale per workflow a 5 fasi, ReportAgent tool-driven, personas e rehearsal; TenderWriter vale per workflow review/rework/gate, forecast a tre scenari e task asincroni già pronti. Quindi l’ordine corretto è: prima strumenti grounded, poi agente, poi rehearsal.

## PR-01 — Create intelligence package and ontology schema

**Titolo**  
Create `app/intelligence` foundation and ontology tagging v1

**Files da creare**

- `backend/app/intelligence/__init__.py`
- `backend/app/intelligence/schemas.py`
- `backend/app/intelligence/ontology.py`

**Files da modificare**

- `backend/app/services/requirement_extraction_v2.py`
- `backend/tests/test_requirement_extraction_v2.py`
- `backend/tests/test_requirement_review.py`

**Cosa fare**

- Definire `RequirementOntologyTag`
- Implementare `TenderOntologyService`
- Aggiungere tagging ontologico post-extraction
- Salvare il risultato in `metadata_json`, senza migration SQL in questa PR

**Acceptance criteria**

- Ogni requirement estratto riceve un blocco `metadata_json["ontology"]` quando il mapping è possibile
- Nessuna regressione su extraction v2
- Nessuna scrittura di stato operativo fuori dai requirement metadata

**Test da scrivere**

- unit test keyword/rule mapping
- integration test extraction → ontology tagging
- regression test su review pipeline

---

## PR-02 — Add tool registry and Wave 1 tools

**Titolo**  
Add intelligence tool registry with coverage, evidence, compliance panorama

**Files da creare**

- `backend/app/intelligence/tool_registry.py`
- `backend/app/intelligence/tools/__init__.py`
- `backend/app/intelligence/tools/coverage_analyzer.py`
- `backend/app/intelligence/tools/evidence_auditor.py`
- `backend/app/intelligence/tools/compliance_panorama.py`

**Files da modificare**

- `backend/app/services/kpi_reason_engine.py`
- `backend/tests/test_compliance_observability.py`
- `backend/tests/test_kpi_reason_engine.py`

**Cosa fare**

- Registrare tre tool:
    - `coverage_analyzer`
    - `evidence_auditor`
    - `compliance_panorama`
- Fare di `compliance_panorama` un adapter verso KPI engine, non un duplicato di logica

**Acceptance criteria**

- I tre tool restituiscono JSON strutturato e stabile
- `compliance_panorama` riflette snapshot/gate/forecast già esistenti
- I tool sono read-only

**Test da scrivere**

- unit test registry register/get/list
- test coverage analyzer su tender fixture
- test evidence auditor su evidence `strong/weak/missing`
- test contract `compliance_panorama` ↔ KPI adapter

---

## PR-03 — Expose Wave 1 intelligence APIs and basic UI

**Titolo**  
Expose intelligence tool APIs and basic Tender Intelligence panel

**Files da creare**

- `backend/app/api/intelligence.py`
- `frontend/src/features/intelligence/TenderIntelligencePanel.tsx`

**Files da modificare**

- `backend/app/main.py`
- `backend/app/api/__init__.py`
- `frontend/src/api/client.ts`
- `frontend/src/api/client.test.ts`
- `frontend/src/router/lazyRoutes.tsx`
- eventuale pagina contenitore observability/workspace

**Cosa fare**

- Aggiungere endpoint:
    - `GET /api/intelligence/tools`
    - `POST /api/intelligence/tools/coverage-analyzer`
    - `POST /api/intelligence/tools/evidence-auditor`
    - `POST /api/intelligence/tools/compliance-panorama`
- Aggiungere pannello FE con tre bottoni tool

**Acceptance criteria**

- I 3 endpoint rispondono correttamente
- Il pannello FE consente di lanciare i tool su un tender reale
- Nessuna regressione sul routing principale

**Test da scrivere**

- backend route registration
- API integration tests
- frontend client tests
- FE smoke test del pannello

---

## PR-04 — Introduce TenderIntelligenceAgent

**Titolo**  
Add tool-orchestrating Tender Intelligence Agent

**Files da creare**

- `backend/app/intelligence/agent.py`
- `backend/app/intelligence/prompts.py`
- `backend/app/intelligence/result_models.py`

**Files da modificare**

- `backend/app/api/intelligence.py`
- `backend/app/intelligence/tool_registry.py`
- `frontend/src/features/intelligence/TenderIntelligencePanel.tsx`

**Cosa fare**

- Implementare loop controllato:
    - classify intent
    - select tools
    - run tools
    - synthesize answer
- Aggiungere `POST /api/intelligence/query`

**Acceptance criteria**

- Max 3 tool per query
- Output con `intent`, `tools_used`, `answer`, `findings`, `recommended_actions`
- Nessuna scrittura su workflow/review/gate/rework

**Test da scrivere**

- intent classification tests
- tool selection limit tests
- read-only enforcement tests
- happy path `why amber?`

---

## PR-05 — Add graph explain and contradiction finder

**Titolo**  
Add graph explainability and contradiction detection tools

**Files da creare**

- `backend/app/intelligence/tools/graph_path_explainer.py`
- `backend/app/intelligence/tools/contradiction_finder.py`

**Files da modificare**

- `backend/app/api/intelligence.py`
- `frontend/src/features/intelligence/TenderIntelligencePanel.tsx`
- `backend/tests/test_requirement_graph_backfill.py`
- nuovo `backend/tests/test_contradiction_finder.py`

**Cosa fare**

- Aggiungere endpoint:
    - `POST /api/intelligence/tools/graph-path-explainer`
    - `POST /api/intelligence/tools/contradiction-finder`
- Spiegare catene requirement → section → contribution → review/rework/gate
- Trovare conflitti:
    - requirement vs proposal
    - proposal vs evidence
    - requirement vs requirement

**Acceptance criteria**

- Explain path leggibile e grounded
- Contradiction finder produce finding utili, non rumore
- Nessuna dipendenza da LLM per tutto il flusso: usare pre-filter strutturato + verifica mirata

**Test da scrivere**

- graph explain path assembly
- contradiction candidate generation
- contradiction precision on fixtures

---

## PR-06 — Project lifecycle events into graph

**Titolo**  
Project operational lifecycle into requirement graph

**Files da creare**

- `backend/app/intelligence/lifecycle_projector.py`

**Files da modificare**

- `backend/app/services/tender_requirements.py`
- `backend/app/services/operational_workflow.py`
- `backend/app/services/kpi_reason_engine.py`
- `backend/tests/test_operational_workflow.py`

**Migration**

- `backend/migrations/versions/202604XX_0011_requirement_lifecycle_projection.py`

**Cosa fare**

- Proiettare eventi canonici sul grafo requirement
- Aggiornare snapshot requirement nel grafo con:
    - `current_status`
    - `coverage_status`
    - `risk_level`
    - `gate_state`
    - `last_event_type`
    - `last_event_at`
- Supportare relazione `HAS_LIFECYCLE_EVENT`

**Acceptance criteria**

- Review/rework/gate updates riflessi nel grafo
- Explain tool può leggere anche gli eventi lifecycle
- Nessuna divergenza tra stato canonico DB e proiezione grafo

**Test da scrivere**

- event projection tests
- graph snapshot refresh tests
- integration test review/rework → graph update

---

## PR-07 — Add reviewer personas and rehearsal schema

**Titolo**  
Add deterministic reviewer personas and rehearsal data model

**Files da creare**

- `backend/app/intelligence/personas.py`
- `backend/app/intelligence/persona_catalog.py`
- `backend/app/intelligence/rehearsal_prompts.py`
- `backend/app/models/rehearsal.py`

**Files da modificare**

- `backend/app/models/__init__.py`

**Migration**

- `backend/migrations/versions/202604XX_0012_add_rehearsal_tables.py`

**Cosa fare**

- Definire catalogo personas v1:
    - formalista_amministrativo
    - valutatore_tecnico
    - compliance_officer
    - economico_finanziario
    - rup_simulato
- Aggiungere tabelle:
    - `rehearsal_runs`
    - `rehearsal_persona_results`
    - `rehearsal_recommendations`

**Acceptance criteria**

- Catalogo personas deterministico e versionato
- Tabelle create e usabili
- Nessuna generazione automatica via LLM in questa PR

**Test da scrivere**

- persona catalog tests
- schema/model tests
- alembic smoke test

---

## PR-08 — Implement rehearsal service and background execution

**Titolo**  
Implement Tender Rehearsal Service with Celery execution

**Files da creare**

- `backend/app/intelligence/rehearsal.py`
- `backend/app/intelligence/rehearsal_runner.py`

**Files da modificare**

- `backend/app/tasks.py`
- `backend/app/api/intelligence.py`
- `backend/app/celery.py`
- `backend/tests/test_rehearsal_service.py`
- `backend/tests/test_rehearsal_api.py`

**Cosa fare**

- Implementare `TenderRehearsalService`
- Orchestrare evaluation loop per persona
- Eseguire il rehearsal via Celery task
- Esporre:
    - `POST /api/intelligence/rehearsals`
    - `GET /api/intelligence/rehearsals/{id}`

**Acceptance criteria**

- Rehearsal eseguito asincronicamente
- Report persistito in `rehearsal_runs.report_json`
- Persona results e recommendations persistiti
- Nessun uso di polling/IPC su filesystem

**Test da scrivere**

- create/status API tests
- Celery task execution tests
- rehearsal aggregation tests

---

## PR-09 — Manual recommendation to rework conversion

**Titolo**  
Allow manual conversion of rehearsal recommendations into rework actions

**Files da modificare**

- `backend/app/api/intelligence.py`
- `backend/app/services/operational_workflow.py`
- `frontend/src/features/intelligence/RehearsalPanel.tsx`
- `backend/tests/test_operational_workflow.py`
- `backend/tests/test_rehearsal_api.py`

**Cosa fare**

- Aggiungere endpoint:
    - `POST /api/intelligence/rehearsals/{id}/recommendations/{rec_id}/accept`
    - `POST /api/intelligence/rehearsals/{id}/recommendations/{rec_id}/dismiss`
- Su accept:
    - creare `ReworkAction`
    - linkare `linked_rework_action_id`
    - aggiornare status recommendation

**Acceptance criteria**

- Nessuna recommendation crea rework automaticamente
- L’utente deve confermare manualmente
- Il nuovo rework entra nel workflow canonico esistente

**Test da scrivere**

- accept → rework created
- dismiss → no side effects
- idempotency / double accept protection

---

## PR-10 — Enrich KPI forecast with rehearsal summary

**Titolo**  
Enrich forecast with rehearsal summary without changing primary state engine

**Files da modificare**

- `kpi-reason-engine/app/forecasting.py`
- `kpi-reason-engine/app/schemas.py`
- `backend/app/services/kpi_reason_engine.py`
- `frontend/src/features/observability/views/ForecastTab.tsx`
- `kpi-reason-engine/tests/test_api.py`
- `backend/tests/test_kpi_reason_engine.py`

**Cosa fare**

- Aggiungere blocco `rehearsal_summary` al forecast
- Non modificare subito la formula principale del forecast; introdurre solo arricchimento

**Acceptance criteria**

- Forecast continua a esporre i 3 scenari esistenti
- Compare `rehearsal_summary`
- Nessun impatto regressivo sui casi attuali `submit_on_time / extended_rework / pause_or_stop`

**Test da scrivere**

- forecast schema extension tests
- backward compatibility tests
- FE render tests

---

# Ordine di esecuzione consigliato

Esegui le PR in questo ordine:

1. PR-01
2. PR-02
3. PR-03
4. PR-04
5. PR-05
6. PR-06
7. PR-07
8. PR-08
9. PR-09
10. PR-10

Perché:

- prima stabilizzi ontologia e tool;
- poi costruisci l’agente sopra tool affidabili;
- poi introduci explainability e lifecycle nel grafo;
- solo dopo passi a personas e rehearsal;
- forecast enrichment arriva per ultimo perché dipende dalla qualità del rehearsal e dai segnali già stabilizzati. Questo è coerente sia con il modo in cui MiroFish costruisce valore a strati, sia con il fatto che TenderWriter ha già workflow review/rework/gate e forecast calibrato da preservare.

# Rollout operativo

Internal beta:

- PR-01 → PR-05

Controlled beta:

- PR-06 → PR-08

Production-gated:

- PR-09 → PR-10

In particolare:

- PR-08 va attivata solo per tender non submitted;
- PR-09 va attivata solo per admin/power user;
- PR-10 va attivata dietro feature flag nel KPI engine.

---

Se vuoi, nel prossimo messaggio ti preparo la stessa checklist in formato **copiabile per issue tracker**, con un blocco per ogni PR già pronto da incollare in GitHub/Jira.

---

# Stato implementazione (2026-04-20)

## PR-08 — Rehearsal service + Celery

- **Status**: implementato.
- **File**: `backend/app/api/intelligence.py` (handler `create_rehearsal_run`, L417-434), `backend/app/intelligence/rehearsal.py`, `backend/app/intelligence/rehearsal_runner.py`, `backend/app/tasks.py` (`run_rehearsal_task`).
- **Rollout guard**: modulo `_REHEARSAL_BLOCKED_TENDER_STATUSES = {SUBMITTED, WON, LOST, CANCELLED}` blocca la creazione con HTTP 409 se il tender è già in uno stato terminale. Coerente col vincolo "PR-08 va attivata solo per tender non submitted".
- **Test**: `tests/test_intelligence_rehearsal_api.py::CreateRehearsalStatusGuardTests` (5 casi: submitted/won/lost/cancelled → 409; tender mancante → 404).

## PR-09 — Manual recommendation → rework conversion

- **Status**: implementato con admin gate.
- **File**: `backend/app/api/intelligence.py` (handlers `accept_rehearsal_recommendation`, `dismiss_rehearsal_recommendation`), helper `_require_admin(current_user)` che valuta `current_user.role == "admin"` e solleva 403 altrimenti.
- **Rollout guard**: gate applicato come prima istruzione dei due handler, prima del caricamento run/recommendation e del `check_tender_access`. Coerente col vincolo "PR-09 va attivata solo per admin/power user".
- **Test**: `tests/test_intelligence_rehearsal_api.py::RecommendationAdminGateTests` (accept/dismiss non-admin → 403; helper accetta admin).

## PR-10 — KPI forecast enrichment con rehearsal summary

- **Status**: implementato lato `app.api.kpi_admin` invece che `kpi-reason-engine`. Divergenza architetturale da documentare.
- **File**: `backend/app/config.py` (`rehearsal_summary_enabled: bool = False`), `backend/app/api/kpi_admin.py` (`get_kpi_tender_forecast`, linee ~920-932) con blocco `if settings.rehearsal_summary_enabled:` intorno alla enrichment.
- **Rollout guard**: flag spenta di default. Coerente col vincolo "PR-10 va attivata dietro feature flag nel KPI engine", ma la flag vive nel backend wrapper, non nel `kpi-reason-engine`. Possibile lavoro futuro: spostare la logica al servizio remoto mantenendo il flag come passthrough.
- **Test**: `tests/test_rehearsal_summary.py::KpiForecastEnrichmentTests` (3 casi: enrichment ON → chiave presente; fallback `None` → chiave con run_id None; flag OFF → chiave assente e `build_rehearsal_summary` non invocato).

## Divergenze ancora aperte

- PR-10 enrichment è in `backend/app/api/kpi_admin.py` invece di `kpi-reason-engine/app/forecasting.py`. Verifica: `grep -n rehearsal backend/app/services/kpi_reason_engine.py` → nessun match; il servizio remoto non espone rehearsal. Per ora scelta pragmatica accettata; se in futuro il `kpi-reason-engine` avrà accesso diretto alla tabella rehearsal si potrà spostare la logica mantenendo il flag come passthrough.

## Divergenze risolte

- FE: rehearsal panel estratto in `frontend/src/features/intelligence/RehearsalPanel.tsx` + `frontend/src/features/intelligence/shared.tsx` (`HEALTH_COLOR`, `StatusBadge`). `pages/TenderIntelligence.tsx` ora importa il componente. Vitest 95/95 verde dopo refactor.

## Baseline test post-rollout safety

- `tests/test_intelligence_*.py` + `tests/test_rehearsal_*.py` + `tests/test_ontology_service.py` + `tests/test_lifecycle_projector.py` + `tests/test_main_route_registration.py`: **155 passed** (include `test_active_status_passes_guard_and_hits_proposal_lookup` per verificare che il guard PR-08 non faccia falso-positivo su tender DRAFT).
- Frontend vitest: **95/95 passed** (incluso `pages/TenderIntelligence.test.tsx` con 5 casi post-estrazione in `features/intelligence/`).
- `.env.example` espone `REHEARSAL_SUMMARY_ENABLED=false` vicino ai sibling `REQUIREMENT_EXTRACTION_LLM_V2_*`.
- Fallimenti non correlati noti: `tests/test_sprint_1_stability.py` (OnlyOffice signed URL), `tests/test_tender_document_requirement_extractor.py`, alcuni test legacy rimossi dal prodotto — pre-esistenti, fuori scope rollout PR-08/09/10.
