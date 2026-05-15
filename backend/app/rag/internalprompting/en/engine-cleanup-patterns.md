# Engine Cleanup Patterns (EN)

Patterns used by `_clean_generation_artifacts` for English text touch-ups
(OCR repairs), meta prefixes to skip while cleaning continuations, and
regexes used to flag critical or broken numeric values.

## OCR Replacements

Each line is `PATTERN || REPLACEMENT` (separator: double pipe). Pattern is
raw regex applied case-insensitive.

- \bfurth\s+further\b || further
- \bBetter\s+\(MAM\) || Better Offer (MAM)
- \bInfrastructure\s+Digital\b || Digital Infrastructures
- \bCIG\s*:?\s*B33988ECF[A-Z0-9]?\b || CIG B33988ECF2

## Continuation Skip Prefixes

- here is the continuation
- continuing the answer

## Broken Numeric Patterns

- \bwithin\s+days\b
- \bup\s+to\s+days\b
- \bID:\s*CH\b(?!\d)

## Critical Numeric Patterns

- \b\d+\s*days\b
- \b\d+[\.,]\d+[\.,]\d+\b
- \beuros?\s*\d
- \bCIG\s+[A-Z0-9]+
- \bSLA\b
- \bpenalty\b
