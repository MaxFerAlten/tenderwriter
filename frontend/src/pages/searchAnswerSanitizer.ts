const PROMPT_LEAKAGE_LINE_RE = /^\s*(?:(?:#{1,6}\s*)(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|answer(?:\s*\([^)]*\))?)(?:\s|:|$)|(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?)(?:\s|:|$)).*$/i;
const PROMPT_LEAKAGE_INLINE_RE = /\s+(?:#{1,6}\s*(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|answer(?:\s*\([^)]*\))?)(?:\s|:|$)|(?:compito|task|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|retrieved context|user question|response constraints|istruzioni importanti)\s*:).*$/i;
const PROMPT_LEAKAGE_INSTRUCTION_RES = [
    /^scrivi solo il seguito naturale della risposta, iniziando direttamente dal contenuto mancante\.?$/i,
    /^continua solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\. inizia direttamente con il testo mancante\.?$/i,
    /^provide a helpful, accurate answer based on the available context\.?$/i,
    /^if the context doesn't contain enough information, say so clearly\.?$/i,
    /^ricorda: rispondi nella stessa lingua della domanda sopra!?$/i,
    /^inizia direttamente con la risposta finale, senza copiare intestazioni o sezioni del prompt\.?$/i,
    /^ora continua direttamente dal punto in cui la risposta si e interrotta\.?$/i,
    /^ora completa solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\.?$/i,
    /^inizia direttamente con il testo mancante\.?$/i,
    /^- devi rispondere nella stessa lingua della domanda dell'utente\.?$/i,
    /^- stai continuando una risposta gia iniziata\.?$/i,
    /^- devi completare solo la frase o il concetto finale rimasto interrotto\.?$/i,
    /^- non ricominciare dall'inizio\.?$/i,
    /^- non ripetere (?:sezioni o frasi gia scritte|il testo gia scritto)\.?$/i,
    /^- non commentare il numero di parole\.?$/i,
    /^- non scrivere titoli o frasi come "continuazione della risposta"\.?$/i,
    /^- non citare o copiare etichette interne del prompt\.?$/i,
    /^- aggiungi solo contenuto nuovo, sostanziale e coerente con quanto gia scritto\.?$/i,
    /^- non iniziare un nuovo paragrafo, una nuova sezione o un nuovo argomento\.?$/i,
    /^- scrivi al massimo 60 parole\.?$/i,
    /^- chiudi con una frase completa e coerente\.?$/i,
] as const;

export function sanitizeSearchAnswer(text: string): string {
    const cleaned = (text || '').trim();
    const keptLines: string[] = [];
    for (const line of cleaned.split(/\r?\n/)) {
        let candidate = line.trimEnd();
        const inlineMatch = PROMPT_LEAKAGE_INLINE_RE.exec(candidate);
        if (inlineMatch && inlineMatch.index >= 0) {
            candidate = candidate.slice(0, inlineMatch.index).trimEnd();
        }

        const stripped = candidate.trim();
        if (!stripped) {
            if (keptLines.length > 0 && keptLines[keptLines.length - 1] !== '') {
                keptLines.push('');
            }
            continue;
        }

        if (PROMPT_LEAKAGE_LINE_RE.test(stripped)) {
            continue;
        }
        if (PROMPT_LEAKAGE_INSTRUCTION_RES.some((pattern) => pattern.test(stripped))) {
            continue;
        }

        keptLines.push(candidate);
    }

    return keptLines.join('\n').trim();
}
