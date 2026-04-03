"""Data models for MedBill document extraction and analysis.

These Pydantic models define the data contracts between all layers:
- OCR extraction outputs DocumentExtraction
- Rule engine consumes DocumentExtraction, produces AnalysisResult
- Explanation layer consumes AnalysisResult, produces user-facing output
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DocumentType(StrEnum):
    """Type of medical billing document."""

    MEDICAL_BILL = "MEDICAL_BILL"
    EOB = "EOB"
    DENIAL_LETTER = "DENIAL_LETTER"


class ErrorType(StrEnum):
    """Category of billing error detected by the rule engine."""

    DUPLICATE_CHARGE = "DUPLICATE_CHARGE"
    UNBUNDLED_CODES = "UNBUNDLED_CODES"
    UPCODING = "UPCODING"
    PRICE_OUTLIER = "PRICE_OUTLIER"
    MUE_EXCEEDED = "MUE_EXCEEDED"
    EXPIRED_CODE = "EXPIRED_CODE"
    BALANCE_BILLING = "BALANCE_BILLING"


class Severity(StrEnum):
    """How serious a flagged error is."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Extraction models (output of OCR layer)
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    """A single line item on a medical bill or EOB."""

    cpt_code: str | None = None
    hcpcs_code: str | None = None
    icd10_codes: list[str] = Field(default_factory=list)
    modifier_codes: list[str] = Field(default_factory=list)
    description: str | None = None
    units: int = Field(default=1, ge=1)
    date_of_service: date | None = None
    billed_amount: Decimal | None = Field(default=None, ge=0)
    allowed_amount: Decimal | None = Field(default=None, ge=0)
    adjustment_amount: Decimal | None = None  # Can be negative (credit)
    patient_responsibility: Decimal | None = Field(default=None, ge=0)


class Totals(BaseModel):
    """Summary totals from a bill or EOB."""

    total_billed: Decimal | None = None
    total_allowed: Decimal | None = None
    total_adjustment: Decimal | None = None
    total_patient_responsibility: Decimal | None = None
    insurance_paid: Decimal | None = None


class DenialInfo(BaseModel):
    """Denial-specific fields from an EOB or denial letter."""

    is_denied: bool = False
    carc_codes: list[str] = Field(default_factory=list)
    rarc_codes: list[str] = Field(default_factory=list)
    denial_reason_text: str | None = None
    appeal_deadline: date | None = None


class DocumentExtraction(BaseModel):
    """Complete structured extraction from a medical billing document.

    This is the primary data contract between the OCR layer and the
    rule engine. Every field the OCR model extracts goes here.
    """

    document_type: DocumentType
    patient_name: str | None = None
    patient_dob: date | None = None
    provider_name: str | None = None
    provider_npi: str | None = None
    claim_number: str | None = None
    service_dates: list[date] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    totals: Totals = Field(default_factory=Totals)
    denial: DenialInfo = Field(default_factory=DenialInfo)


# ---------------------------------------------------------------------------
# Analysis models (output of rule engine)
# ---------------------------------------------------------------------------


class BillingError(BaseModel):
    """A single billing error flagged by the rule engine."""

    error_type: ErrorType
    severity: Severity
    description: str
    affected_line_indices: list[int] = Field(default_factory=list)
    estimated_overcharge: Decimal | None = None
    details: dict[str, str] = Field(default_factory=dict)


class PriceBenchmark(BaseModel):
    """Comparison of a billed amount against Medicare rates."""

    line_index: int
    cpt_code: str
    code_description: str | None = None
    billed_amount: Decimal
    medicare_rate: Decimal
    ratio: float = Field(description="billed / medicare")


class AnalysisResult(BaseModel):
    """Complete output of the rule engine.

    Contains the original extraction plus all flagged errors,
    price benchmarks, and coverage/quality metadata.
    """

    extraction: DocumentExtraction
    errors: list[BillingError] = Field(default_factory=list)
    price_benchmarks: list[PriceBenchmark] = Field(default_factory=list)
    total_estimated_overcharge: Decimal = Decimal("0")
    warnings: list[str] = Field(default_factory=list)
    data_year: str = ""
    codes_checked: int = 0
    codes_without_rates: int = 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


# ---------------------------------------------------------------------------
# Appeal models
# ---------------------------------------------------------------------------


class AppealRequest(BaseModel):
    """Input for generating a draft appeal letter."""

    denial_type: str
    carc_code: str
    carc_description: str | None = None
    cpt_code: str
    cpt_description: str | None = None
    service_date: date
    denied_amount: Decimal
    appeal_deadline: date | None = None
    patient_name: str | None = None
    provider_name: str | None = None


# ---------------------------------------------------------------------------
# Impact counters (anonymous aggregates only)
# ---------------------------------------------------------------------------


class ImpactCounters(BaseModel):
    """Anonymous aggregate counters. No PII. No individual tracking."""

    counter_date: date
    documents_scanned: int = 0
    errors_flagged: int = 0
    estimated_savings_cents: int = 0
    appeals_generated: int = 0


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------


class ScanResponse(BaseModel):
    """Response from the /scan endpoint."""

    status: Literal["success", "partial", "error"]
    document_type: DocumentType | None = None
    extraction: DocumentExtraction | None = None
    analysis: AnalysisResult | None = None
    error_message: str | None = None


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: Literal["ok"]
    version: str
