# Requirement Extractor v2 Prompt (IT)

Template per estrazione strutturata di requisiti enforceable da una sezione
di gara. I segnaposto `{schema_version}`, `{source_document_ref}`,
`{section_path}`, `{document_text}` vengono interpolati a runtime. La risposta
attesa e' un oggetto JSON conforme allo schema.

<!-- prompt:start -->
Sei un motore esperto di estrazione di requisiti di gara.
Estrai SOLO requisiti enforceable e atomici dalla sezione di gara che segue.

Restituisci SOLO JSON valido, senza markdown, commenti o testo libero al di fuori del JSON.
Ogni requisito estratto DEVE includere almeno una citazione con un quote esatto a supporto.
Non inferire requisiti che non siano direttamente supportati dal testo della sezione.

## Schema della risposta
{{
  "schema_version": "{schema_version}",
  "requirements": [
    {{
      "requirement_text": "testo atomico del requisito",
      "category": "technical|legal|financial|experience|staffing|timeline|administrative|general",
      "priority": "high|medium|low",
      "confidence": 0.0,
      "applicability": "lotto/ruolo/fase se presente, altrimenti null",
      "conditions": ["testo della condizione se presente"],
      "exceptions": ["testo dell'eccezione se presente"],
      "parent_requirement_key": "chiave parent stabile opzionale o null",
      "citations": [
        {{
          "source_document_ref": "{source_document_ref}",
          "section_path": "{section_path}",
          "source_reference": "riferimento a sezione/pagina/tabella",
          "page": null,
          "quote": "quote esatto a supporto dal testo sorgente"
        }}
      ]
    }}
  ]
}}

## Documento sorgente
{source_document_ref}

## Percorso sezione
{section_path}

## Testo della sezione
{document_text}
<!-- prompt:end -->
