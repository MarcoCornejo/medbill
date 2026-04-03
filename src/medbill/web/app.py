"""FastAPI web application for MedBill.

Upload a bill -> extract -> analyze -> show results.
Server-rendered with Jinja2 + HTMX. Zero JS build step.
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from medbill import __version__
from medbill.analysis.rules import analyze
from medbill.core.ocr import ExtractionError, create_extractor

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

app = FastAPI(
    title="MedBill",
    version=__version__,
    description="Privacy-first medical bill scanner",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for local/self-hosted use
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Auto-detect best extractor (Ollama/GLM-OCR or MockExtractor fallback)
_extractor, _extractor_name = create_extractor()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Landing page with upload form."""
    return templates.TemplateResponse(request, "index.html", {"extractor": _extractor_name})


@app.post("/scan", response_class=HTMLResponse)
async def scan(request: Request, file: UploadFile) -> HTMLResponse:
    """Process an uploaded document and return analysis results."""
    content: bytes | None = None
    file_bytes: io.BytesIO | None = None
    try:
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

        # Extract structured data — run in thread to not block event loop
        extraction = await asyncio.to_thread(_extractor.extract, Path(safe_name), file_bytes)

        # Run rule engine (fast, pure Python — OK to run in event loop)
        result = analyze(extraction)

        return templates.TemplateResponse(
            request,
            "results.html",
            {"result": result, "extractor": _extractor_name},
        )

    except ExtractionError as exc:
        logger.warning("Extraction failed: %s", exc)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"error_message": str(exc), "extractor": _extractor_name},
        )

    finally:
        # ALWAYS purge document content, even on exceptions
        if file_bytes is not None:
            file_bytes.close()
        del content, file_bytes


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": __version__, "extractor": _extractor_name}
