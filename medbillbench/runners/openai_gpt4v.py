"""GPT-4V runner for MedBillBench evaluation."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from medbill.core.prompts import EXTRACTION_PROMPT, parse_extraction_lenient
from medbill.models import DocumentExtraction

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


class GPT4VRunner:
    """Run GPT-4V/4o against benchmark documents via OpenAI API."""

    def __init__(self, model: str = OPENAI_MODEL) -> None:
        self._model = model

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    def predict(self, image_path: Path) -> DocumentExtraction | None:
        """Send image to OpenAI and parse extraction."""
        import httpx

        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not set")
            return None

        img_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": EXTRACTION_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_b64}",
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 4096,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=120.0,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("OpenAI API error for %s: %s", image_path.name, exc)
            return None

        raw = resp.json()["choices"][0]["message"]["content"]
        return parse_extraction_lenient(raw)
