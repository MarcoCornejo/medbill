"""MedBillScore — composite metric for medical billing document understanding.

MedBillScore = (
    0.10 * Classification Accuracy +
    0.25 * Code Extraction F1 +
    0.25 * Amount Accuracy +
    0.15 * Date Extraction F1 +
    0.10 * Name Extraction F1 +
    0.10 * Structural Accuracy +
    0.05 * Denial Field F1
) * 100
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from medbill.models import DocumentExtraction


@dataclass
class SubMetrics:
    """Individual metric scores (0-1 scale)."""

    classification_accuracy: float = 0.0
    code_extraction_f1: float = 0.0
    amount_accuracy: float = 0.0
    date_extraction_f1: float = 0.0
    name_extraction_f1: float = 0.0
    structural_accuracy: float = 0.0
    denial_field_f1: float = 0.0


@dataclass
class BenchmarkResult:
    """Result of evaluating one document."""

    doc_id: str
    medbill_score: float
    sub_metrics: SubMetrics
    predicted: DocumentExtraction | None = None
    ground_truth: DocumentExtraction | None = None


@dataclass
class BenchmarkSummary:
    """Aggregate results across all benchmark documents."""

    model_name: str
    num_documents: int = 0
    mean_medbill_score: float = 0.0
    mean_sub_metrics: SubMetrics = field(default_factory=SubMetrics)
    results: list[BenchmarkResult] = field(default_factory=list)


def compute_medbill_score(sub: SubMetrics) -> float:
    """Compute the weighted MedBillScore (0-100) from sub-metrics."""
    return (
        0.10 * sub.classification_accuracy
        + 0.25 * sub.code_extraction_f1
        + 0.25 * sub.amount_accuracy
        + 0.15 * sub.date_extraction_f1
        + 0.10 * sub.name_extraction_f1
        + 0.10 * sub.structural_accuracy
        + 0.05 * sub.denial_field_f1
    ) * 100


def evaluate_document(
    predicted: DocumentExtraction,
    ground_truth: DocumentExtraction,
    doc_id: str = "",
) -> BenchmarkResult:
    """Evaluate a single predicted extraction against ground truth."""
    sub = SubMetrics(
        classification_accuracy=_classification_accuracy(predicted, ground_truth),
        code_extraction_f1=_code_extraction_f1(predicted, ground_truth),
        amount_accuracy=_amount_accuracy(predicted, ground_truth),
        date_extraction_f1=_date_extraction_f1(predicted, ground_truth),
        name_extraction_f1=_name_extraction_f1(predicted, ground_truth),
        structural_accuracy=_structural_accuracy(predicted, ground_truth),
        denial_field_f1=_denial_field_f1(predicted, ground_truth),
    )
    score = compute_medbill_score(sub)
    return BenchmarkResult(
        doc_id=doc_id,
        medbill_score=round(score, 2),
        sub_metrics=sub,
        predicted=predicted,
        ground_truth=ground_truth,
    )


def summarize_results(results: list[BenchmarkResult], model_name: str) -> BenchmarkSummary:
    """Aggregate individual results into a summary."""
    n = len(results)
    if n == 0:
        return BenchmarkSummary(model_name=model_name)

    mean_score = sum(r.medbill_score for r in results) / n
    mean_sub = SubMetrics(
        classification_accuracy=sum(r.sub_metrics.classification_accuracy for r in results) / n,
        code_extraction_f1=sum(r.sub_metrics.code_extraction_f1 for r in results) / n,
        amount_accuracy=sum(r.sub_metrics.amount_accuracy for r in results) / n,
        date_extraction_f1=sum(r.sub_metrics.date_extraction_f1 for r in results) / n,
        name_extraction_f1=sum(r.sub_metrics.name_extraction_f1 for r in results) / n,
        structural_accuracy=sum(r.sub_metrics.structural_accuracy for r in results) / n,
        denial_field_f1=sum(r.sub_metrics.denial_field_f1 for r in results) / n,
    )

    return BenchmarkSummary(
        model_name=model_name,
        num_documents=n,
        mean_medbill_score=round(mean_score, 2),
        mean_sub_metrics=mean_sub,
        results=results,
    )


# ---------------------------------------------------------------------------
# Sub-metric implementations
# ---------------------------------------------------------------------------


def _classification_accuracy(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """1.0 if document type matches, 0.0 otherwise."""
    return 1.0 if pred.document_type == gt.document_type else 0.0


def _code_extraction_f1(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """Micro-averaged F1 across all CPT/HCPCS/ICD-10 codes."""
    gt_codes = _extract_all_codes(gt)
    pred_codes = _extract_all_codes(pred)
    return _f1(pred_codes, gt_codes)


def _extract_all_codes(ext: DocumentExtraction) -> set[str]:
    """Extract all billing codes from an extraction."""
    codes: set[str] = set()
    for item in ext.line_items:
        if item.cpt_code:
            codes.add(item.cpt_code)
        if item.hcpcs_code:
            codes.add(item.hcpcs_code)
        for icd in item.icd10_codes:
            codes.add(icd)
    return codes


def _amount_accuracy(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """1 - MAPE across all dollar amounts, capped at [0, 1]."""
    gt_amounts = _extract_amounts(gt)
    pred_amounts = _extract_amounts(pred)

    if not gt_amounts:
        return 1.0 if not pred_amounts else 0.0

    # Match amounts by position (line item index)
    errors: list[float] = []
    for i, gt_amt in enumerate(gt_amounts):
        if i < len(pred_amounts) and gt_amt > 0:
            pred_amt = pred_amounts[i]
            errors.append(abs(float(pred_amt - gt_amt)) / float(gt_amt))
        elif gt_amt > 0:
            errors.append(1.0)  # Missing prediction = 100% error

    if not errors:
        return 1.0

    mape = sum(errors) / len(errors)
    return max(0.0, 1.0 - mape)


def _extract_amounts(ext: DocumentExtraction) -> list[Decimal]:
    """Extract all billed amounts in line item order."""
    return [item.billed_amount or Decimal("0") for item in ext.line_items]


def _date_extraction_f1(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """F1 on extracted dates (service dates + line item dates)."""
    gt_dates = {str(d) for d in gt.service_dates}
    for item in gt.line_items:
        if item.date_of_service:
            gt_dates.add(str(item.date_of_service))

    pred_dates = {str(d) for d in pred.service_dates}
    for item in pred.line_items:
        if item.date_of_service:
            pred_dates.add(str(item.date_of_service))

    return _f1(pred_dates, gt_dates)


def _name_extraction_f1(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """Fuzzy match on patient and provider names."""
    scores: list[float] = []
    if gt.patient_name:
        scores.append(_fuzzy_match(pred.patient_name or "", gt.patient_name))
    if gt.provider_name:
        scores.append(_fuzzy_match(pred.provider_name or "", gt.provider_name))
    return sum(scores) / len(scores) if scores else 1.0


def _structural_accuracy(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """Jaccard similarity of line item count."""
    gt_count = len(gt.line_items)
    pred_count = len(pred.line_items)
    if gt_count == 0:
        return 1.0 if pred_count == 0 else 0.0
    return min(pred_count, gt_count) / max(pred_count, gt_count)


def _denial_field_f1(pred: DocumentExtraction, gt: DocumentExtraction) -> float:
    """F1 on denial-specific fields."""
    gt_denial = gt.denial
    pred_denial = pred.denial

    gt_set: set[str] = set()
    pred_set: set[str] = set()

    if gt_denial.is_denied:
        gt_set.add("DENIED")
    if pred_denial.is_denied:
        pred_set.add("DENIED")

    gt_set.update(gt_denial.carc_codes)
    pred_set.update(pred_denial.carc_codes)
    gt_set.update(gt_denial.rarc_codes)
    pred_set.update(pred_denial.rarc_codes)

    if not gt_set and not pred_set:
        return 1.0
    return _f1(pred_set, gt_set)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _f1(predicted: set[str], ground_truth: set[str]) -> float:
    """Compute F1 score between two sets."""
    if not ground_truth and not predicted:
        return 1.0
    if not ground_truth or not predicted:
        return 0.0

    tp = len(predicted & ground_truth)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(ground_truth) if ground_truth else 0.0

    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def _fuzzy_match(a: str, b: str) -> float:
    """Simple fuzzy string match using Levenshtein ratio."""
    a = a.strip().upper()
    b = b.strip().upper()
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    # Simple character-level ratio (no external dependency)
    max_len = max(len(a), len(b))
    common = sum(1 for ca, cb in zip(a, b, strict=False) if ca == cb)
    return common / max_len
