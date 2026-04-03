"""MedBillGen CLI.

Usage:
    python -m medbillgen.cli generate --count 10 --seed 42 --output output/train
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from medbillgen.generator import generate_batch


def main(argv: list[str] | None = None) -> int:
    """Entry point for medbillgen CLI."""
    parser = argparse.ArgumentParser(
        prog="medbillgen",
        description="Generate synthetic medical billing documents",
    )
    subparsers = parser.add_subparsers(dest="command")

    gen_parser = subparsers.add_parser("generate", help="Generate documents")
    gen_parser.add_argument("--count", type=int, default=10, help="Number of documents")
    gen_parser.add_argument("--seed", type=int, default=42, help="Random seed")
    gen_parser.add_argument("--output", type=Path, default=None, help="Output directory")
    gen_parser.add_argument(
        "--error-rate", type=float, default=0.3, help="Error injection rate (0-1)"
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "generate":
        results = generate_batch(
            count=args.count,
            seed=args.seed,
            output_dir=args.output,
            error_rate=args.error_rate,
        )
        errors_injected = 0
        for r in results:
            errs = r["injected_errors"]
            assert isinstance(errs, list)
            errors_injected += len(errs)
        print(f"Generated {len(results)} documents ({errors_injected} errors injected)")
        if args.output:
            print(f"Output: {args.output}/")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
