"""MedBillBench evaluator — run a model against the benchmark dataset."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from medbill.models import DocumentExtraction
from medbillbench.metrics import (
    BenchmarkResult,
    BenchmarkSummary,
    SubMetrics,
    evaluate_document,
    summarize_results,
)
from medbillbench.runners.base import BenchmarkRunner

logger = logging.getLogger(__name__)


def run_benchmark(
    runner: BenchmarkRunner,
    data_dir: Path,
    max_docs: int | None = None,
) -> BenchmarkSummary:
    """Run a model against all documents in the benchmark directory.

    Args:
        runner: Model runner implementing BenchmarkRunner protocol.
        data_dir: Directory containing doc_XXXXX/ subdirectories.
        max_docs: Limit number of documents to evaluate (for testing).

    Returns:
        BenchmarkSummary with per-document and aggregate results.
    """
    doc_dirs = sorted(data_dir.glob("doc_*"))
    if max_docs:
        doc_dirs = doc_dirs[:max_docs]

    results: list[BenchmarkResult] = []

    for doc_dir in doc_dirs:
        gt_path = doc_dir / "ground_truth.json"
        img_path = doc_dir / "image.png"

        if not gt_path.exists() or not img_path.exists():
            logger.warning("Skipping %s: missing files", doc_dir.name)
            continue

        # Load ground truth
        gt_data = json.loads(gt_path.read_text())
        ground_truth = DocumentExtraction.model_validate(gt_data)

        # Run model
        logger.info("Evaluating %s...", doc_dir.name)
        predicted = runner.predict(img_path)

        if predicted is None:
            # Model failed — score as zero
            result = BenchmarkResult(
                doc_id=doc_dir.name,
                medbill_score=0.0,
                sub_metrics=SubMetrics(),
            )
        else:
            result = evaluate_document(predicted, ground_truth, doc_id=doc_dir.name)

        results.append(result)
        logger.info("  %s: MedBillScore=%.1f", doc_dir.name, result.medbill_score)

    return summarize_results(results, runner.name)


def format_leaderboard(summaries: list[BenchmarkSummary]) -> str:
    """Format benchmark results as a markdown leaderboard table."""
    lines = [
        "# MedBillBench Leaderboard",
        "",
        "| Rank | Model | Score | Codes | Amounts | Dates | Class. | Struct. |",
        "|------|-------|-------|-------|---------|-------|--------|---------|",
    ]

    sorted_summaries = sorted(summaries, key=lambda s: s.mean_medbill_score, reverse=True)

    for rank, s in enumerate(sorted_summaries, 1):
        m = s.mean_sub_metrics
        lines.append(
            f"| {rank} | {s.model_name} | {s.mean_medbill_score:.1f} "
            f"| {m.code_extraction_f1:.3f} | {m.amount_accuracy:.3f} "
            f"| {m.date_extraction_f1:.3f} | {m.classification_accuracy:.3f} "
            f"| {m.structural_accuracy:.3f} |"
        )

    lines.append("")
    lines.append(
        f"*{sorted_summaries[0].num_documents if sorted_summaries else 0} documents evaluated.*"
    )
    return "\n".join(lines)
