# Requirement Analyzer Prompt (IT)

Template per analizzare un documento di gara/RFP ed estrarne i requisiti.
Il segnaposto `{document_text}` viene interpolato a runtime. La risposta
attesa e' un array JSON.

<!-- prompt:start -->
Sei un esperto nell'analisi di documenti di gara/RFP.
Estrai e categorizza tutti i requisiti dal testo del documento di gara che segue.

IMPORTANTE: rispondi nella STESSA LINGUA del documento di gara.

## Documento di gara
{document_text}

Per ogni requisito individuato, fornisci:
1. Il testo del requisito (esatto o parafrasato fedelmente)
2. Categoria (technical, financial, legal, experience, staffing, timeline, ecc.)
3. Priorita' (must-have, should-have, nice-to-have)

Formatta la risposta come array JSON:
[
  {{
    "text": "descrizione del requisito",
    "category": "categoria",
    "priority": "must-have|should-have|nice-to-have"
  }}
]

## Requisiti estratti
<!-- prompt:end -->
