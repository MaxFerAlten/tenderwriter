# Ottimizzazioni Performance Llama Server

## Problema
Il modello Qwen3.5-9B su CPU era troppo lento, causando timeout (504 Gateway Timeout).

## Ottimizzazioni Applicate

### 1. Llama Server (docker-compose.yml)

**llama-tender (RAG):**
- Context size: 8192 → **4096** (ridotto del 50%)
- Threads: 8 → **16** (raddoppiati per CPU multi-core)
- Max predict: **512 tokens** (limitato per risposte più veloci)
- Batch size: **512** (ottimizzato per throughput)

**llama-opencode (Coding):**
- Context size: **8192** (mantenuto per code generation)
- Threads: 8 → **16**

### 2. Backend (config.py)
- Timeout: 120s → **300s** (5 minuti per CPU lenta)

### 3. Generator (generator.py)
- max_tokens default: 2048 → **512** (risposte più brevi e veloci)

## Parametri Llama Server Spiegati

```bash
-m /models/Qwen3.5-9B-Q4_K_M.gguf  # Modello da usare
--host 0.0.0.0                      # Ascolta su tutte le interfacce
--port 8080                         # Porta del server
-c 4096                             # Context window (memoria conversazione)
-t 16                               # Thread CPU (usa più core)
--n-predict 512                     # Max token da generare
-b 512                              # Batch size (processa più token insieme)
```

## Risultati Attesi

- **Tempo risposta**: ~30-60 secondi per query semplici
- **Qualità**: Risposte più brevi ma più veloci
- **Stabilità**: Nessun timeout con query normali

## Se Ancora Troppo Lento

### Opzione 1: Ridurre ulteriormente max_tokens
```python
# In backend/app/rag/generator.py
max_tokens: int = 256  # Risposte molto brevi
```

### Opzione 2: Usare modello più piccolo
Scarica un modello 3B o 1.5B:
```bash
cd models
# Qwen2.5-3B (molto più veloce)
wget https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

Poi aggiorna docker-compose.yml:
```yaml
command: ["-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", ...]
```

### Opzione 3: Usare GPU (se disponibile)
Aggiungi al docker-compose.yml:
```yaml
llama-tender:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  command: [..., "-ngl", "35"]  # Carica 35 layer su GPU
```

### Opzione 4: Usare API Cloud
Configura Ollama Cloud o OpenAI invece di llama locale:
```python
# In .env
LLAMA_SERVER_URL=https://api.openai.com/v1
LLAMA_MODEL=gpt-4o-mini
```

## Monitoraggio Performance

```bash
# Monitora uso CPU/RAM
docker stats tw-llama-tender

# Vedi log generazione
docker logs -f tw-llama-tender

# Test velocità
time curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5-9b","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'
```

## Note

- Su CPU, modelli 7B+ sono lenti (5-10 token/sec)
- GPU accelera 10-50x (50-500 token/sec)
- Modelli più piccoli (3B) sono 2-3x più veloci
- Context size grande rallenta molto
