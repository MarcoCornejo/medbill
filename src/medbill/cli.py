"""MedBill command-line interface.

Usage:
    medbill scan <file>       Scan a medical bill and show analysis
    medbill scan --json <file>  Output raw JSON instead of formatted text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from medbill import __version__
from medbill.analysis.rules import analyze
from medbill.core.ocr import ExtractionError, create_extractor
from medbill.models import AnalysisResult, Severity


def main(argv: list[str] | None = None) -> int:
    """Entry point for the medbill CLI."""
    parser = argparse.ArgumentParser(
        prog="medbill",
        description="Privacy-first medical bill scanner",
    )
    parser.add_argument("--version", action="version", version=f"medbill {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # medbill scan
    scan_parser = subparsers.add_parser("scan", help="Scan a medical bill for errors")
    scan_parser.add_argument("file", type=Path, help="Path to bill image or PDF")
    scan_parser.add_argument("--json", action="store_true", dest="output_json", help="Output JSON")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "scan":
        return _cmd_scan(args.file, output_json=args.output_json)

    return 0


def _cmd_scan(file_path: Path, *, output_json: bool) -> int:
    """Scan a document and print analysis."""
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        return 1

    # Extract (auto-detects Ollama/GLM-OCR, falls back to mock)
    extractor, extractor_name = create_extractor()
    if extractor_name == "mock":
        print("NOTE: Using mock extractor (Ollama not available).", file=sys.stderr)
        print("  Install Ollama and run: ollama pull glm-ocr", file=sys.stderr)

    try:
        extraction = extractor.extract(file_path)
    except ExtractionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Analyze
    result = analyze(extraction)

    if output_json:
        print(result.model_dump_json(indent=2))
        return 0

    _print_result(result)
    return 0


def _print_result(result: AnalysisResult) -> None:
    """Print a human-readable analysis result."""
    ext = result.extraction

    print(f"\n  Document type: {ext.document_type.value}")
    if ext.provider_name:
        print(f"  Provider:      {ext.provider_name}")
    print(f"  Line items:    {len(ext.line_items)}")
    if ext.totals.total_billed is not None:
        print(f"  Total billed:  ${ext.totals.total_billed}")
    print()

    # Warnings (revenue code bills, stale data, coverage gaps)
    if result.warnings:
        for warning in result.warnings:
            print(f"  WARNING: {warning}")
        print()

    # Errors
    if result.has_errors:
        print(f"  ISSUES FOUND: {result.error_count}")
        if result.total_estimated_overcharge > 0:
            print(f"  Estimated overcharge: ${result.total_estimated_overcharge}")
        print("  (These are potential issues for review, not confirmed errors.)")
        print()

        for error in result.errors:
            icon = _severity_icon(error.severity)
            print(f"  {icon} [{error.error_type.value}] {error.description}")
            if error.estimated_overcharge:
                print(f"     Estimated overcharge: ${error.estimated_overcharge}")
        print()
    else:
        print("  No issues found by current rules.")
        print("  This does not guarantee your bill is error-free.")
        if result.codes_checked > 0:
            print(f"  ({result.codes_checked} codes checked, rates from CY{result.data_year})")
        print()

    # Price benchmarks
    if result.price_benchmarks:
        print("  PRICE COMPARISON (vs Medicare national rates):")
        for b in result.price_benchmarks:
            flag = " !!" if b.ratio > 4 else ""
            desc = f" ({b.code_description})" if b.code_description else ""
            line = f"    CPT {b.cpt_code}{desc}: ${b.billed_amount} billed"
            line += f" / ${b.medicare_rate} Medicare = {b.ratio}x{flag}"
            print(line)
        print()

    # Disclaimer
    print("  NOTE: MedBill is an informational tool. Output may contain errors.")
    print("  Do not rely on these results without review by a qualified professional.")
    print()


def _severity_icon(severity: Severity) -> str:
    if severity == Severity.ERROR:
        return "[ERROR]  "
    if severity == Severity.WARNING:
        return "[WARNING]"
    return "[INFO]   "


if __name__ == "__main__":
    sys.exit(main())
