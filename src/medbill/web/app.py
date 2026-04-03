"""FastAPI web application for MedBill.

Upload a bill → extract → analyze → show results.
Server-rendered with Jinja2 + HTMX. Zero JS build step.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, UploadFile
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
    # Read file into memory (ephemeral — never written to disk)
    _ = await file.read()

    # Extract structured data (mock for now)
    extraction = _extractor.extract(Path(file.filename or "document.pdf"))

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
