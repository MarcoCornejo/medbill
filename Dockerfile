# =============================================================================
# MedBill Dockerfile — FastAPI + Ollama (model pulled on first run)
# =============================================================================
# Build:   docker build -t medbill:latest .
# Run:     docker compose up
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Python build — install deps with uv, build the package
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (layer caching — only re-runs when lock changes)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install the project itself
COPY src/ src/
COPY medbillgen/ medbillgen/
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev && uv run python scripts/build_cms_data.py

# ---------------------------------------------------------------------------
# Stage 2: Runtime — slim image
# ---------------------------------------------------------------------------
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy Ollama binary from official image
COPY --from=ollama/ollama:latest /bin/ollama /usr/local/bin/ollama

# Copy Python venv and app from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src/ /app/src/
COPY --from=builder /app/medbillgen/ /app/medbillgen/
COPY --from=builder /app/pyproject.toml /app/
COPY --from=builder /app/README.md /app/

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    MEDBILL_MODEL=glm-ocr

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
