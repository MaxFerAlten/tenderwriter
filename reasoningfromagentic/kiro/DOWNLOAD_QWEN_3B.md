# Download Qwen2.5-3B-Instruct

## Opzione 1: wget (Linux/WSL/Git Bash)

```bash
cd models
wget https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

## Opzione 2: curl (Windows/Mac/Linux)

```bash
cd models
curl -L -o qwen2.5-3b-instruct-q4_k_m.gguf https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

## Opzione 3: PowerShell (Windows)

```powershell
cd models
Invoke-WebRequest -Uri "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf" -OutFile "qwen2.5-3b-instruct-q4_k_m.gguf"
```

## Opzione 4: Browser

1. Vai su: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/tree/main
2. Clicca su `qwen2.5-3b-instruct-q4_k_m.gguf`
3. Clicca su "Download"
4. Sposta il file nella cartella `models/`

## Dettagli Modello

- **Nome**: Qwen2.5-3B-Instruct-Q4_K_M
- **Dimensione**: ~2.0 GB
- **Quantizzazione**: Q4_K_M (buon bilanciamento qualità/dimensione)
- **RAM richiesta**: ~4-5 GB
- **Velocità**: 2-3x più veloce del 9B su CPU

## Dopo il Download

Aggiorna docker-compose.yml per usare il nuovo modello:

```yaml
llama-tender:
  command: ["-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", "--host", "0.0.0.0", "--port", "8080", "-c", "4096", "-t", "16", "--n-predict", "512", "-b", "512"]

llama-opencode:
  command: ["-m", "/models/qwen2.5-3b-instruct-q4_k_m.gguf", "--host", "0.0.0.0", "--port", "8080", "-c", "8192", "-t", "16"]
```

Poi riavvia i servizi:

```bash
docker-compose up -d --force-recreate llama-tender llama-opencode
```

## Vantaggi Qwen2.5-3B

- ✅ Molto più veloce su CPU (~15-20 token/sec vs 8-10 del 9B)
- ✅ Usa meno RAM (~5GB vs ~12GB)
- ✅ Risposte più rapide (30-40 sec vs 60+ sec)
- ✅ Buona qualità per task RAG/QA
- ⚠️ Leggermente meno capace su task complessi

## Alternative

Se 3B è troppo piccolo, considera:

- **Qwen2.5-7B-Instruct-Q4_K_M** (~4.5GB, buon compromesso)
- **Qwen2.5-14B-Instruct-Q4_K_M** (~8.5GB, migliore qualità)
