"""Tests for the billing error rule engine."""

from datetime import date
from decimal import Decimal

from medbill.analysis.rules import (
    analyze,
    find_duplicate_charges,
    find_mue_violations,
    find_price_outliers,
    find_unbundled_codes,
)
from medbill.models import (
    DocumentExtraction,
    DocumentType,
    ErrorType,
    LineItem,
    Severity,
)


def _bill(*items: LineItem) -> DocumentExtraction:
    """Helper to create a medical bill extraction with line items."""
    return DocumentExtraction(
        document_type=DocumentType.MEDICAL_BILL,
        line_items=list(items),
    )


# ---------------------------------------------------------------------------
# Duplicate charges
# ---------------------------------------------------------------------------


class TestDuplicateCharges:
    def test_no_duplicates(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="99213", date_of_service=date(2026, 1, 15)),
            LineItem(cpt_code="85025", date_of_service=date(2026, 1, 15)),
        )
        errors = find_duplicate_charges(extraction)
        assert len(errors) == 0

    def test_same_code_same_date(self) -> None:
        extraction = _bill(
            LineItem(
                cpt_code="99213",
                date_of_service=date(2026, 1, 15),
                billed_amount=Decimal("250.00"),
            ),
            LineItem(
                cpt_code="99213",
                date_of_service=date(2026, 1, 15),
                billed_amount=Decimal("250.00"),
            ),
        )
        errors = find_duplicate_charges(extraction)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.DUPLICATE_CHARGE
        assert errors[0].severity == Severity.ERROR
        assert errors[0].estimated_overcharge == Decimal("250.00")
        assert errors[0].affected_line_indices == [0, 1]

    def test_same_code_different_date(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="99213", date_of_service=date(2026, 1, 15)),
            LineItem(cpt_code="99213", date_of_service=date(2026, 1, 16)),
        )
        errors = find_duplicate_charges(extraction)
        assert len(errors) == 0

    def test_triple_duplicate(self) -> None:
        extraction = _bill(
            LineItem(
                cpt_code="85025",
                date_of_service=date(2026, 1, 15),
                billed_amount=Decimal("45.00"),
            ),
            LineItem(
                cpt_code="85025",
                date_of_service=date(2026, 1, 15),
                billed_amount=Decimal("45.00"),
            ),
            LineItem(
                cpt_code="85025",
                date_of_service=date(2026, 1, 15),
                billed_amount=Decimal("45.00"),
            ),
        )
        errors = find_duplicate_charges(extraction)
        assert len(errors) == 1
        assert errors[0].estimated_overcharge == Decimal("90.00")  # 2 extra
        assert errors[0].affected_line_indices == [0, 1, 2]

    def test_ignores_items_without_codes(self) -> None:
        extraction = _bill(
            LineItem(description="Facility fee", billed_amount=Decimal("500.00")),
            LineItem(description="Facility fee", billed_amount=Decimal("500.00")),
        )
        errors = find_duplicate_charges(extraction)
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# NCCI unbundled codes
# ---------------------------------------------------------------------------


class TestUnbundledCodes:
    def test_no_ncci_violation(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="99213"),
            LineItem(cpt_code="85025"),
        )
        errors = find_unbundled_codes(extraction)
        assert len(errors) == 0

    def test_bundled_pair_no_modifier_exception(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="80053", billed_amount=Decimal("150.00")),
            LineItem(cpt_code="82565", billed_amount=Decimal("45.00")),
        )
        errors = find_unbundled_codes(extraction)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.UNBUNDLED_CODES
        assert errors[0].severity == Severity.ERROR
        assert "component" in errors[0].description.lower()

    def test_bundled_pair_with_modifier_exception_no_modifier(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="58150"),
            LineItem(cpt_code="58661"),
        )
        errors = find_unbundled_codes(extraction)
        assert len(errors) == 1
        assert errors[0].severity == Severity.ERROR

    def test_bundled_pair_with_modifier_exception_has_modifier(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="58150"),
            LineItem(cpt_code="58661", modifier_codes=["59"]),
        )
        errors = find_unbundled_codes(extraction)
        assert len(errors) == 1
        assert errors[0].severity == Severity.INFO
        assert "modifier present" in errors[0].description.lower()

    def test_xe_modifier_also_accepted(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="58150"),
            LineItem(cpt_code="58661", modifier_codes=["XE"]),
        )
        errors = find_unbundled_codes(extraction)
        assert len(errors) == 1
        assert errors[0].severity == Severity.INFO

    def test_reversed_order_still_detected(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="82565", billed_amount=Decimal("45.00")),
            LineItem(cpt_code="80053", billed_amount=Decimal("150.00")),
        )
        errors = find_unbundled_codes(extraction)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.UNBUNDLED_CODES


# ---------------------------------------------------------------------------
# MUE violations
# ---------------------------------------------------------------------------


class TestMUEViolations:
    def test_within_limits(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="71046", units=1),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 0

    def test_exceeds_limit(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="71046", units=5),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.MUE_EXCEEDED
        assert "5 total units" in errors[0].description
        assert "max 1" in errors[0].description

    def test_venipuncture_at_limit(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="36415", units=1),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 0  # max is 1

    def test_venipuncture_exceeds(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="36415", units=2),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 1

    def test_unknown_code_ignored(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="12345", units=100),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 0

    def test_aggregate_across_lines(self) -> None:
        """Two lines of same CPT x 1 unit each = 2 total, should exceed MUE of 1."""
        extraction = _bill(
            LineItem(cpt_code="71046", units=1, date_of_service=date(2026, 1, 15)),
            LineItem(cpt_code="71046", units=1, date_of_service=date(2026, 1, 15)),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 1
        assert "2 total units" in errors[0].description
        assert errors[0].affected_line_indices == [0, 1]

    def test_different_dates_not_aggregated(self) -> None:
        """Same CPT on different dates should be checked independently."""
        extraction = _bill(
            LineItem(cpt_code="71046", units=1, date_of_service=date(2026, 1, 15)),
            LineItem(cpt_code="71046", units=1, date_of_service=date(2026, 1, 16)),
        )
        errors = find_mue_violations(extraction)
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# Price outliers
# ---------------------------------------------------------------------------


class TestPriceOutliers:
    def test_reasonable_price(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="99213", billed_amount=Decimal("350.00")),
        )
        errors, benchmarks = find_price_outliers(extraction)
        assert len(errors) == 0  # 350/95.42 = 3.67x, below 4x threshold
        assert len(benchmarks) == 1
        assert benchmarks[0].ratio == 3.67

    def test_extreme_outlier(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="27447", billed_amount=Decimal("45000.00")),
        )
        errors, benchmarks = find_price_outliers(extraction)
        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.PRICE_OUTLIER
        assert errors[0].severity == Severity.WARNING
        assert "Medicare rate $700.36" in errors[0].description
        assert len(benchmarks) == 1

    def test_no_code_skipped(self) -> None:
        extraction = _bill(
            LineItem(description="Misc", billed_amount=Decimal("100.00")),
        )
        errors, benchmarks = find_price_outliers(extraction)
        assert len(errors) == 0
        assert len(benchmarks) == 0

    def test_no_amount_skipped(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="99213"),
        )
        errors, benchmarks = find_price_outliers(extraction)
        assert len(errors) == 0
        assert len(benchmarks) == 0

    def test_unknown_code_skipped(self) -> None:
        extraction = _bill(
            LineItem(cpt_code="99999", billed_amount=Decimal("500.00")),
        )
        errors, benchmarks = find_price_outliers(extraction)
        assert len(errors) == 0
        assert len(benchmarks) == 0


# ---------------------------------------------------------------------------
# Full analysis pipeline
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_clean_bill(self) -> None:
        extraction = _bill(
            LineItem(
                cpt_code="99213",
                billed_amount=Decimal("200.00"),
                date_of_service=date(2026, 1, 15),
            ),
        )
        result = analyze(extraction)
        assert result.error_count == 0
        assert result.has_errors is False
        assert result.total_estimated_overcharge == Decimal("0")
        assert len(result.price_benchmarks) == 1

    def test_bill_with_multiple_errors(self) -> None:
        extraction = _bill(
            LineItem(
                cpt_code="99213",
                billed_amount=Decimal("250.00"),
                date_of_service=date(2026, 1, 15),
            ),
            LineItem(
                cpt_code="99213",
                billed_amount=Decimal("250.00"),
                date_of_service=date(2026, 1, 15),
            ),
            LineItem(
                cpt_code="71046",
                billed_amount=Decimal("500.00"),
                units=3,
                date_of_service=date(2026, 1, 15),
            ),
        )
        result = analyze(extraction)
        assert result.has_errors is True

        error_types = {e.error_type for e in result.errors}
        assert ErrorType.DUPLICATE_CHARGE in error_types
        assert ErrorType.MUE_EXCEEDED in error_types
        assert ErrorType.PRICE_OUTLIER in error_types  # 500/28.18 = 17.7x

    def test_empty_bill(self) -> None:
        extraction = _bill()
        result = analyze(extraction)
        assert result.error_count == 0
        assert result.total_estimated_overcharge == Decimal("0")
