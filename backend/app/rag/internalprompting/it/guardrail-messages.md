# Guardrail Messages (IT)

Messaggi user-facing emessi dai guardrail RAG quando la risposta viene bloccata
o riparata. Le chiavi sono lette da `_build_guardrail_blocked_answer` e
`_append_guardrail_soft_warning` in `engine.py`.

## Messages

soft_warning: > Nota: alcuni dati numerici non verificabili dalle fonti recuperate sono stati mascherati o sostituiti.
blocked_intro: Risposta generata scartata: conteneva dati non verificati rispetto alle fonti recuperate.
fact_sheet_heading: Fatti verificati disponibili:
procedure_label: Procedura
procedure_id_label: ID procedura
cig_label: CIG
critical_days_label: Giorni critici
duration_label: Durata
amounts_label: Importi
locations_label: Sedi/luoghi
percentages_label: Percentuali
sources_label: Fonti
not_detected: non rilevato
conflict_detected: conflitto rilevato
