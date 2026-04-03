"""MedBillBench CLI.

Usage:
    python -m medbillbench.cli evaluate --model glm-ocr --data benchmark/test/
    python -m medbillbench.cli generate --count 500 --output benchmark/test/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Entry point for medbillbench CLI."""
    parser = argparse.ArgumentParser(
        prog="medbillbench",
        description="MedBillBench: medical billing document AI benchmark",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Generate benchmark dataset
    gen_parser = subparsers.add_parser("generate", help="Generate benchmark dataset")
    gen_parser.add_argument("--count", type=int, default=500, help="Number of documents")
    gen_parser.add_argument(
        "--seed", type=int, default=44, help="Random seed (default 44 for test set)"
    )
    gen_parser.add_argument("--output", type=Path, required=True, help="Output directory")
    gen_parser.add_argument("--error-rate", type=float, default=0.35, help="Error injection rate")

    # Evaluate a model
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a model")
    eval_parser.add_argument("--model", type=str, default="glm-ocr", help="Model name")
    eval_parser.add_argument("--data", type=Path, required=True, help="Benchmark data directory")
    eval_parser.add_argument("--max-docs", type=int, default=None, help="Limit docs (for testing)")
    eval_parser.add_argument("--output", type=Path, default=None, help="Save results JSON")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "generate":
        return _cmd_generate(args)

    if args.command == "evaluate":
        return _cmd_evaluate(args)

    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    """Generate benchmark dataset."""
    from medbillgen.generator import generate_batch
    from medbillgen.renderer import render_batch

    print(f"Generating {args.count} benchmark documents (seed={args.seed})...")
    results = generate_batch(
        count=args.count,
        seed=args.seed,
        error_rate=args.error_rate,
    )

    print(f"Rendering images to {args.output}/...")
    render_batch(results, args.output)

    print(f"Done. {args.count} documents in {args.output}/")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate a model against the benchmark."""
    from medbillbench.evaluator import format_leaderboard, run_benchmark
    from medbillbench.runners.ollama import OllamaRunner

    runner = OllamaRunner(model_name=args.model)
    print(f"Evaluating {runner.name} on {args.data}...")

    summary = run_benchmark(runner, args.data, max_docs=args.max_docs)

    print(f"\n{runner.name}: MedBillScore = {summary.mean_medbill_score:.1f}")
    print(f"  Documents: {summary.num_documents}")
    m = summary.mean_sub_metrics
    print(f"  Classification: {m.classification_accuracy:.3f}")
    print(f"  Code F1:        {m.code_extraction_f1:.3f}")
    print(f"  Amount Acc:     {m.amount_accuracy:.3f}")
    print(f"  Date F1:        {m.date_extraction_f1:.3f}")
    print(f"  Name F1:        {m.name_extraction_f1:.3f}")
    print(f"  Structure:      {m.structural_accuracy:.3f}")
    print(f"  Denial F1:      {m.denial_field_f1:.3f}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        result_data = {
            "model": summary.model_name,
            "medbill_score": summary.mean_medbill_score,
            "num_documents": summary.num_documents,
            "sub_metrics": {
                "classification_accuracy": m.classification_accuracy,
                "code_extraction_f1": m.code_extraction_f1,
                "amount_accuracy": m.amount_accuracy,
                "date_extraction_f1": m.date_extraction_f1,
                "name_extraction_f1": m.name_extraction_f1,
                "structural_accuracy": m.structural_accuracy,
                "denial_field_f1": m.denial_field_f1,
            },
        }
        args.output.write_text(json.dumps(result_data, indent=2))
        print(f"\nResults saved to {args.output}")

    # Print leaderboard
    leaderboard = format_leaderboard([summary])
    print(f"\n{leaderboard}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
