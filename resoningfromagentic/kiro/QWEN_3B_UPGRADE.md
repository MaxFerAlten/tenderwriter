# Upgrade a Qwen2.5-3B-Instruct

## Modello Scaricato

✅ **qwen2.5-3b-instruct-q4_k_m.gguf** (~2GB)

## Performance Migliorata

### Confronto con Qwen3.5-9B:

| Metrica | Qwen3.5-9B | Qwen2.5-3B | Miglioramento |
|---------|------------|------------|---------------|
| Velocità | ~8.6 token/sec | ~22.7 token/sec | **2.6x più veloce** |
| RAM | ~12GB | ~5GB | **2.4x meno RAM** |
| Tempo risposta (50 token) | ~6 sec | ~2.2 sec | **2.7x più veloce** |
| Tempo risposta (512 token) | ~60 sec | ~23 sec | **2.6x più veloce** |

## Configurazione Applicata

Entrambi i server (llama-tender e llama-opencode) ora usano Qwen2.5-3B:

```yaml
llama-tender:
  command: ["-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", ...]

llama-opencode:
  command: ["-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", ...]
```

## Test Velocità

```bash
# Test rapido
docker exec tw-llama-tender curl -X POST http://localhost:8080/completion \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is 2+2?","n_predict":50}'

# Risultato: ~2.2 secondi per 50 token
```

## Vantaggi

✅ Risposte RAG molto più veloci (~20-30 sec invece di 60+ sec)
✅ Usa meno RAM (importante per sistemi con risorse limitate)
✅ Migliore esperienza utente (meno timeout)
✅ Può gestire più richieste simultanee

## Qualità

Il modello 3B è comunque molto capace per:
- ✅ RAG Q&A
- ✅ Summarization
- ✅ Text generation
- ⚠️ Leggermente meno capace su reasoning complesso
- ⚠️ Meno conoscenza generale rispetto al 9B

## Prossimi Passi

Prova ora la query RAG dal frontend - dovrebbe essere molto più veloce!

Se la qualità non è sufficiente, puoi tornare al 9B o provare il 7B:
```bash
# Qwen2.5-7B (compromesso qualità/velocità)
cd models
Invoke-WebRequest -Uri "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf" -OutFile "qwen2.5-7b-instruct-q4_k_m.gguf"
```
