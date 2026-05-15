# Query Intent Keywords (IT)

Frammenti regex e liste di parole chiave usati dall'engine per classificare
l'intento delle query, ripulire il testo per il retrieval e individuare
heading/token rumorosi. Ogni gruppo è una lista bullet di frammenti — i bullet
NON vengono escapati: sono inseriti tali e quali in `(?:alt1|alt2|...)`.

## Word Count Units

- parole
- words
- palabras

## Line Count Units

- righe
- lines
- lineas

## Expanded Explanation Verbs

- riassum\w*
- spiega\w*
- descriv\w*
- sintetizza\w*
- summari[sz]\w*
- explain\w*
- describe\w*
- analizz\w*
- approfond\w*

## Summary Intent Markers

- riassum\w*
- sintetizza\w*
- summari[sz]\w*
- overview
- panoramica
- spiega\w*
- descriv\w*
- analizz\w*
- approfond\w*
- esaustiv\w*
- dettagli?\b

## Structured Overview Markers

- elenco
- lista
- punti?\s+chiave
- dettagli?\b
- dettagliat\w*
- complet\w*
- strutturat\w*
- esaustiv\w*
- approfondit\w*

## Tender Documents

- gara
- bando
- capitolato
- disciplinare
- documentazione
- procedura
- lotto
- tender
- rfp
- avviso

## Tender Definition Phrases

- cos\s*['’`]?\s*[eè]
- che\s+cosa\s+(?:e|è)
- what\s+is
- what's
- definisci
- definizione
- come\s+funziona

## Tender Indefinite Articles

- un
- una
- uno
- a
- an

## Tender Indefinite Nouns

- gara
- bando
- capitolato
- disciplinare
- procedura
- lotto
- tender
- rfp
- avviso
- appalto

## Tender Concept Phrases

- procedura\s+aperta
- criteri?o\s+di\s+aggiudicazione
- gara\s+pubblica
- appalto\s+pubblico
- codice\s+(?:dei\s+)?appalti

## Retrieval Intent Verbs

- fai
- fammi
- dammi
- fornisci
- scrivi
- prepara
- genera
- riassum\w*
- sintetizza\w*
- summari[sz]\w*
- overview
- panoramica
- spiega\w*
- descriv\w*
- analizz\w*
- approfond\w*
- elenco
- lista
- punti?\s+chiave
- dettagli?\b
- dettagliat\w*
- complet\w*
- strutturat\w*
- esaustiv\w*
- tutti?\b

## Retrieval Stopwords

- un
- una
- uno
- i
- gli
- del
- della
- delle
- dei
- degli
- dello
- di
- da
- dei
- della

## Math Markers

- latex
- la\s*tex
- formula
- formule
- equation
- equazioni
- matematica
- matematiche
- simboli matematici
- math

## Length Meta Units

- parole
- words
- righe
- lines

## Length Meta Adjectives

- sufficienti
- insufficienti
- troppo pochi
- troppo poche
- too few
- enough
- conteggio
- numero di parole

## Integrity Pact Context

- patto\s+di\s+integrit
- integrit[aà]
- anticorruzione
- soglie\s+economiche

## Integrity Pact Query

- patto\s+di\s+integrit
- integrit[aà]
- anticorruzione
- soglie

## Continuation Headings

- continuazione
- continuation
- proseguimento

## Singular Day Word

- giorno

## Sentence End Tokens

- a
- ad
- al
- alla
- allo
- an
- and
- as
- con
- da
- de
- del
- della
- di
- e
- for
- fra
- from
- il
- in
- into
- la
- le
- lo
- nel
- nella
- of
- o
- on
- or
- per
- su
- the
- to
- tra
- un
- una
- uno
- verso
- with
- y

## Prompt Garbage Tokens

- a
- answer
- as
- assistant
- context
- constraints
- language
- only
- output
- own
- question
- response
- retrieved
- s
- same
- system
- the
- user
- users
