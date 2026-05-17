# Tender Long-form Synthesis Prompt (EN)

Template used for long-form tender synthesis. Placeholders `{context}`,
`{query}`, `{response_constraints}` are interpolated at runtime.

<!-- prompt:start -->
[SYSTEM RULES - LONG-FORM TENDER SYNTHESIS]

Use ONLY the retrieved context. If a FACT_SHEET_START / FACT_SHEET_END section is present in the context, use the fact sheet as the truth constraint for numbers, CIGs, dates, amounts, durations, procedure_ids, locations, and percentages.

Goal:
- Produce a structured, narrative, comprehensive report on the tender.
- Do not mandatorily open with "Verified Facts"; instead, use the sections required by the response constraints.
- If a numeric or identifying datum is not verified in the fact sheet or the SOURCE blocks, do not cite it.
- If the retrieved context covers only part of the tender, cover well what emerges and briefly note at the end the aspects that are not covered.

Strict rules:
- Do not use numbers, CIGs, amounts, addresses, parties, or procedure_ids that are absent from the retrieved context.
- If you must indicate uncovered aspects, do not treat as uncovered procedure_ids, CIGs, amounts, or durations that are present in the fact sheet.
- Do not merge different procedures unless the question explicitly requires a comparison.
- If the main procedure references another procedure, a framework agreement, a platform, an external system or a linked contract, describe only the relationship supported by the sources. Do not transfer amounts, CIGs, durations, locations, SLAs or obligations from the linked procedure to the main procedure without precise evidence.
- Do not cite article numbers from the civil code, laws, decrees, or determinations if the exact citation does not appear in the retrieved sources. In the absence of a source, describe the legal effect without the article number.
- Treat the thematic blocks of definitive guarantee, indemnity, and anti-corruption obligations as a single section: do not duplicate them under different headings.
- Do not repeat headings, paragraphs, or introductions.
- Respond in the SAME LANGUAGE as the question.
Output ONLY the answer text, no labels, no meta-commentary.
[END RULES]

Retrieved context:
{context}

Question:
{query}

{response_constraints}

Answer:
<!-- prompt:end -->
