const PROMPT_LEAKAGE_LINE_RE = /^\s*(?:(?:#{1,6}\s*)(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|answer(?:\s*\([^)]*\))?|own answer|your answer)(?:\s|:|$)|(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|own answer|your answer)(?:\s|:|$)).*$/i;
const PROMPT_LEAKAGE_INLINE_RE = /\s+(?:#{1,6}\s*(?:draft ending|(?:task|compito)(?=\s*:|$)|retrieved context|user question|response constraints|istruzioni importanti|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|own answer|your answer|(?<!own )(?<!your )answer(?:\s*\([^)]*\))?)(?:\s|:|$)|(?:compito|task|domanda utente|contesto recuperato|parte finale gia scritta(?:\s*\([^)]*\))?|retrieved context|user question|response constraints|istruzioni importanti)\s*:).*$/i;
const PROMPT_LEAKAGE_LOOP_RE = /^\s*(?:(?:[A-Za-z]\s+)?(?:own answer|your answer|answer|user question|retrieved context|response constraints|draft ending|task|compito)\s*){3,}\s*$/i;
const PROMPT_OWN_TOKEN_LOOP_RE = /^\s*(?:s\s+)?(?:own\s*){3,}\s*$/i;
const PROMPT_OWN_TOKEN_PREFIX_RE = /^\s*(?:s\s+)?(?:own\s*){3,}/i;
const PROMPT_LEAKAGE_SUFFIX_RE = /\s+(?:(?:[A-Za-z]{1,3}\s+)?(?:own answer|your answer|answer|user question|retrieved context|response constraints|draft ending|task|compito)\s*){3,}$/i;
const DANGLING_CLOSING_BRACE_SUFFIX_RE = /(?<=\w)\s*[}\])]{1,}\s*$/;
const BRACE_ONLY_LINE_RE = /^\s*[}\])]+\s*$/;
const LIKELY_USER_QUERY_START_RE = /^(?:fai\b|fammi\b|dammi\b|dimmi\b|spiega\b|descrivi\b|analizza\b|riassumi\b|elenca\b|fornisci\b|scrivi\b|prepara\b|genera\b|trova\b|cerca\b|indica\b|mostra\b|confronta\b|valuta\b)/i;
const PROMPT_LEAKAGE_INSTRUCTION_RES = [
    /^scrivi solo il seguito naturale della risposta, iniziando direttamente dal contenuto mancante\.?$/i,
    /^continua solo quanto basta per chiudere in modo naturale l'ultima frase o l'ultimo concetto rimasto interrotto\. inizia direttamente con il testo mancante\.?$/i,
    /^provide a helpful, accurate answer based on the available context\.?$/i,
    /^respond in the same language as the user(?:'s)? question\.?$/i,
    /^always respond in the same language as the user(?:'s)? question\.?$/i,
    /^use only the retrieved context\.?$/i,
    /^output only the answer text, no labels, no meta-commentary\.?$/i,
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
const PROMPT_GARBAGE_PREFIX_TOKENS = new Set([
    'a',
    'answer',
    'as',
    'assistant',
    'context',
    'constraints',
    'language',
    'only',
    'output',
    'own',
    'question',
    'response',
    'retrieved',
    's',
    'same',
    'system',
    'the',
    'user',
    'users',
]);

function stripPromptGarbagePrefix(text: string): { text: string; trimmed: boolean } {
    const candidate = text.trimStart();
    if (!candidate) {
        return { text: '', trimmed: false };
    }

    const matches = [...candidate.matchAll(/\S+/g)];
    let garbageCount = 0;

    for (const match of matches) {
        const rawToken = match[0];
        let normalized = rawToken
            .replace(/^[ \t\r\n:/\\|#[\](){}<>,.;'"`*\-_=!?]+/, '')
            .replace(/[ \t\r\n:/\\|#[\](){}<>,.;'"`*\-_=!?]+$/, '')
            .toLowerCase()
            .replace(/’/g, "'")
            .replace(/'s/g, 's')
            .replace(/[^a-zà-ÿ]+/g, '');

        if (!normalized || PROMPT_GARBAGE_PREFIX_TOKENS.has(normalized)) {
            garbageCount += 1;
            continue;
        }

        if (garbageCount >= 3) {
            const remainder = candidate.slice(match.index ?? 0).trimStart();
            if (!LIKELY_USER_QUERY_START_RE.test(remainder)) {
                return { text: remainder, trimmed: true };
            }
            return { text: '', trimmed: true };
        }
        return { text: candidate, trimmed: false };
    }

    if (garbageCount >= 3) {
        return { text: '', trimmed: true };
    }
    return { text: candidate, trimmed: false };
}

export function sanitizeSearchAnswer(text: string): string {
    const cleaned = (text || '').trim();
    const keptLines: string[] = [];
    for (const line of cleaned.split(/\r?\n/)) {
        let candidate = line.trimEnd();
        const rawStripped = candidate.trim();
        if (!rawStripped) {
            if (keptLines.length > 0 && keptLines[keptLines.length - 1] !== '') {
                keptLines.push('');
            }
            continue;
        }
        if (PROMPT_LEAKAGE_LINE_RE.test(rawStripped)) {
            continue;
        }
        if (PROMPT_LEAKAGE_LOOP_RE.test(rawStripped)) {
            continue;
        }
        if (PROMPT_OWN_TOKEN_LOOP_RE.test(rawStripped)) {
            continue;
        }
        if (BRACE_ONLY_LINE_RE.test(rawStripped)) {
            continue;
        }
        if (PROMPT_LEAKAGE_INSTRUCTION_RES.some((pattern) => pattern.test(rawStripped))) {
            continue;
        }

        let suffixTrimmed = false;
        let braceTrimmed = false;
        const inlineMatch = PROMPT_LEAKAGE_INLINE_RE.exec(candidate);
        if (inlineMatch && inlineMatch.index >= 0) {
            candidate = candidate.slice(0, inlineMatch.index).trimEnd();
        }
        const suffixMatch = PROMPT_LEAKAGE_SUFFIX_RE.exec(candidate);
        if (suffixMatch && suffixMatch.index >= 0) {
            candidate = candidate.slice(0, suffixMatch.index).trimEnd();
            suffixTrimmed = true;
        }
        const ownPrefixMatch = PROMPT_OWN_TOKEN_PREFIX_RE.exec(candidate);
        if (ownPrefixMatch && ownPrefixMatch.index === 0) {
            candidate = candidate.slice(ownPrefixMatch[0].length).trimStart();
            suffixTrimmed = true;
        }
        const braceSuffixMatch = DANGLING_CLOSING_BRACE_SUFFIX_RE.exec(candidate);
        if (braceSuffixMatch && braceSuffixMatch.index >= 0) {
            candidate = candidate.slice(0, braceSuffixMatch.index).trimEnd();
            braceTrimmed = true;
        }
        const garbagePrefix = stripPromptGarbagePrefix(candidate);
        if (garbagePrefix.trimmed) {
            candidate = garbagePrefix.text;
            suffixTrimmed = true;
        }

        const stripped = candidate.trim();
        if (!stripped) {
            continue;
        }

        if (
            (suffixTrimmed || braceTrimmed)
            && !/[.!?;)"'\]}\u00bb]$/.test(candidate)
            && stripped.split(/\s+/).length >= 3
        ) {
            candidate = `${candidate.replace(/[ ,;:-]+$/, '')}.`;
        }

        keptLines.push(candidate);
    }

    return keptLines.join('\n').trim();
}
