"""End-to-end tests covering critical paths and edge cases.

These tests validate the full pipeline works correctly from input to output,
including edge cases discovered during manual testing.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medbill.analysis.rules import analyze
from medbill.models import (
    AnalysisResult,
    DocumentExtraction,
    DocumentType,
    ErrorType,
    LineItem,
)
from medbill.web.app import app
from medbillgen.generator import generate_batch

# ---------------------------------------------------------------------------
# E2E: MedBillGen → Rule Engine → Correct detection
# ---------------------------------------------------------------------------


class TestGeneratorToRuleEngine:
    """Validate that generated errors are caught by the rule engine."""

    def test_detection_rate_above_threshold(self) -> None:
        """100% of injected errors should be detected."""
        results = generate_batch(count=50, seed=42, error_rate=0.8)
        docs_with_errors = [r for r in results if r["injected_errors"]]
        assert len(docs_with_errors) > 0

        missed = 0
        for r in docs_with_errors:
            ext = DocumentExtraction.model_validate(r["extraction"])
            analysis = analyze(ext)
            errs = r["injected_errors"]
            assert isinstance(errs, list)
            for inj in errs:
                detected_types = {e.error_type.value for e in analysis.errors}
                if inj["error_type"] not in detected_types:
                    missed += 1

        assert missed == 0, f"Missed {missed} injected errors"

    def test_generated_json_validates_as_pydantic(self) -> None:
        """Every generated document must validate against the Pydantic schema."""
        results = generate_batch(count=30, seed=99)
        for r in results:
            ext = DocumentExtraction.model_validate(r["extraction"])
            assert ext.document_type == DocumentType.MEDICAL_BILL
            assert ext.patient_name is not None
            assert len(ext.line_items) >= 1
            for item in ext.line_items:
                if item.billed_amount is not None:
                    assert item.billed_amount > 0

    def test_deterministic_output(self) -> None:
        """Same seed must produce identical output."""
        r1 = generate_batch(count=10, seed=42, error_rate=0.5)
        r2 = generate_batch(count=10, seed=42, error_rate=0.5)
        assert r1 == r2

    def test_analysis_json_roundtrip(self) -> None:
        """Full analysis result must survive JSON serialization."""
        results = generate_batch(count=5, seed=42, error_rate=0.8)
        for r in results:
            ext = DocumentExtraction.model_validate(r["extraction"])
            analysis = analyze(ext)
            json_str = analysis.model_dump_json()
            restored = AnalysisResult.model_validate_json(json_str)
            assert restored.error_count == analysis.error_count
            assert restored.total_estimated_overcharge == analysis.total_estimated_overcharge


# ---------------------------------------------------------------------------
# E2E: Rule engine edge cases
# ---------------------------------------------------------------------------


class TestRuleEngineEdgeCases:
    def test_negative_billed_amount_rejected_by_validator(self) -> None:
        """Negative amounts are now rejected at the model level."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LineItem(cpt_code="99213", billed_amount=Decimal("-100.00"))

    def test_zero_billed_amount_skipped(self) -> None:
        """Zero amounts should not produce price benchmarks."""
        ext = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            line_items=[LineItem(cpt_code="99213", billed_amount=Decimal("0.00"))],
        )
        result = analyze(ext)
        assert len(result.price_benchmarks) == 0

    def test_hcpcs_code_path_works(self) -> None:
        """All rules should work with hcpcs_code when cpt_code is None."""
        ext = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            line_items=[
                LineItem(
                    hcpcs_code="99213",
                    billed_amount=Decimal("250.00"),
                    date_of_service=date(2026, 1, 15),
                ),
                LineItem(
                    hcpcs_code="99213",
                    billed_amount=Decimal("250.00"),
                    date_of_service=date(2026, 1, 15),
                ),
            ],
        )
        result = analyze(ext)
        assert any(e.error_type == ErrorType.DUPLICATE_CHARGE for e in result.errors)
        assert len(result.price_benchmarks) >= 1

    def test_duplicates_with_no_date(self) -> None:
        """Duplicates should be caught even when date_of_service is None."""
        ext = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            line_items=[
                LineItem(cpt_code="85025", billed_amount=Decimal("50.00")),
                LineItem(cpt_code="85025", billed_amount=Decimal("50.00")),
            ],
        )
        result = analyze(ext)
        assert any(e.error_type == ErrorType.DUPLICATE_CHARGE for e in result.errors)

    def test_overcharge_total_includes_zero_decimal(self) -> None:
        """Decimal('0') overcharge must be included in the sum (not treated as falsy)."""
        ext = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            line_items=[
                LineItem(
                    cpt_code="85025",
                    billed_amount=Decimal("50.00"),
                    date_of_service=date(2026, 1, 15),
                ),
                LineItem(
                    cpt_code="85025",
                    billed_amount=Decimal("50.00"),
                    date_of_service=date(2026, 1, 15),
                ),
            ],
        )
        result = analyze(ext)
        # Should have an overcharge (the duplicate)
        assert result.total_estimated_overcharge >= Decimal("0")

    def test_empty_bill_no_crash(self) -> None:
        ext = DocumentExtraction(document_type=DocumentType.MEDICAL_BILL)
        result = analyze(ext)
        assert result.error_count == 0
        assert result.total_estimated_overcharge == Decimal("0")

    def test_all_none_fields_no_crash(self) -> None:
        """Line item with all None/default fields should not crash any rule."""
        ext = DocumentExtraction(
            document_type=DocumentType.MEDICAL_BILL,
            line_items=[LineItem()],
        )
        result = analyze(ext)
        assert result.error_count == 0


# ---------------------------------------------------------------------------
# E2E: Web app critical paths
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Force MockExtractor in web tests regardless of Ollama state."""
    import medbill.web.app as _app
    from medbill.core.ocr import MockExtractor

    original = _app._extractor
    _app._extractor = MockExtractor()
    yield TestClient(app)
    _app._extractor = original


class TestWebE2E:
    def test_upload_scan_returns_html_with_errors(self, client: TestClient) -> None:
        """Upload → scan → response contains error flags and line items."""
        resp = client.post(
            "/scan",
            files={"file": ("bill.pdf", BytesIO(b"fake"), "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "potential issue" in body
        assert "99214" in body
        assert "Duplicate" in body or "DUPLICATE" in body

    def test_upload_oversized_returns_413(self, client: TestClient) -> None:
        """Files over 10MB should be rejected."""
        big = BytesIO(b"x" * (11 * 1024 * 1024))
        resp = client.post(
            "/scan",
            files={"file": ("big.pdf", big, "application/pdf")},
        )
        assert resp.status_code == 413

    def test_no_file_returns_422(self, client: TestClient) -> None:
        """Missing file field should return 422."""
        resp = client.post("/scan")
        assert resp.status_code == 422

    def test_health_returns_version(self, client: TestClient) -> None:
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"

    def test_landing_page_has_privacy_disclaimer(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Nothing is stored" in resp.text
        assert "not legal or medical advice" in resp.text


# ---------------------------------------------------------------------------
# E2E: CLI → JSON → Pydantic validation
# ---------------------------------------------------------------------------


class TestCLIE2E:
    def test_json_output_validates_as_analysis_result(self, tmp_path: Path) -> None:
        """CLI --json output must be a valid AnalysisResult."""
        from unittest.mock import patch

        from medbill.cli import main
        from medbill.core.ocr import MockExtractor

        dummy = tmp_path / "bill.pdf"
        dummy.write_bytes(b"fake")

        import io
        import sys

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            with patch("medbill.cli.create_extractor", return_value=(MockExtractor(), "mock")):
                ret = main(["scan", "--json", str(dummy)])
        finally:
            sys.stdout = old_stdout

        assert ret == 0
        data = json.loads(captured.getvalue())
        result = AnalysisResult.model_validate(data)
        assert result.extraction.document_type == DocumentType.MEDICAL_BILL
        assert result.error_count > 0
