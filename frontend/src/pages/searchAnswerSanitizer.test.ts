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
});
