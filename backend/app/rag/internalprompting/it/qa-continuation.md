# QA Continuation Prompt (IT)

Template usato per estendere una risposta long-form già iniziata. I segnaposto
`{query}`, `{context}` e `{current_answer_tail}` vengono interpolati a runtime.

<!-- prompt:start -->
ISTRUZIONI IMPORTANTI:
- Devi rispondere nella STESSA LINGUA della domanda dell'utente.
- Stai continuando una risposta gia iniziata.
- Non ricominciare dall'inizio.
- Non ripetere sezioni o frasi gia scritte.
- Non commentare il numero di parole.
- Non scrivere titoli o frasi come "Continuazione della risposta".
- Non citare o copiare etichette interne del prompt.
- Se nel draft trovi formule OCR rovinate o simboli incompleti, non copiarli alla cieca: riscrivi il passaggio in forma corretta oppure spiegalo in prosa accurata.
- Aggiungi solo contenuto nuovo, sostanziale e coerente con quanto gia scritto.

DOMANDA UTENTE:
{query}

CONTESTO RECUPERATO:
{context}

PARTE FINALE GIA SCRITTA (solo riferimento, non copiarla):
{current_answer_tail}

Ora continua direttamente dal punto in cui la risposta si e interrotta.
Scrivi solo il seguito naturale della risposta, iniziando direttamente dal contenuto mancante.
<!-- prompt:end -->
