# =============================================================================
# MedBill Dockerfile — FastAPI web app (connects to external Ollama)
# =============================================================================
# Ollama runs on the HOST for native hardware performance.
# This container runs only the web app.
#
# Setup:
#   1. Install Ollama on your machine: https://ollama.com
#   2. ollama pull glm-ocr
#   3. docker compose up --build
# =============================================================================

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src/ src/
COPY medbillgen/ medbillgen/
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev && uv run python scripts/build_cms_data.py

# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src/ src/
COPY --from=builder /app/medbillgen/ medbillgen/
COPY --from=builder /app/pyproject.toml ./
COPY --from=builder /app/README.md ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    MEDBILL_MODEL=glm-ocr

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

CMD ["uvicorn", "medbill.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
