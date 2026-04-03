"""OCR extraction protocol and implementations.

The OCR layer is a Protocol: anything that implements `extract()` works.
This allows swapping between mock, GLM-OCR (via Ollama), and future models
without changing downstream code.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from medbill.models import (
    DenialInfo,
    DocumentExtraction,
    DocumentType,
    LineItem,
    Totals,
)

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("MEDBILL_MODEL", "glm-ocr")
OLLAMA_TIMEOUT = float(os.environ.get("MEDBILL_OCR_TIMEOUT", "120"))


class ExtractionError(Exception):
    """Raised when document extraction fails."""


class Extractor(Protocol):
    """Protocol for document extraction backends."""

    def extract(self, image_path: Path, content: io.BytesIO | None = None) -> DocumentExtraction:
        """Extract structured data from a document image."""
        ...


# ---------------------------------------------------------------------------
# Factory: pick the best available extractor
# ---------------------------------------------------------------------------


def create_extractor() -> tuple[Extractor, str]:
    """Probe for Ollama and return the best available extractor.

    Returns (extractor_instance, extractor_name) so callers can report
    which mode is active. Never raises — falls back to MockExtractor.
    """
    try:
        import httpx

        resp = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=3.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            names = {m.get("name", "").split(":")[0] for m in models}
            if OLLAMA_MODEL in names:
                logger.info("Using OllamaExtractor with model %s", OLLAMA_MODEL)
                return OllamaExtractor(), f"ollama:{OLLAMA_MODEL}"
            logger.warning(
                "Ollama is running but model '%s' not found. Run: ollama pull %s",
                OLLAMA_MODEL,
                OLLAMA_MODEL,
            )
    except Exception:
        logger.warning(
            "Ollama not available at %s. Using mock extractor. "
            "Install Ollama and run: ollama pull %s",
            OLLAMA_HOST,
            OLLAMA_MODEL,
        )

    return MockExtractor(), "mock"


# ---------------------------------------------------------------------------
# OllamaExtractor: real GLM-OCR via Ollama HTTP API
# ---------------------------------------------------------------------------


class OllamaExtractor:
    """Extract structured data from documents via GLM-OCR running in Ollama."""

    def extract(self, image_path: Path, content: io.BytesIO | None = None) -> DocumentExtraction:
        """Send image to Ollama GLM-OCR and parse the structured output."""
        import httpx

        from medbill.core.prompts import EXTRACTION_PROMPT, parse_extraction

        # Get image bytes
        if content is not None:
            img_bytes = content.read()
            content.seek(0)
        else:
            img_bytes = image_path.read_bytes()

        img_b64 = base64.b64encode(img_bytes).decode("ascii")

        try:
            resp = httpx.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": EXTRACTION_PROMPT,
                            "images": [img_b64],
                        }
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 4096},
                },
                timeout=OLLAMA_TIMEOUT,
            )
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            msg = f"Cannot connect to Ollama at {OLLAMA_HOST}. Is it running?"
            raise ExtractionError(msg) from exc
        except httpx.TimeoutException as exc:
            msg = f"Ollama timed out after {OLLAMA_TIMEOUT}s. Document may be too complex."
            raise ExtractionError(msg) from exc
        except httpx.HTTPStatusError as exc:
            msg = f"Ollama returned error: {exc.response.status_code}"
            raise ExtractionError(msg) from exc

        raw_output = resp.json().get("message", {}).get("content", "")
        if not raw_output:
            msg = "Ollama returned empty response"
            raise ExtractionError(msg)

        try:
            return parse_extraction(raw_output)
        except (ValueError, Exception) as exc:
            msg = f"Failed to parse model output: {exc}"
            raise ExtractionError(msg) from exc


# ---------------------------------------------------------------------------
# MockExtractor: hardcoded data for dev/test
# ---------------------------------------------------------------------------


class MockExtractor:
    """Returns a hardcoded extraction for development and testing.

    This lets the full pipeline (upload -> extract -> analyze -> display)
    work end-to-end without a real model installed.
    """

    def extract(self, image_path: Path, content: io.BytesIO | None = None) -> DocumentExtraction:
        return DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            patient_name="Jane Rodriguez",
            provider_name="Memorial Regional Hospital",
            claim_number="CLM-2026-00847",
            service_dates=[date(2026, 1, 15)],
            line_items=[
                LineItem(
                    cpt_code="99214",
                    description="Office visit, established patient, moderate",
                    units=1,
                    date_of_service=date(2026, 1, 15),
                    billed_amount=Decimal("350.00"),
                    allowed_amount=Decimal("139.81"),
                    patient_responsibility=Decimal("45.00"),
                ),
                LineItem(
                    cpt_code="85025",
                    description="Complete blood count (CBC) with differential",
                    units=1,
                    date_of_service=date(2026, 1, 15),
                    billed_amount=Decimal("120.00"),
                    allowed_amount=Decimal("8.46"),
                    patient_responsibility=Decimal("8.46"),
                ),
                LineItem(
                    cpt_code="85025",
                    description="Complete blood count (CBC) with differential",
                    units=1,
                    date_of_service=date(2026, 1, 15),
                    billed_amount=Decimal("120.00"),
                    allowed_amount=Decimal("8.46"),
                    patient_responsibility=Decimal("8.46"),
                ),
                LineItem(
                    cpt_code="80053",
                    description="Comprehensive metabolic panel",
                    units=1,
                    date_of_service=date(2026, 1, 15),
                    billed_amount=Decimal("185.00"),
                    allowed_amount=Decimal("11.22"),
                    patient_responsibility=Decimal("11.22"),
                ),
                LineItem(
                    cpt_code="82565",
                    description="Creatinine, blood",
                    units=1,
                    date_of_service=date(2026, 1, 15),
                    billed_amount=Decimal("75.00"),
                    allowed_amount=Decimal("5.89"),
                    patient_responsibility=Decimal("5.89"),
                ),
                LineItem(
                    cpt_code="93000",
                    description="Electrocardiogram (EKG), 12-lead",
                    units=1,
                    date_of_service=date(2026, 1, 15),
                    billed_amount=Decimal("250.00"),
                    allowed_amount=Decimal("17.26"),
                    patient_responsibility=Decimal("17.26"),
                ),
            ],
            totals=Totals(
                total_billed=Decimal("1100.00"),
                total_allowed=Decimal("191.10"),
                total_patient_responsibility=Decimal("96.09"),
                insurance_paid=Decimal("95.01"),
            ),
            denial=DenialInfo(is_denied=False),
        )
