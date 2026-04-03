"""OCR extraction protocol and implementations.

The OCR layer is a Protocol: anything that implements `extract()` works.
This allows swapping between mock, GLM-OCR, and future models without
changing downstream code.
"""

from __future__ import annotations

import io
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


class Extractor(Protocol):
    """Protocol for document extraction backends."""

    def extract(self, image_path: Path, content: io.BytesIO | None = None) -> DocumentExtraction:
        """Extract structured data from a document image."""
        ...


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
