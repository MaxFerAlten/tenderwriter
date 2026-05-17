# Planning Coverage Messages (EN)

Slot labels, notes, error templates, and coverage slot definitions.

## Messages

slot_label_identification: Identification
slot_label_cig_lots: CIG and lots
slot_label_amounts: Amounts and ceilings
slot_label_duration: Duration
slot_label_deadlines: Deadlines
slot_label_platform: Platform and access
slot_label_scoring: Scores and criteria
slot_label_certifications: Certifications
slot_label_sla_penalties: SLA and penalties
slot_label_documents: Documents and constraints

tender_query_terms: gara|appalto|procedura|disciplinare|capitolato|lotto|lotti|cig|rup|offerta|stazione appaltante

note_disabled: Planning coverage disabled by configuration.
note_not_tender: Query not classified as tender; coverage not executed.
note_activated_tender: Coverage planner activated on tender-like query.
note_activated_always: Coverage planner activated by always_on configuration.
note_no_slot_activated: No specific slot activated.

error_sparse_retrieval: Sparse retrieval failed for slot {slot}: {error}
error_dense_retrieval: Dense retrieval failed for slot {slot}: {error}
error_graph_retrieval: Graph retrieval failed for slot {slot}: {error}

slot_identification_trigger: determina|determinazione|rup|stazione appaltante|procedura
slot_identification_queries: "determinazione" "rep." "prot." "indice" "indetta"|"responsabile unico del progetto" "RUP" "ing." "dott."|"stazione appaltante" "procedura" "numero gara"
slot_identification_evidence: determinazione|responsabile unico|rup|stazione appaltante|indetta|rep.|prot.

slot_cig_lots_trigger: cig|lotto|lotti|simog
slot_cig_lots_queries: "CIG" "lotto 1" "lotto 2" "lotto 3" "lotto 4"|"codice CIG" "lotto" "gara"|"SIMOG" "CIG" "lotti"
slot_cig_lots_evidence: cig|lotto|lotti|simog

slot_amounts_trigger: importo|base d'asta|base asta|valore|euro|oneri|massimale
slot_amounts_queries: base d'asta|IVA esclusa|importo|€|massimale|accordo quadro|quinto d'obbligo|20%|oneri sicurezza|importo|euro
slot_amounts_evidence: base d'asta|base asta|iva esclusa|importo|euro|€|massimale|oneri|quinto

slot_duration_trigger: duration|months|days|extension|renewal|start date|signing
slot_duration_queries: "duration" "months from signing" "days" "extension"|"renewal" "start date" "\d+ months" "\d+ days"
slot_duration_evidence: duration|months from signing|days|extension|renewal|start date|\d+ months|\d+ days

slot_deadlines_trigger: scadenza|termine|presentazione|offerte|ore|deadline
slot_deadlines_queries: "termine" "presentazione" "offerte" "ore"|"scadenza" "presentazione offerte" "data"
slot_deadlines_evidence: termine|presentazione|offerte|ore|scadenza|deadline

slot_platform_trigger: e-procurement platform|portal|authentication|spid|cie|cns|eidas|url
slot_platform_queries: "e-procurement platform" "portal" "URL" "authentication"|"SPID" "CIE" "CNS" "eIDAS" "authentication"|"portal" "e-procurement platform" "tender"
slot_platform_evidence: e-procurement platform|portal|url|authentication|spid|cie|cns|eidas

slot_scoring_trigger: score|technical bid|economic bid|criterion|evaluation|quality/price
slot_scoring_queries: "score" "technical bid" "economic bid" "evaluation criteria"|"technical score" "economic score" "quality/price"
slot_scoring_evidence: score|technical bid|economic bid|evaluation criteria|technical score|economic score|quality/price

slot_certifications_trigger: certification|certifications|iso|uni|qualification|attestation
slot_certifications_queries: "certification" "certifications" "ISO" "UNI"|"qualification" "attestation" "mandatory requirement"
slot_certifications_evidence: certification|certifications|iso|uni|qualification|attestation|mandatory requirement

slot_sla_penalties_trigger: sla|penale|penali|livello di servizio|disponibilita|disponibilità
slot_sla_penalties_queries: "penale" "%" "livello di servizio" "SLA" "disponibilità"|"penali" "livelli di servizio" "risoluzione"
slot_sla_penalties_evidence: sla|penale|penali|livello di servizio|disponibilità|risoluzione

slot_documents_trigger: passoe|avcpass|dgue|garanzia|cauzione|documenti|vincolo
slot_documents_queries: "PASSOE" "AVCpass" "DGUE" "garanzia" "cauzione"|"max" "lotti" "aggiudicabili" "partecipare" "vincolo"|"documentazione amministrativa" "disciplinare" "allegati"
slot_documents_evidence: passoe|avcpass|dgue|garanzia|cauzione|vincolo|allegati
