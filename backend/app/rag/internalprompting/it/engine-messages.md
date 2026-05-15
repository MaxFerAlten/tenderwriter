# Engine Messages (IT)

Etichette emesse dall'engine per la fact sheet serializzata nel context, le
parole chiave usate dal regex di rilevamento heading, i marker per campi
mancanti/conflitto, i messaggi di fallback user-facing e i sentinel per
classificazione procedura.

I FACT_SHEET_START / FACT_SHEET_END markers (sezione protocol) restano
identici tra IT ed EN perché parte del wire protocol.

## Messages

fact_sheet_heading_text: Fatti verificati
fact_sheet_start_marker: FACT_SHEET_START
fact_sheet_end_marker: FACT_SHEET_END
fact_sheet_label_procedure: procedura
fact_sheet_label_status: stato_verifica
fact_sheet_label_procedure_id: procedure_id
fact_sheet_label_cig: cig
fact_sheet_label_critical_days: giorni_critici
fact_sheet_label_duration: durata
fact_sheet_label_amounts: importi
fact_sheet_label_locations: sedi_luoghi
fact_sheet_label_percentages: percentuali
fact_sheet_label_sources: fonti
fact_sheet_label_conflicts: conflitti
fact_sheet_value_not_detected: non_rilevato
fact_sheet_value_no_conflicts: nessuno
fact_sheet_value_conflict_detected: conflitto_rilevato
procedure_label_unattributed: non_attribuibile
model_unavailable_fallback: Il modello e temporaneamente non disponibile. Mostro solo le fonti recuperate.
length_unit_lines: righe
length_unit_words: parole
