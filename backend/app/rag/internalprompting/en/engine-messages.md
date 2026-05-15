# Engine Messages (EN)

Labels emitted by the engine for the fact sheet serialized inside the
context, keywords used by the heading detection regex, missing/conflict
field markers, the user-facing fallback messages, and the sentinel used
for procedure classification.

The FACT_SHEET_START / FACT_SHEET_END markers (protocol section) stay
identical across IT and EN because they are part of the wire protocol.

## Messages

fact_sheet_heading_text: Verified facts
fact_sheet_start_marker: FACT_SHEET_START
fact_sheet_end_marker: FACT_SHEET_END
fact_sheet_label_procedure: procedure
fact_sheet_label_status: verification_status
fact_sheet_label_procedure_id: procedure_id
fact_sheet_label_cig: cig
fact_sheet_label_critical_days: critical_days
fact_sheet_label_duration: duration
fact_sheet_label_amounts: amounts
fact_sheet_label_locations: locations
fact_sheet_label_percentages: percentages
fact_sheet_label_sources: sources
fact_sheet_label_conflicts: conflicts
fact_sheet_value_not_detected: not_detected
fact_sheet_value_no_conflicts: none
fact_sheet_value_conflict_detected: conflict_detected
procedure_label_unattributed: unattributed
model_unavailable_fallback: The model is temporarily unavailable. Showing only the retrieved sources.
length_unit_lines: lines
length_unit_words: words
