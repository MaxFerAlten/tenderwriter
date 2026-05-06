# Setup Llama Server - Qwen2.5-Coder 7B (Temporaneo)

## Architettura Attuale

Il sistema utilizza **due istanze separate** di llama.cpp server:

1. **llama-tender** (porta 8080): per RAG e generazione testi TenderWriter
2. **llama-opencode** (porta 8081): per agentic coding con OpenCode

Attualmente entrambi usano: **Qwen2.5-Coder-7B-Instruct-Q4_K_M** (modello esistente)

## Upgrade Consigliato: Qwen2.5-32B-Instruct

Per prestazioni migliori, specialmente per il RAG, si consiglia di scaricare un modello più grande:

```bash
cd models

# Scarica Qwen2.5-32B-Instruct quantizzato Q4_K_M (~19GB)
# ATTENZIONE: richiede ~24GB RAM e tempo per il download
wget https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-GGUF/resolve/main/qwen2.5-32b-instruct-q4_k_m.gguf

NOITA ho appana cambiato con Qwen3.5-9B-Q4_K_M.gguf

```

Poi aggiorna `docker-compose.yml` per usare il nuovo modello:
```yaml
command: ["-m", "/models/qwen2.5-32b-instruct-q4_k_m.gguf", ...]
```

## Verifica Setup

```bash
# Avvia i servizi
docker-compose up -d llama-tender llama-opencode

# Verifica llama-tender (TenderWriter RAG)
curl http://localhost:8080/health

# Verifica llama-opencode (OpenCode)
curl http://localhost:8081/health

# Test generazione su llama-tender
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-32b-instruct",
    "messages": [{"role": "user", "content": "Ciao, come stai?"}],
    "temperature": 0.7
  }'

# Test generazione su llama-opencode
curl http://localhost:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-32b-instruct",
    "messages": [{"role": "user", "content": "Write a Python function to reverse a string"}],
    "temperature": 0.7
  }'
```

## Configurazione GPU (Opzionale)

Se hai una GPU NVIDIA, puoi abilitare l'accelerazione GPU:

```yaml
# In docker-compose.yml, aggiungi per entrambi i servizi:
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

E modifica il comando per usare più layer GPU:
```bash
--n-gpu-layers 40  # Aumenta in base alla VRAM disponibile
```

## Requisiti Sistema

- **RAM**: minimo 24GB (consigliato 32GB per entrambe le istanze)
- **Disco**: ~20GB per il modello
- **CPU**: 8+ core consigliati
- **GPU** (opzionale): NVIDIA con 12GB+ VRAM per accelerazione

## Troubleshooting

### Out of Memory
Se hai problemi di memoria, riduci il context size:
```bash
-c 4096  # invece di 8192
```

### Lentezza
Riduci i thread:
```bash
-t 4  # invece di 8
```

### Modello non trovato
Verifica che il file sia in `./models/qwen2.5-32b-instruct-q4_k_m.gguf`

## Alternative Modelli

Se Qwen2.5-32B è troppo pesante, alternative più leggere:

- **Qwen2.5-14B-Instruct-Q4_K_M** (~8GB RAM)
- **Qwen2.5-7B-Instruct-Q4_K_M** (~4GB RAM)
- **Mistral-7B-Instruct-v0.3-Q4_K_M** (~4GB RAM)
