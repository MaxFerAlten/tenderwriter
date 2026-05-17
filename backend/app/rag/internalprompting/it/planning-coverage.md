# Planning Coverage Messages (IT)

Etichette slot, note, template di errore, e definizioni degli slot di copertura.

## Messages

slot_label_identification: Identificazione procedura
slot_label_cig_lots: CIG e lotti
slot_label_amounts: Importi e massimali
slot_label_duration: Durata
slot_label_deadlines: Scadenze
slot_label_platform: Piattaforma e accesso
slot_label_scoring: Punteggi e criteri
slot_label_certifications: Certificazioni
slot_label_sla_penalties: SLA e penali
slot_label_documents: Documenti e vincoli

tender_query_terms: gara|appalto|procedura|disciplinare|capitolato|lotto|lotti|cig|rup|offerta|stazione appaltante

note_disabled: Planning coverage disabilitato da configurazione.
note_not_tender: Query non classificata come gara; coverage non eseguito.
note_activated_tender: Coverage planner attivato su query tender-like.
note_activated_always: Coverage planner attivato da configurazione always_on.
note_no_slot_activated: Nessuno slot specifico attivato.

error_sparse_retrieval: Sparse retrieval fallito per slot {slot}: {error}
error_dense_retrieval: Dense retrieval fallito per slot {slot}: {error}
error_graph_retrieval: Graph retrieval fallito per slot {slot}: {error}

slot_identification_trigger: determina|determinazione|rup|stazione appaltante|procedura
slot_identification_queries: "determinazione" "rep." "prot." "indice" "indetta"|"responsabile unico del progetto" "RUP" "ing." "dott."|"stazione appaltante" "procedura" "numero gara"
slot_identification_evidence: determinazione|responsabile unico|rup|stazione appaltante|indetta|rep.|prot.

slot_cig_lots_trigger: cig|lotto|lotti|simog
slot_cig_lots_queries: "CIG" "lotto 1" "lotto 2" "lotto 3" "lotto 4"|"codice CIG" "lotto" "gara"|"SIMOG" "CIG" "lotti"
slot_cig_lots_evidence: cig|lotto|lotti|simog

slot_amounts_trigger: importo|base d'asta|base asta|valore|euro|oneri|massimale
slot_amounts_queries: base d'asta|IVA esclusa|importo|€|massimale|accordo quadro|quinto d'obbligo|20%|oneri sicurezza|importo|euro
slot_amounts_evidence: base d'asta|base asta|iva esclusa|importo|euro|€|massimale|oneri|quinto

slot_duration_trigger: durata|mesi|giorni|proroga|rinnovo|decorrenza|stipula
slot_duration_queries: "durata" "mesi dalla stipula" "giorni" "proroga"|"rinnovo" "decorrenza" "\d+ mesi" "\d+ giorni"
slot_duration_evidence: durata|mesi dalla stipula|giorni|proroga|rinnovo|decorrenza|\d+ mesi|\d+ giorni

slot_deadlines_trigger: scadenza|termine|presentazione|offerte|ore|deadline
slot_deadlines_queries: "termine" "presentazione" "offerte" "ore"|"scadenza" "presentazione offerte" "data"
slot_deadlines_evidence: termine|presentazione|offerte|ore|scadenza|deadline

slot_platform_trigger: piattaforma|piattaforma telematica|portale|autenticazione|spid|cie|cns|eidas|url
slot_platform_queries: "piattaforma telematica" "portale" "URL" "autenticazione"|"SPID" "CIE" "CNS" "eIDAS" "autenticazione"|"portale" "piattaforma telematica" "gara"
slot_platform_evidence: piattaforma telematica|portale|url|autenticazione|spid|cie|cns|eidas

slot_scoring_trigger: punteggio|offerta tecnica|offerta economica|criterio|valutazione|qualità/prezzo
slot_scoring_queries: "punteggio" "offerta tecnica" "offerta economica" "criteri di valutazione"|"punteggio tecnico" "punteggio economico" "qualità/prezzo"
slot_scoring_evidence: punteggio|offerta tecnica|offerta economica|criteri di valutazione|punteggio tecnico|punteggio economico|qualità/prezzo

slot_certifications_trigger: certificazione|certificazioni|iso|uni|qualificazione|attestazione
slot_certifications_queries: "certificazione" "certificazioni" "ISO" "UNI"|"qualificazione" "attestazione" "requisito obbligatorio"
slot_certifications_evidence: certificazione|certificazioni|iso|uni|qualificazione|attestazione|requisito obbligatorio

slot_sla_penalties_trigger: sla|penale|penali|livello di servizio|disponibilita|disponibilità
slot_sla_penalties_queries: "penale" "%" "livello di servizio" "SLA" "disponibilità"|"penali" "livelli di servizio" "risoluzione"
slot_sla_penalties_evidence: sla|penale|penali|livello di servizio|disponibilità|risoluzione

slot_documents_trigger: passoe|avcpass|dgue|garanzia|cauzione|documenti|vincolo
slot_documents_queries: "PASSOE" "AVCpass" "DGUE" "garanzia" "cauzione"|"max" "lotti" "aggiudicabili" "partecipare" "vincolo"|"documentazione amministrativa" "disciplinare" "allegati"
slot_documents_evidence: passoe|avcpass|dgue|garanzia|cauzione|vincolo|allegati
