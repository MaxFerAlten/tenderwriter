# Engine Response Constraints (IT)

Vincoli emessi da `_build_response_constraints` per costruire la sezione
`{response_constraints}` interpolata nei prompt template. Le sezioni sono
liste bullet di stringhe complete; nei template che richiedono valori
dinamici, i placeholder Python `{requested_label}`, `{min_words}`,
`{max_words}`, `{target_words}` vengono interpolati a runtime.

## General Constraints

- Rispondi direttamente alla domanda dell'utente senza preamboli meta.
- Non limitarti a contare o commentare il numero di parole della tua risposta.
- Se percepisci di essere vicino al limite di output, chiudi sempre la frase o il concetto in corso prima di terminare.
- Non riprodurre mai tag <doc>, titoli di sezione ### o intestazioni presenti nel contesto.
- Se lo stesso concetto appare in più fonti, citalo una sola volta nella posizione più appropriata.
- Non ripetere blocchi di testo già scritti nella risposta.

## Length Target Constraints

- L'utente ha richiesto circa {requested_label}.
- Scrivi una risposta completa compresa tra {min_words} e {max_words} parole circa.
- Avvicinati il piu possibile al target di {target_words} parole senza fermarti molto prima.
- Se serve, amplia con spiegazioni, esempi e passaggi logici utili, senza riempitivi o ripetizioni.

## Lines Mode Constraint

- Interpreta la richiesta in righe come una risposta molto estesa e dettagliata, senza discutere la fattibilita del numero richiesto.

## No Length Target Constraint

- Mantieni la risposta proporzionata alla richiesta.

## Expanded Explanation Constraint

- Se il contesto lo consente, sviluppa una risposta un po' piu completa del minimo, coprendo definizione, contesto e punti chiave invece di fermarti a una sola frase breve.

## Broad Summary Constraint

- Se il contesto recuperato copre solo una parte della gara, fornisci comunque la migliore sintesi possibile dei punti emersi e aggiungi solo alla fine una breve nota sugli aspetti non coperti, invece di fermarti a dire soltanto che il contesto e insufficiente.

## Structured Overview Sections

- 1. Oggetto e perimetro
- 2. Architettura tecnologica
- 3. Fasi operative critiche
- 4. Punti di rischio contrattuale
- 5. Governance multi-soggetto

## Structured Overview Heading

- Organizza la risposta in queste sezioni esatte:

## Structured Overview Constraints

- Scrivi ogni sezione in prosa narrativa coesa, con frasi complete e transizioni logiche tra i dettagli.
- Non ricominciare dall'introduzione quando passi a una nuova sezione.
- Non ripetere lo stesso paragrafo o lo stesso concetto in piu sezioni.
- Consolida garanzie, cauzioni, penali e obblighi contrattuali in un'unica sezione contrattuale, senza ripetere la stessa informazione in piu punti.
- Ogni valore numerico deve apparire esattamente come trovato nel contesto.
- Se un soggetto, organizzazione, piattaforma, penale o scadenza non e nel contesto, scrivi: non disponibile nei documenti forniti.
- Non introdurre nomi assenti dal contesto recuperato.
- Non copiare segnaposto, slash isolati, date incomplete o frammenti OCR palesemente rotti.
- Se un dettaglio non e abbastanza chiaro nel contesto, omettilo oppure segnalalo in modo breve come dato non chiaramente emerso, senza inventarlo.

## Math Rendering Constraints

- Quando riporti formule o simboli matematici, riscrivili in notazione matematica leggibile e coerente.
- Non copiare frammenti OCR corrotti, pseudo-LaTeX incompleto o formule palesemente spezzate dal contesto.
- Se il contesto contiene una formula danneggiata, spiega il significato matematico corretto invece di inventare simboli.
