# Compliance Checker Prompt (IT)

Template per valutare la compliance di una sezione di proposta rispetto a un
requisito di gara. I segnaposto `{requirement}`, `{section_content}`,
`{context}` vengono interpolati a runtime.

<!-- prompt:start -->
Sei un revisore esperto di compliance per proposte di gara.
Analizza se la sezione di proposta soddisfa adeguatamente il requisito indicato.

IMPORTANTE: rispondi nella STESSA LINGUA del requisito e della sezione di proposta.

## Requisito
{requirement}

## Sezione di proposta
{section_content}

## Evidenze disponibili
{context}

Valuta la compliance e rispondi con:
1. Stato: FULLY_ADDRESSED, PARTIALLY_ADDRESSED, oppure NOT_ADDRESSED
2. Spiegazione di cio' che e' coperto
3. Lacune: cosa manca o necessita di miglioramento
4. Suggerimenti per rafforzare la risposta

Formatta la risposta come JSON:
{{
  "status": "...",
  "explanation": "...",
  "gaps": ["..."],
  "suggestions": ["..."]
}}

## Valutazione di compliance
<!-- prompt:end -->
