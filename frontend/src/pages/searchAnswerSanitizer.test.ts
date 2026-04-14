import { describe, expect, it } from 'vitest';

import { sanitizeSearchAnswer } from './searchAnswerSanitizer';

describe('sanitizeSearchAnswer', () => {
    it('removes inline prompt leakage markers like ## Answer while preserving later answer text', () => {
        expect(
            sanitizeSearchAnswer('Testo utile. ## Answer (in the same language as the question)\nRipresa utile.')
        ).toBe('Testo utile.\nRipresa utile.');
    });

    it('removes line-based prompt leakage markers like COMPITO while preserving later answer text', () => {
        expect(
            sanitizeSearchAnswer(
                'Testo utile.\nCOMPITO:\nContinua solo quanto basta per chiudere in modo naturale l\'ultima frase o l\'ultimo concetto rimasto interrotto. Inizia direttamente con il testo mancante.\nRipresa utile.'
            )
        ).toBe('Testo utile.\nRipresa utile.');
    });

    it('removes repeated own-answer leakage loops while preserving surrounding answer text', () => {
        expect(
            sanitizeSearchAnswer(
                'Dettaglio utile.\nown answer own answer own answer user question own answer own answer\nConclusione utile.'
            )
        ).toBe('Dettaglio utile.\nConclusione utile.');
    });

    it('removes repeated own-answer leakage suffixes from the same line', () => {
        expect(
            sanitizeSearchAnswer(
                'Dettaglio utile sulla gara s own answer own answer own answer user question own answer own answer'
            )
        ).toBe('Dettaglio utile sulla gara');
    });

    it('removes repeated own prefixes and trailing brace junk', () => {
        expect(
            sanitizeSearchAnswer(
                "s own own own own own own\ns own own own own own own L'analisi della gara della Regione Toscana.\nDettaglio finale proporzionalmente}\n}\n}"
            )
        ).toBe("L'analisi della gara della Regione Toscana.\nDettaglio finale proporzionalmente.");
    });

    it('removes same-language garbage prefixes before a valid answer', () => {
        expect(
            sanitizeSearchAnswer(
                "s own language:// a own own own own own own L'analisi della gara della Regione Toscana e dei suoi requisiti principali."
            )
        ).toBe("L'analisi della gara della Regione Toscana e dei suoi requisiti principali.");
    });

    it('drops same-language garbage when no valid answer follows', () => {
        expect(
            sanitizeSearchAnswer(
                's own language:// a own own own own own own fai dei test prima di concludere che va bene'
            )
        ).toBe('');
    });

    it('preserves accented answer starts after garbage prefixes', () => {
        expect(
            sanitizeSearchAnswer(
                "s own language:// a own own own own own own è prevista una cauzione definitiva a carico dell'aggiudicatario."
            )
        ).toBe("è prevista una cauzione definitiva a carico dell'aggiudicatario.");
    });
});
