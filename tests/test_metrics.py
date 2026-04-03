"""Tests for MedBillBench metrics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from medbill.models import (
    DenialInfo,
    DocumentExtraction,
    DocumentType,
    LineItem,
)
from medbillbench.metrics import (
    SubMetrics,
    compute_medbill_score,
    evaluate_document,
    summarize_results,
)


def _bill(**kwargs: object) -> DocumentExtraction:
    defaults = {"document_type": DocumentType.MEDICAL_BILL}
    defaults.update(kwargs)  # type: ignore[arg-type]
    return DocumentExtraction(**defaults)  # type: ignore[arg-type]


class TestMedBillScore:
    def test_perfect_score(self) -> None:
        sub = SubMetrics(
            classification_accuracy=1.0,
            code_extraction_f1=1.0,
            amount_accuracy=1.0,
            date_extraction_f1=1.0,
            name_extraction_f1=1.0,
            structural_accuracy=1.0,
            denial_field_f1=1.0,
        )
        assert compute_medbill_score(sub) == 100.0

    def test_zero_score(self) -> None:
        sub = SubMetrics()
        assert compute_medbill_score(sub) == 0.0

    def test_weights_sum_to_one(self) -> None:
        weights = [0.10, 0.25, 0.25, 0.15, 0.10, 0.10, 0.05]
        assert abs(sum(weights) - 1.0) < 1e-10


class TestEvaluateDocument:
    def test_perfect_extraction(self) -> None:
        gt = _bill(
            patient_name="Jane Doe",
            provider_name="Hospital",
            service_dates=[date(2026, 1, 15)],
            line_items=[
                LineItem(cpt_code="99213", billed_amount=Decimal("250.00")),
            ],
        )
        result = evaluate_document(gt, gt, doc_id="test")
        assert result.medbill_score == 100.0
        assert result.sub_metrics.classification_accuracy == 1.0
        assert result.sub_metrics.code_extraction_f1 == 1.0
        assert result.sub_metrics.amount_accuracy == 1.0

    def test_wrong_document_type(self) -> None:
        gt = _bill(document_type=DocumentType.MEDICAL_BILL)
        pred = _bill(document_type=DocumentType.EOB)
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.classification_accuracy == 0.0

    def test_missing_codes(self) -> None:
        gt = _bill(
            line_items=[
                LineItem(cpt_code="99213"),
                LineItem(cpt_code="85025"),
            ]
        )
        pred = _bill(
            line_items=[
                LineItem(cpt_code="99213"),
            ]
        )
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.code_extraction_f1 < 1.0
        assert result.sub_metrics.code_extraction_f1 > 0.0

    def test_wrong_amounts(self) -> None:
        gt = _bill(
            line_items=[
                LineItem(cpt_code="99213", billed_amount=Decimal("100.00")),
            ]
        )
        pred = _bill(
            line_items=[
                LineItem(cpt_code="99213", billed_amount=Decimal("200.00")),
            ]
        )
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.amount_accuracy == 0.0  # 100% error

    def test_exact_amounts(self) -> None:
        gt = _bill(
            line_items=[
                LineItem(cpt_code="99213", billed_amount=Decimal("100.00")),
            ]
        )
        pred = _bill(
            line_items=[
                LineItem(cpt_code="99213", billed_amount=Decimal("100.00")),
            ]
        )
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.amount_accuracy == 1.0

    def test_name_match(self) -> None:
        gt = _bill(patient_name="JANE DOE", provider_name="HOSPITAL")
        pred = _bill(patient_name="Jane Doe", provider_name="Hospital")
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.name_extraction_f1 == 1.0

    def test_structural_accuracy(self) -> None:
        gt = _bill(line_items=[LineItem(), LineItem(), LineItem()])
        pred = _bill(line_items=[LineItem(), LineItem()])
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.structural_accuracy == 2 / 3

    def test_empty_vs_empty(self) -> None:
        gt = _bill()
        pred = _bill()
        result = evaluate_document(pred, gt)
        assert result.medbill_score == 100.0

    def test_denial_detection(self) -> None:
        gt = _bill(denial=DenialInfo(is_denied=True, carc_codes=["CO-4"]))
        pred = _bill(denial=DenialInfo(is_denied=True, carc_codes=["CO-4"]))
        result = evaluate_document(pred, gt)
        assert result.sub_metrics.denial_field_f1 == 1.0


class TestSummarize:
    def test_aggregate(self) -> None:
        gt = _bill(patient_name="Test")
        results = [evaluate_document(gt, gt, doc_id=f"doc_{i}") for i in range(5)]
        summary = summarize_results(results, "test-model")
        assert summary.num_documents == 5
        assert summary.mean_medbill_score == 100.0
        assert summary.model_name == "test-model"

    def test_empty(self) -> None:
        summary = summarize_results([], "empty")
        assert summary.num_documents == 0
        assert summary.mean_medbill_score == 0.0
