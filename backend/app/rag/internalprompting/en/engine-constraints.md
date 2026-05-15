# Engine Response Constraints (EN)

Constraints emitted by `_build_response_constraints` to build the
`{response_constraints}` section interpolated into prompt templates.
Sections are bullet lists of complete strings; templates that require
dynamic values use Python placeholders `{requested_label}`, `{min_words}`,
`{max_words}`, `{target_words}` interpolated at runtime.

## General Constraints

- Answer the user's question directly without meta preambles.
- Do not just count or comment on the word count of your answer.
- If you sense you are near the output limit, always close the current sentence or concept before stopping.
- Never reproduce <doc> tags, ### section titles, or headings present in the context.
- If the same concept appears in multiple sources, cite it once in the most appropriate position.
- Do not repeat blocks of text already written in the answer.

## Length Target Constraints

- The user requested approximately {requested_label}.
- Write a complete answer between roughly {min_words} and {max_words} words.
- Get as close as possible to the target of {target_words} words without stopping much earlier.
- If needed, expand with explanations, examples, and useful logical steps, without filler or repetition.

## Lines Mode Constraint

- Interpret the request in lines as a very long and detailed answer, without arguing about the feasibility of the requested number.

## No Length Target Constraint

- Keep the answer proportionate to the request.

## Expanded Explanation Constraint

- If the context allows, develop an answer slightly more complete than the minimum, covering definition, context, and key points instead of stopping at a single short sentence.

## Broad Summary Constraint

- If the retrieved context covers only part of the tender, still provide the best possible synthesis of the emerging points and add only at the end a short note about the uncovered aspects, instead of stopping by saying the context is insufficient.

## Structured Overview Sections

- 1. Object and scope
- 2. Technological architecture
- 3. Critical operational phases
- 4. Contractual risk points
- 5. Multi-party governance

## Structured Overview Heading

- Organize the answer in these exact sections:

## Structured Overview Constraints

- Write each section in cohesive narrative prose, with complete sentences and logical transitions between details.
- Do not restart from the introduction when moving to a new section.
- Do not repeat the same paragraph or concept across multiple sections.
- Consolidate guarantees, deposits, penalties, and contractual obligations into a single contractual section, without repeating the same information in multiple places.
- Every numeric value must appear exactly as found in the context.
- If a subject, organization, platform, penalty, or deadline is not in the context, write: not available in the supplied documents.
- Do not introduce names absent from the retrieved context.
- Do not copy placeholders, isolated slashes, incomplete dates, or clearly broken OCR fragments.
- If a detail is not clear enough in the context, omit it or briefly flag it as data not clearly emerged, without inventing it.

## Math Rendering Constraints

- When reporting formulas or mathematical symbols, rewrite them in readable and consistent mathematical notation.
- Do not copy corrupt OCR fragments, incomplete pseudo-LaTeX, or clearly broken formulas from the context.
- If the context contains a damaged formula, explain the correct mathematical meaning instead of inventing symbols.
