# Context Quality Lexicon (EN)

Language tokens used by `context_quality` to: recognize numeric/legal
facts worth preserving during compression (`_NUMERIC_OR_LEGAL_RE`), detect
tender-overview queries (`_BROAD_TENDER_QUERY_RE`), expand tender query
terms (`_TENDER_OVERVIEW_TERMS`) and filter Italian stopwords
(`_QUERY_STOPWORDS`).

The regex structure (numeric skeleton, lookaround) stays in
`localization.get_context_quality`; only the language-varying tokens live
here. Section bodies stay identical between `it/` and `en/` (only the
header prose differs): they match Italian tender text and queries
regardless of the UI language.

## Duration Unit Words

- giorni
- mesi
- anni
- days
- months
- years

## Money Currency Words

- euro
- eur

## Broad Query Verbs

- riassum\w*
- sintetizza\w*
- overview
- panoramica
- spiega\w*
- descriv\w*
- analizz\w*
- dettagli?\b
- elenco
- lista

## Tender Noun Markers

- gara
- bando
- capitolato
- disciplinare
- procedura
- lotto
- tender
- rfp
- appalto

## Tender Overview Terms

- capitolato
- cloud
- contratto
- durata
- fornitore
- fornitura
- infrastruttura
- oggetto
- perimetro
- qualificazione
- requisiti
- servizi
- sistema

## Query Stopwords

- che
- chi
- cosa
- come
- con
- dei
- del
- della
- delle
- dimmi
- gara
- gli
- per
- quale
- quali
- richiesta
- sono
- una
