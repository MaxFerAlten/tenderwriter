# Guardrail Messages (EN)

User-facing messages emitted by the RAG guardrails when an answer is blocked
or repaired. Keys are consumed by `_build_guardrail_blocked_answer` and
`_append_guardrail_soft_warning` in `engine.py`.

## Messages

soft_warning: > Note: some numeric values that could not be verified against the retrieved sources have been masked or replaced.
blocked_intro: Generated answer discarded: it contained values not verified against the retrieved sources.
fact_sheet_heading: Verified facts available:
procedure_label: Procedure
procedure_id_label: Procedure ID
cig_label: CIG
critical_days_label: Critical days
duration_label: Duration
amounts_label: Amounts
locations_label: Locations
percentages_label: Percentages
sources_label: Sources
not_detected: not detected
conflict_detected: conflict detected
