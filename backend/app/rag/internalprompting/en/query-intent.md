# Query Intent Keywords (EN)

English keyword groups consumed by the engine to classify query intent, clean
text for retrieval, and identify noisy headings/tokens. Each group is a bullet
list of regex fragments — bullets are NOT escaped: they are spliced verbatim
into `(?:alt1|alt2|...)`.

## Word Count Units

- words
- words?

## Line Count Units

- lines
- lines?

## Expanded Explanation Verbs

- summari[sz]\w*
- explain\w*
- describe\w*
- analyz\w*
- analys\w*
- elaborate\w*
- detail\w*

## Summary Intent Markers

- summari[sz]\w*
- overview
- summary
- explain\w*
- describe\w*
- analyz\w*
- analys\w*
- elaborate\w*
- exhaustiv\w*
- detailed?

## Structured Overview Markers

- list
- points?
- key\s+points
- detailed?
- complete
- structured
- exhaustiv\w*
- thorough\w*

## Tender Documents

- tender
- rfp
- procurement
- bid
- bidding
- procedure
- lot
- notice
- specification

## Tender Definition Phrases

- what\s+is
- what's
- define
- definition
- how\s+does\s+it\s+work

## Tender Indefinite Articles

- a
- an

## Tender Indefinite Nouns

- tender
- rfp
- procurement
- bid
- procedure
- lot
- notice
- contract

## Tender Concept Phrases

- open\s+procedure
- award\s+criteri(?:on|a)
- public\s+tender
- public\s+procurement
- procurement\s+code

## Retrieval Intent Verbs

- give
- show
- write
- prepare
- generate
- summari[sz]\w*
- overview
- summary
- explain\w*
- describe\w*
- analyz\w*
- analys\w*
- elaborate\w*
- list
- points?
- key\s+points
- detailed?
- complete
- structured
- exhaustiv\w*
- all\b

## Retrieval Stopwords

- a
- an
- the
- of
- in
- on
- at
- by
- for
- with
- to
- from

## Math Markers

- latex
- la\s*tex
- formula
- formulas
- equation
- equations
- math
- mathematics
- mathematical\s+symbols

## Length Meta Units

- words
- lines

## Length Meta Adjectives

- enough
- insufficient
- too\s+few
- too\s+many
- count
- word\s+count

## Integrity Pact Context

- integrity\s+pact
- integrity
- anti-?corruption
- economic\s+threshold

## Integrity Pact Query

- integrity\s+pact
- integrity
- anti-?corruption
- threshold

## Continuation Headings

- continuation
- proseguimento
- continuazione

## Singular Day Word

- day

## Sentence End Tokens

- a
- an
- and
- as
- at
- by
- for
- from
- in
- into
- of
- on
- or
- the
- to
- with

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
