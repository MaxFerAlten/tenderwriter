# QA Sentence Closure Prompt (IT)

Template usato per chiudere una frase o un concetto rimasto interrotto a fine
generazione. I segnaposto `{query}`, `{context}` e `{current_answer_tail}` vengono
interpolati a runtime.

<!-- prompt:start -->
ISTRUZIONI IMPORTANTI:
- Devi rispondere nella STESSA LINGUA della domanda dell'utente.
- Devi completare solo la frase o il concetto finale rimasto interrotto.
- Non iniziare un nuovo paragrafo, una nuova sezione o un nuovo argomento.
- Non ripetere il testo gia scritto.
- Scrivi al massimo 60 parole.
- Chiudi con una frase completa e coerente.
- Non citare o copiare etichette interne del prompt.

DOMANDA UTENTE:
{query}

CONTESTO RECUPERATO:
{context}

PARTE FINALE GIA SCRITTA (solo riferimento, non copiarla):
{current_answer_tail}

Ora completa solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto.
Inizia direttamente con il testo mancante.
<!-- prompt:end -->
