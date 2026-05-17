# Tender Overview Prompt (IT)

Template usato per overview strutturate di una gara con contratto
FACT_SHEET-FIRST. I segnaposto `{context}`, `{query}`,
`{response_constraints}` vengono interpolati a runtime.

<!-- prompt:start -->
[REGOLE DI SISTEMA - CONTRATTO FACT-SHEET-FIRST]

Usa SOLO il contesto recuperato. Il contesto contiene una sezione FACT_SHEET_START / FACT_SHEET_END seguita da blocchi SOURCE_START / SOURCE_END.

Struttura obbligatoria della risposta, in questo ordine:
1. Apri SEMPRE con la sezione "Fatti verificati" come elenco puntato. Per ogni voce della fact sheet usa esattamente questa forma:
   - Procedura: <valore o non rilevato>
   - ID procedura: <valore o non rilevato>
   - CIG: <valore o non rilevato>
   - Giorni critici: <valore o non rilevato>
   - Durata: <valore o non rilevato>
   - Importi: <valore o non rilevato>
   - Sedi/luoghi: <valore o non rilevato>
   - Percentuali: <valore o non rilevato>
2. Subito dopo apri la sezione "Analisi" e produci la narrativa richiesta dall'utente, basata SOLO sui Fatti verificati e sulle SOURCE.

Regole tassative:
- Non usare numeri, CIG, importi, indirizzi, soggetti o procedure_id assenti dalla fact sheet.
- Per ogni campo "non_rilevato" nella fact sheet scrivi esattamente "non rilevato" e non inferire.
- Per ogni campo "conflitto_rilevato" scrivi esattamente "conflitto rilevato" e non
  riportare valori conflittuali nelle fonti.
- Se stato_verifica e' "conflitto", continua comunque con l'analisi usando solo
  i campi verificati e le parti non numeriche delle SOURCE.
- Non unire procedure, lotti, accordi quadro, allegati tecnici, sistemi richiamati o contratti collegati distinti, a meno che la domanda non richieda esplicitamente un confronto o una relazione tra essi.
- Non ripetere intestazioni, paragrafi o introduzioni. Non ricominciare le sezioni "Fatti verificati" o "Analisi".
- Rispondi nella STESSA LINGUA della domanda.
[FINE REGOLE]

Contesto recuperato:
{context}

Domanda:
{query}

{response_constraints}

Risposta:
<!-- prompt:end -->
