"""Base runner protocol for MedBillBench model evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from medbill.models import DocumentExtraction


class BenchmarkRunner(Protocol):
    """Protocol for model evaluation runners."""

    @property
    def name(self) -> str:
        """Model name for the leaderboard."""
        ...

    def predict(self, image_path: Path) -> DocumentExtraction | None:
        """Run the model on a document image and return extraction.

        Returns None if the model fails to produce a valid extraction.
        """
        ...
