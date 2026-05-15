# Prompt Leakage Labels & Instructions (IT)

Frammenti regex usati per rilevare leakage del prompt interno nel testo
generato dall'LLM. Ogni gruppo è una bullet list di alternative regex
spliced verbatim in `(?:alt1|alt2|...)`. Le sezioni `Instruction Lines`
contengono regex complete (uno per riga, già `^...$` ancorati implicitamente).

## Plain Labels

- draft ending
- (?:task|compito)(?=\s*:|$)
- retrieved context
- user question
- response constraints
- istruzioni importanti
- domanda utente
- contesto recuperato
- parte finale gia scritta(?:\s*\([^)]*\))?

## Plain Answer Labels

- own answer
- your answer

## Heading Only Answer Labels

- answer(?:\s*\([^)]*\))?
- own answer
- your answer

## Loop Labels

- own answer
- your answer
- answer
- user question
- retrieved context
- response constraints
- draft ending
- task
- compito

## Inline Trigger Labels

- compito
- task
- domanda utente
- contesto recuperato
- parte finale gia scritta(?:\s*\([^)]*\))?
- retrieved context
- user question
- response constraints
- istruzioni importanti

## User Query Verbs

- fai
- fammi
- dammi
- dimmi
- spiega
- descrivi
- analizza
- riassumi
- elenca
- fornisci
- scrivi
- prepara
- genera
- trova
- cerca
- indica
- mostra
- confronta
- valuta

## Instruction Lines

- scrivi solo il seguito naturale della risposta, iniziando direttamente dal contenuto mancante\.?
- continua solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\. inizia direttamente con il testo mancante\.?
- provide a helpful, accurate answer based on the available context\.?
- respond in the same language as the user(?:'s)? question\.?
- always respond in the same language as the user(?:'s)? question\.?
- use only the retrieved context\.?
- output only the answer text, no labels, no meta-commentary\.?
- if the context doesn't contain enough information, say so clearly\.?
- ricorda: rispondi nella stessa lingua della domanda sopra!?
- inizia direttamente con la risposta finale, senza copiare intestazioni o sezioni del prompt\.?
- ora continua direttamente dal punto in cui la risposta si e interrotta\.?
- ora completa solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\.?
- inizia direttamente con il testo mancante\.?
- - devi rispondere nella stessa lingua della domanda dell'utente\.?
- - stai continuando una risposta gia iniziata\.?
- - devi completare solo la frase o il concetto finale rimasto interrotto\.?
- - non ricominciare dall'inizio\.?
- - non ripetere (?:sezioni o frasi gia scritte|il testo gia scritto)\.?
- - non commentare il numero di parole\.?
- - non scrivere titoli o frasi come "continuazione della risposta"\.?
- - non citare o copiare etichette interne del prompt\.?
- - aggiungi solo contenuto nuovo, sostanziale e coerente con quanto gia scritto\.?
- - non iniziare un nuovo paragrafo, una nuova sezione o un nuovo argomento\.?
- - scrivi al massimo 60 parole\.?
- - chiudi con una frase completa e coerente\.?
