# Guardrail Lexicon (EN)

Anchor and keyword lists used by the deterministic guardrails to classify
a chunk's procedure (`classify_chunk_procedure`), detect thematically
duplicated paragraphs (`_duplicate_paragraph_failures`) and recognize
comparison requests (`_allows_comparison`).

These lists are matched against Italian tender text and the generated
answer, so they are intrinsically lexical and the section bodies stay
identical between `it/` and `en/` (only the header prose differs). The
procedure labels (OSCAT/SCT) and theme keys (garanzie/manleva/integrita)
remain canonical in code: only the members are externalized here.

## Semantic Theme garanzie

- garanzia
- garanzie
- garante
- svincolat
- svincolo
- escussione
- fideiussoria
- cauzione
- cauzioni

## Semantic Theme manleva

- manlevare
- manleva
- indenni
- intellettuale
- proprieta
- proprietà
- azione legale
- spese di giudizio

## Semantic Theme integrita

- corruzione
- anticorruzione
- segnalare
- segnalazione
- prefettura
- giudiziaria
- integrita
- integrità
- illecita
- illecito
- risoluzione espressa

## Comparison Markers

- confront
- compar
- distingu
- separ
