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
from medbill.core.ocr import MockExtractor
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

    # Extract (mock for now — will swap to GLM-OCR)
    extractor = MockExtractor()
    extraction = extractor.extract(file_path)

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

    # Errors
    if result.has_errors:
        print(f"  ISSUES FOUND: {result.error_count}")
        if result.total_estimated_overcharge > 0:
            print(f"  Estimated overcharge: ${result.total_estimated_overcharge}")
        print()

        for error in result.errors:
            icon = _severity_icon(error.severity)
            print(f"  {icon} [{error.error_type.value}] {error.description}")
            if error.estimated_overcharge:
                print(f"     Estimated overcharge: ${error.estimated_overcharge}")
        print()
    else:
        print("  No billing errors detected.\n")

    # Price benchmarks
    if result.price_benchmarks:
        print("  PRICE COMPARISON (vs Medicare national rates):")
        for b in result.price_benchmarks:
            flag = " !!" if b.ratio > 3 else ""
            line = f"    CPT {b.cpt_code}: ${b.billed_amount} billed"
            line += f" / ${b.medicare_rate} Medicare = {b.ratio}x{flag}"
            print(line)
        print()


def _severity_icon(severity: Severity) -> str:
    if severity == Severity.ERROR:
        return "[ERROR]  "
    if severity == Severity.WARNING:
        return "[WARNING]"
    return "[INFO]   "


if __name__ == "__main__":
    sys.exit(main())
