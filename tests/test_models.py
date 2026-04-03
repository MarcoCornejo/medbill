"""Tests for MedBill data models."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from medbill.models import (
    AnalysisResult,
    AppealRequest,
    BillingError,
    DenialInfo,
    DocumentExtraction,
    DocumentType,
    ErrorType,
    HealthResponse,
    ImpactCounters,
    LineItem,
    PriceBenchmark,
    ScanResponse,
    Severity,
    Totals,
)


class TestLineItem:
    def test_minimal(self) -> None:
        item = LineItem()
        assert item.cpt_code is None
        assert item.units == 1
        assert item.icd10_codes == []
        assert item.modifier_codes == []

    def test_full(self) -> None:
        item = LineItem(
            cpt_code="99213",
            hcpcs_code=None,
            icd10_codes=["M54.5"],
            modifier_codes=["25"],
            description="Office visit, established patient",
            units=1,
            date_of_service=date(2026, 1, 15),
            billed_amount=Decimal("250.00"),
            allowed_amount=Decimal("95.42"),
            adjustment_amount=Decimal("154.58"),
            patient_responsibility=Decimal("30.00"),
        )
        assert item.cpt_code == "99213"
        assert item.billed_amount == Decimal("250.00")
        assert item.date_of_service == date(2026, 1, 15)

    def test_decimal_precision(self) -> None:
        item = LineItem(billed_amount=Decimal("3247.80"))
        assert item.billed_amount == Decimal("3247.80")
        assert str(item.billed_amount) == "3247.80"

    def test_rejects_negative_billed_amount(self) -> None:
        with pytest.raises(ValidationError):
            LineItem(cpt_code="99213", billed_amount=Decimal("-100.00"))

    def test_rejects_zero_units(self) -> None:
        with pytest.raises(ValidationError):
            LineItem(cpt_code="99213", units=0)

    def test_rejects_negative_units(self) -> None:
        with pytest.raises(ValidationError):
            LineItem(cpt_code="99213", units=-1)

    def test_allows_negative_adjustment(self) -> None:
        item = LineItem(cpt_code="99213", adjustment_amount=Decimal("-50.00"))
        assert item.adjustment_amount == Decimal("-50.00")

    def test_serialization_roundtrip(self) -> None:
        item = LineItem(
            cpt_code="27447",
            billed_amount=Decimal("45000.00"),
            date_of_service=date(2026, 3, 1),
        )
        data = item.model_dump(mode="json")
        restored = LineItem.model_validate(data)
        assert restored.cpt_code == "27447"
        assert restored.date_of_service == date(2026, 3, 1)


class TestDocumentExtraction:
    def test_medical_bill(self) -> None:
        extraction = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            patient_name="Jane Rodriguez",
            provider_name="Memorial Regional Hospital",
            service_dates=[date(2026, 1, 15)],
            line_items=[
                LineItem(
                    cpt_code="99213",
                    billed_amount=Decimal("250.00"),
                    date_of_service=date(2026, 1, 15),
                ),
                LineItem(
                    cpt_code="85025",
                    description="CBC with differential",
                    billed_amount=Decimal("45.00"),
                    date_of_service=date(2026, 1, 15),
                ),
            ],
            totals=Totals(
                total_billed=Decimal("295.00"),
                total_patient_responsibility=Decimal("75.00"),
            ),
        )
        assert extraction.document_type == DocumentType.MEDICAL_BILL
        assert len(extraction.line_items) == 2
        assert extraction.totals.total_billed == Decimal("295.00")
        assert extraction.denial.is_denied is False

    def test_eob_with_denial(self) -> None:
        extraction = DocumentExtraction(
            document_type=DocumentType.EOB,
            denial=DenialInfo(
                is_denied=True,
                carc_codes=["CO-4"],
                denial_reason_text="Procedure inconsistent with modifier",
                appeal_deadline=date(2026, 7, 15),
            ),
        )
        assert extraction.denial.is_denied is True
        assert extraction.denial.carc_codes == ["CO-4"]
        assert extraction.denial.appeal_deadline == date(2026, 7, 15)

    def test_denial_letter(self) -> None:
        extraction = DocumentExtraction(
            document_type=DocumentType.DENIAL_LETTER,
            denial=DenialInfo(
                is_denied=True,
                carc_codes=["CO-50"],
                rarc_codes=["N115"],
                denial_reason_text="Not medically necessary",
                appeal_deadline=date(2026, 4, 30),
            ),
        )
        assert extraction.document_type == DocumentType.DENIAL_LETTER
        assert "CO-50" in extraction.denial.carc_codes

    def test_empty_extraction(self) -> None:
        extraction = DocumentExtraction(document_type=DocumentType.MEDICAL_BILL)
        assert extraction.line_items == []
        assert extraction.totals.total_billed is None
        assert extraction.patient_name is None

    def test_json_roundtrip(self) -> None:
        extraction = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            patient_name="Test Patient",
            line_items=[
                LineItem(
                    cpt_code="99213",
                    billed_amount=Decimal("250.00"),
                ),
            ],
        )
        json_str = extraction.model_dump_json()
        restored = DocumentExtraction.model_validate_json(json_str)
        assert restored.patient_name == "Test Patient"
        assert restored.line_items[0].cpt_code == "99213"


class TestBillingError:
    def test_duplicate_charge(self) -> None:
        error = BillingError(
            error_type=ErrorType.DUPLICATE_CHARGE,
            severity=Severity.ERROR,
            description="CPT 99213 billed twice on 2026-01-15",
            affected_line_indices=[0, 3],
            estimated_overcharge=Decimal("250.00"),
        )
        assert error.error_type == ErrorType.DUPLICATE_CHARGE
        assert error.severity == Severity.ERROR
        assert error.estimated_overcharge == Decimal("250.00")
        assert error.affected_line_indices == [0, 3]

    def test_price_outlier(self) -> None:
        error = BillingError(
            error_type=ErrorType.PRICE_OUTLIER,
            severity=Severity.WARNING,
            description="CPT 27447: billed $45,000, Medicare rate $700 (64x)",
            affected_line_indices=[2],
            details={"medicare_rate": "700.00", "ratio": "64.3"},
        )
        assert error.details["ratio"] == "64.3"

    def test_mue_exceeded(self) -> None:
        error = BillingError(
            error_type=ErrorType.MUE_EXCEEDED,
            severity=Severity.WARNING,
            description="CPT 71046: 5 units billed, max 1 per day",
            affected_line_indices=[4],
        )
        assert error.error_type == ErrorType.MUE_EXCEEDED


class TestAnalysisResult:
    def test_no_errors(self) -> None:
        result = AnalysisResult(
            extraction=DocumentExtraction(
                document_type=DocumentType.MEDICAL_BILL,
            ),
        )
        assert result.error_count == 0
        assert result.has_errors is False
        assert result.total_estimated_overcharge == Decimal("0")

    def test_with_errors(self) -> None:
        result = AnalysisResult(
            extraction=DocumentExtraction(
                document_type=DocumentType.MEDICAL_BILL,
                line_items=[
                    LineItem(cpt_code="99213", billed_amount=Decimal("250.00")),
                    LineItem(cpt_code="99213", billed_amount=Decimal("250.00")),
                ],
            ),
            errors=[
                BillingError(
                    error_type=ErrorType.DUPLICATE_CHARGE,
                    severity=Severity.ERROR,
                    description="Duplicate CPT 99213",
                    affected_line_indices=[0, 1],
                    estimated_overcharge=Decimal("250.00"),
                ),
            ],
            total_estimated_overcharge=Decimal("250.00"),
        )
        assert result.error_count == 1
        assert result.has_errors is True
        assert result.total_estimated_overcharge == Decimal("250.00")

    def test_with_price_benchmarks(self) -> None:
        result = AnalysisResult(
            extraction=DocumentExtraction(
                document_type=DocumentType.MEDICAL_BILL,
            ),
            price_benchmarks=[
                PriceBenchmark(
                    line_index=0,
                    cpt_code="99213",
                    billed_amount=Decimal("250.00"),
                    medicare_rate=Decimal("95.42"),
                    ratio=2.62,
                ),
            ],
        )
        assert len(result.price_benchmarks) == 1
        assert result.price_benchmarks[0].ratio == 2.62


class TestAppealRequest:
    def test_construction(self) -> None:
        req = AppealRequest(
            denial_type="medical_necessity",
            carc_code="CO-50",
            carc_description="Non-covered service",
            cpt_code="27447",
            cpt_description="Total knee replacement",
            service_date=date(2026, 1, 15),
            denied_amount=Decimal("45000.00"),
            appeal_deadline=date(2026, 7, 15),
        )
        assert req.denial_type == "medical_necessity"
        assert req.denied_amount == Decimal("45000.00")


class TestImpactCounters:
    def test_defaults(self) -> None:
        counters = ImpactCounters(counter_date=date(2026, 4, 2))
        assert counters.documents_scanned == 0
        assert counters.errors_flagged == 0
        assert counters.estimated_savings_cents == 0


class TestApiModels:
    def test_scan_response_success(self) -> None:
        resp = ScanResponse(
            status="success",
            document_type=DocumentType.MEDICAL_BILL,
        )
        assert resp.status == "success"

    def test_scan_response_error(self) -> None:
        resp = ScanResponse(
            status="error",
            error_message="Unsupported document format",
        )
        assert resp.error_message is not None

    def test_health_response(self) -> None:
        resp = HealthResponse(status="ok", version="0.1.0")
        assert resp.status == "ok"
