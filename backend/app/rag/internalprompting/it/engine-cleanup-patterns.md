# Engine Cleanup Patterns (IT)

Pattern usati da `_clean_generation_artifacts` per rifiniture testuali
italiane (riparazioni OCR), prefissi meta da saltare durante il pulizia
delle continuazioni e regex per identificare valori numerici critici o
spezzati.

## OCR Replacements

Ogni riga ha formato `PATTERN || REPLACEMENT` (separatore: due pipe).
Pattern raw regex, applicato case-insensitive.

- \bulter\s+ulteriore\b || ulteriore
- \bMigliore\s+\(MAM\) || Migliorativa (MAM)
- \bInfrastruttura\s+Digitali\b || Infrastrutture Digitali
- \bCIG\s*:?\s*B33988ECF[A-Z0-9]?\b || CIG B33988ECF2

## Continuation Skip Prefixes

- ecco la continuazione
- continuo la risposta

## Broken Numeric Patterns

- \bentro\s+giorni\b
- \bfino\s+a\s+giorni\b
- \bID:\s*CH\b(?!\d)

## Critical Numeric Patterns

- \b\d+\s*giorni\b
- \b\d+[\.,]\d+[\.,]\d+\b
- \beuro\s*\d
- \bCIG\s+[A-Z0-9]+
- \bSLA\b
- \bpenale\b
