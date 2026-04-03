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
        echo "[medbill] ERROR: Ollama failed to start within 30s" >&2
        exit 1
    fi
    sleep 1
done

# Verify the model is available
echo "[medbill] Verifying model '${MEDBILL_MODEL:-glm-ocr}' is loaded..."
if ! ollama list | grep -q "${MEDBILL_MODEL:-glm-ocr}"; then
    echo "[medbill] WARNING: Model not found. Pulling ${MEDBILL_MODEL:-glm-ocr}..."
    ollama pull "${MEDBILL_MODEL:-glm-ocr}"
fi

echo "[medbill] Starting FastAPI on port 8000..."
exec uvicorn medbill.web.app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
