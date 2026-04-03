"""FastAPI web application for MedBill.

Upload a bill -> extract -> analyze -> show results.
Server-rendered with Jinja2 + HTMX. Zero JS build step.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from medbill import __version__
from medbill.analysis.rules import analyze
from medbill.core.ocr import Extractor, MockExtractor
from medbill.models import HealthResponse

WEB_DIR = Path(__file__).parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

app = FastAPI(
    title="MedBill",
    version=__version__,
    description="Privacy-first medical bill scanner",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Extractor is swappable — MockExtractor for dev, GLM-OCR for production
_extractor: Extractor = MockExtractor()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Landing page with upload form."""
    return templates.TemplateResponse(request, "index.html")


@app.post("/scan", response_class=HTMLResponse)
async def scan(request: Request, file: UploadFile) -> HTMLResponse:
    """Process an uploaded document and return analysis results."""
    # Read file into memory with size limit — never written to disk
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Explicitly close the upload to release any spooled temp file
    await file.close()

    # Sanitize filename (prevent path traversal)
    safe_name = Path(file.filename or "document.pdf").name

    # Process in memory via BytesIO — no disk writes
    file_bytes = io.BytesIO(content)

    # Extract structured data (mock for now)
    extraction = _extractor.extract(Path(safe_name), file_bytes)

    # Explicitly clear document content from memory
    file_bytes.close()
    del content, file_bytes

    # Run rule engine
    result = analyze(extraction)

    return templates.TemplateResponse(
        request,
        "results.html",
        {"result": result},
    )


@app.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)
