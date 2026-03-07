# Test RAG con Llama Server

## Verifica Configurazione

✅ llama-tender: http://localhost:8080 (per TenderWriter RAG)
✅ llama-opencode: http://localhost:8081 (per OpenCode)
✅ Backend configurato per usare llama-tender
✅ Health check RAG: OK

## Test da Frontend

Prova ora a fare una query dal frontend. Se ottieni ancora errore 500:

```bash
# Monitora i log del backend in tempo reale
docker logs -f tw-backend

# In un altro terminale, fai la query dal frontend
```

## Test Manuale API

```bash
# Test diretto dell'endpoint RAG (sostituisci YOUR_TOKEN con il tuo JWT)
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "query": "Test query",
    "mode": "qa",
    "temperature": 0.7
  }'
```

## Configurazione Attuale

- **Backend**: usa `llama_server_url = http://llama-tender:8080/v1`
- **Modello**: `qwen2.5-coder-7b` (Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf)
- **API**: OpenAI-compatible (`/v1/chat/completions`)

## Note

Il modello Qwen2.5-Coder-7B è ottimizzato per code, non per RAG su documenti.
Per migliorare le performance del RAG, considera di scaricare un modello più adatto come:
- Qwen2.5-32B-Instruct (migliore per RAG)
- Mistral-7B-Instruct (più leggero, buono per RAG)
