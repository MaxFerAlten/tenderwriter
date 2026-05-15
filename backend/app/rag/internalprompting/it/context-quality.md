# Context Quality Lexicon (IT)

Token linguistici usati da `context_quality` per: riconoscere fatti
numerici/legali da preservare in compressione (`_NUMERIC_OR_LEGAL_RE`),
rilevare query di panoramica gara (`_BROAD_TENDER_QUERY_RE`), espandere i
termini di query per gare (`_TENDER_OVERVIEW_TERMS`) e filtrare le stopword
italiane (`_QUERY_STOPWORDS`).

La struttura regex (skeleton numerico, lookaround) resta in
`localization.get_context_quality`; qui solo i token che variano per lingua.
I corpi delle sezioni restano identici tra `it/` ed `en/` (cambia solo la
prosa di intestazione): matchano testo di gara e query italiane
indipendentemente dalla lingua della UI.

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

- acn
- capitolato
- cctt
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
