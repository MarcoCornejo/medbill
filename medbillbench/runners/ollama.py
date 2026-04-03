"""Ollama-based runner for MedBillBench evaluation."""

from __future__ import annotations

import logging
from pathlib import Path

from medbill.core.ocr import ExtractionError, OllamaExtractor
from medbill.models import DocumentExtraction

logger = logging.getLogger(__name__)


class OllamaRunner:
    """Run GLM-OCR (or any Ollama model) against benchmark documents."""

    def __init__(self, model_name: str = "glm-ocr") -> None:
        self._model_name = model_name
        self._extractor = OllamaExtractor()

    @property
    def name(self) -> str:
        return f"ollama:{self._model_name}"

    def predict(self, image_path: Path) -> DocumentExtraction | None:
        """Extract from a single benchmark image."""
        try:
            return self._extractor.extract(image_path)
        except ExtractionError as exc:
            logger.warning("Extraction failed for %s: %s", image_path.name, exc)
            return None
