# Guardrail Patterns (IT)

Frammenti regex linguistici usati dai guardrail deterministici. La struttura
(skeleton numerico, lookbehind, gruppi di cattura) resta in
`localization.get_guardrail_patterns`; qui si esternalizzano solo i token
italiani che variano per lingua. Ogni voce è un frammento regex valido
(case-insensitive applicato in compilazione).

I corpi delle sezioni restano identici tra `it/` ed `en/` (cambia solo la
prosa di intestazione): questi pattern matchano testo di gara e risposte
italiane indipendentemente dalla lingua della UI.

## Day Word

- giorn[oi]

## Day Plural Word

- giorni

## Month Word

- mesi

## Year Word

- anni

## Negation Word

- non

## Unverified Status Words

- verificato
- rilevato

## Unverified Adjective

- verificat[oa]

## Procedure Id Field Label

- ID\s+procedura

## Procedure Id Prefix Alternatives

- ID(?:\s+procedura)?
- procedura

## Procedure Id Synonyms

- ID\s+procedura
- identificativo
- procedure_id

## Money Currency Words

- euro
- eur

## Money Million Words

- milion[ei]
- mln

## Money Of Connector

- di

## Address Pattern

- via\s+[a-zàèéìòù'\.\s]+\s+\d+

## Service Location Lead

- luogo\s+di\s+svolgimento\s+del\s+servizio

## Copula Forms

- è
- e'
- e

## Service Location Article

- la

## Region Word

- Regione

## Placeholder Day Leads

- entro
- fino a
- non oltre

## Article Words

- art\.?
- articolo
- articoli

## Article Word Compact

- art(?:icol[oi])?\.?

## Civil Code Phrase

- c\.?c\.?
- del\s+codice\s+civile

## Duration Range Lead

- tra

## Duration Range Articles

- i
- gli

## Duration Range Connectors

- e
- a
- ed

## Money Range Verbs

- oscilla(?:no)?
- varia(?:no)?
- compres[oi]
- variabil[ei]

## Money Range Connectors

- e
- ed

## Contamination Markers

- gara\s+collegata
- procedura\s+collegata
- accordo\s+quadro\s+richiamato
- contratto\s+collegato
- sistema\s+esterno
- piattaforma\s+esterna
- allegato\s+tecnico
- appendice
- riferimento\s+ad\s+altra\s+procedura

## Identity Markers

- procedura\s+principale
- procedura\s+di\s+riferimento
- sistema\s+collegato
- piattaforma\s+collegata

## False Missing Markers

- aspetti\s+non\s+coperti
- non\s+(?:(?:risulta(?:no)?|sono|e'|è)\s+)?(?:disponibil[ei]|rilevat[ioae]|copert[ioe])
- non\s+(?:emerge|emergono|risulta(?:no)?)
- mancan[oa]
- assen[zt][aei]

## Field Duration Words

- durata
- durate
- mesi
- termine
- tempi

## Field Amount Words

- import[oi]
- valor[ei]
- base\s+d['’]?asta
- economi(?:co|ci|ca|che)

## Field Location Words

- sed[ei]
- luogh[oi]
- localizzazion[ei]
- territorio
- esecuzione
