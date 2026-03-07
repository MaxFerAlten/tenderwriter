# Fix Llama Server - Errore 500 "Failed to parse input"

## Problema Identificato

Il llama.cpp server ha un bug con l'endpoint `/v1/chat/completions` che causa errori di parsing JSON:
```
"Failed to parse input at pos XXX"
```

## Root Cause

L'endpoint OpenAI-compatible `/v1/chat/completions` del llama.cpp server non riesce a parsare correttamente le richieste JSON, anche quando sono valide.

## Soluzione Implementata

Modificato `backend/app/rag/generator.py` per usare l'endpoint nativo `/completion` invece di `/v1/chat/completions`:

### Prima (non funzionante):
```python
POST http://llama-tender:8080/v1/chat/completions
{
  "model": "qwen3.5-9b",
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 512
}
```

### Dopo (funzionante):
```python
POST http://llama-tender:8080/completion
{
  "prompt": "...",
  "n_predict": 512,
  "temperature": 0.3,
  "stop": ["</s>", "<|im_end|>", "<|endoftext|>"]
}
```

## Modifiche Applicate

1. **Endpoint**: `/v1/chat/completions` → `/completion`
2. **Parametri**: 
   - `messages` → `prompt` (stringa diretta)
   - `max_tokens` → `n_predict`
   - Aggiunto `stop` tokens per terminazione corretta
3. **Response parsing**: 
   - `data["choices"][0]["message"]["content"]` → `data["content"]`
   - `data["usage"]["prompt_tokens"]` → `data["tokens_evaluated"]`
   - `data["usage"]["completion_tokens"]` → `data["tokens_predicted"]`

## Test

```bash
# Test endpoint /completion (funziona)
docker exec tw-llama-tender curl -X POST http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","n_predict":50}'

# Test endpoint /v1/chat/completions (non funziona)
docker exec tw-llama-tender curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"max_tokens":50}'
```

## Note

- Questo è un workaround per un bug noto del llama.cpp server
- L'endpoint `/completion` è più stabile e performante
- Il formato è leggermente diverso ma funzionalmente equivalente
- Streaming supportato con `"stream": true`

## Riferimenti

- llama.cpp issue tracker: https://github.com/ggerganov/llama.cpp/issues
- Documentazione endpoint: https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md
