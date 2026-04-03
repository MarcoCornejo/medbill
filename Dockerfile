# =============================================================================
# MedBill Dockerfile -- single-container: FastAPI + Ollama + GLM-OCR
# =============================================================================
# Build:   docker build -t medbill:latest .
# Run:     docker run -p 8000:8000 medbill:latest
# GPU:     docker run --gpus all -p 8000:8000 medbill:latest
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Python build -- install deps with uv, build the package
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (layer caching -- only re-runs when lock changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY src/ src/
COPY medbillgen/ medbillgen/
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: Pull the model into Ollama's data directory
# ---------------------------------------------------------------------------
FROM ollama/ollama:latest AS model

# Start Ollama in the background, pull the model, then stop.
# The pulled model lands in /root/.ollama/models/
RUN ollama serve & \
    SERVER_PID=$! && \
    sleep 3 && \
    until ollama list >/dev/null 2>&1; do sleep 1; done && \
    ollama pull glm-ocr && \
    kill $SERVER_PID && \
    wait $SERVER_PID 2>/dev/null || true

# ---------------------------------------------------------------------------
# Stage 3: Runtime -- slim image with everything combined
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# System deps for Pillow / PyMuPDF (already satisfied in slim, but be safe)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy Ollama binary from the official image
COPY --from=ollama/ollama:latest /bin/ollama /usr/local/bin/ollama

# Copy pre-pulled model weights from stage 2
COPY --from=model /root/.ollama /root/.ollama

# Copy Python venv from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source (templates, static, etc.)
WORKDIR /app
COPY src/ src/
COPY medbillgen/ medbillgen/
COPY pyproject.toml ./

# Put the venv on PATH so `python`, `uvicorn` resolve correctly
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    MEDBILL_MODEL=glm-ocr

# Entrypoint script starts Ollama, waits, then starts uvicorn
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
