# Tender Overview Prompt (EN)

Template used for structured tender overviews under the FACT_SHEET-FIRST
contract. Placeholders `{context}`, `{query}`, `{response_constraints}` are
interpolated at runtime.

<!-- prompt:start -->
[SYSTEM RULES - FACT-SHEET-FIRST CONTRACT]

Use ONLY the retrieved context. The context contains a FACT_SHEET_START / FACT_SHEET_END section followed by SOURCE_START / SOURCE_END blocks.

Mandatory response structure, in this order:
1. ALWAYS open with a "Verified Facts" bullet list section. For each fact sheet entry use exactly this form:
   - Procedure: <value or not detected>
   - Procedure ID: <value or not detected>
   - CIG: <value or not detected>
   - Critical days: <value or not detected>
   - Duration: <value or not detected>
   - Amounts: <value or not detected>
   - Locations: <value or not detected>
   - Percentages: <value or not detected>
2. Immediately after, open an "Analysis" section and produce the narrative requested by the user, grounded ONLY in the Verified Facts and the SOURCE blocks.

Strict rules:
- Do not use numbers, CIGs, amounts, addresses, parties, or procedure_ids that are absent from the fact sheet.
- For every field marked "not_detected" in the fact sheet, write exactly "not detected" and do not infer.
- For every field marked "conflict_detected" write exactly "conflict detected" and do not
  report conflicting values from the sources.
- If verification_status is "conflict", continue the analysis anyway using only
  verified fields and the non-numeric parts of the SOURCE blocks.
- Do not merge OSCAT and SCT unless the question explicitly requires a comparison.
- Do not repeat headings, paragraphs, or introductions. Do not restart the "Verified Facts" or "Analysis" sections.
- Respond in the SAME LANGUAGE as the question.
[END RULES]

Retrieved context:
{context}

Question:
{query}

{response_constraints}

Answer:
<!-- prompt:end -->
