#!/bin/sh
set -e

echo "[medbill] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready (up to 30s)
echo "[medbill] Waiting for Ollama to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "[medbill] Ollama is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[medbill] WARNING: Ollama failed to start. Running in mock mode."
        exec uvicorn medbill.web.app:app --host 0.0.0.0 --port 8000 --workers 1
    fi
    sleep 1
done

# Try to verify/pull the model (non-fatal if no network)
MODEL="${MEDBILL_MODEL:-glm-ocr}"
if ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "[medbill] Model '$MODEL' is available."
else
    echo "[medbill] Model '$MODEL' not found. Attempting pull..."
    if ollama pull "$MODEL" 2>&1; then
        echo "[medbill] Model pulled successfully."
    else
        echo "[medbill] WARNING: Could not pull model. App will use mock extractor."
        echo "[medbill] Pre-pull the model: docker exec <container> ollama pull $MODEL"
    fi
fi

echo "[medbill] Starting FastAPI on port 8000..."
exec uvicorn medbill.web.app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
