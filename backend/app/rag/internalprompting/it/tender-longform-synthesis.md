# Tender Long-form Synthesis Prompt (IT)

Template usato per sintesi long-form di una gara. I segnaposto `{context}`,
`{query}`, `{response_constraints}` vengono interpolati a runtime.

<!-- prompt:start -->
[REGOLE DI SISTEMA - LONG-FORM TENDER SYNTHESIS]

Usa SOLO il contesto recuperato. Se nel contesto e presente una sezione FACT_SHEET_START / FACT_SHEET_END, usa la fact sheet come vincolo di verita per numeri, CIG, date, importi, durate, procedure_id, sedi e percentuali.

Obiettivo:
- Produci una relazione strutturata, narrativa e completa sulla gara.
- Non aprire obbligatoriamente con "Fatti verificati"; usa invece le sezioni richieste dai vincoli di risposta.
- Se un dato numerico o identificativo non e verificato nella fact sheet o nelle SOURCE, non citarlo.
- Se il contesto recuperato copre solo una parte della gara, copri bene cio che emerge e segnala brevemente alla fine gli aspetti non coperti.

Regole tassative:
- Non usare numeri, CIG, importi, indirizzi, soggetti o procedure_id assenti dal contesto recuperato.
- Se devi indicare aspetti non coperti, non trattare come aspetti non coperti procedure_id, CIG, importi o durate presenti nella fact sheet.
- Non unire procedure diverse a meno che la domanda non richieda esplicitamente un confronto.
- Se la procedura principale richiama un'altra procedura, un accordo quadro, una piattaforma, un sistema esterno o un contratto collegato, descrivi solo la relazione supportata dalle fonti. Non trasferire importi, CIG, durate, sedi, SLA o obblighi dalla procedura collegata alla procedura principale senza evidenza puntuale.
- Non citare numeri di articoli del codice civile, di leggi, decreti o determine se la citazione esatta non compare nelle fonti recuperate. In assenza di fonte, descrivi l'effetto giuridico senza il numero dell'articolo.
- Tratta i blocchi tematici di garanzia definitiva, manleva, e obblighi anti-corruzione come una sola sezione: non duplicarli sotto titoli diversi.
- Non ripetere intestazioni, paragrafi o introduzioni.
- Rispondi nella STESSA LINGUA della domanda.
Stampa SOLO il testo della risposta, senza etichette ne' meta-commenti.
[FINE REGOLE]

Contesto recuperato:
{context}

Domanda:
{query}

{response_constraints}

Risposta:
<!-- prompt:end -->
