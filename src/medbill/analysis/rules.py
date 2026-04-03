"""Rule engine for detecting billing errors.

Pure functions. Deterministic. No ML, no API calls, no randomness.
Input: DocumentExtraction. Output: list[BillingError].

Data comes from src/medbill/data/ (SQLite with hardcoded fallback).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from medbill.data import (
    get_all_ncci_edits,
    get_code_description,
    get_data_year,
    get_medicare_rate,
    get_mue_limit,
)
from medbill.models import (
    AnalysisResult,
    BillingError,
    DocumentExtraction,
    ErrorType,
    PriceBenchmark,
    Severity,
)

MODIFIER_59_FAMILY = {"59", "XE", "XS", "XP", "XU"}
BILATERAL_MODIFIERS = {"50", "LT", "RT"}

# 4x threshold: median hospital markup is 2.5-3.5x Medicare.
PRICE_OUTLIER_THRESHOLD = Decimal("4.0")

# Minimum dollar difference to flag a price outlier (avoids noisy flags on $3 items)
PRICE_OUTLIER_MIN_DIFFERENCE = Decimal("50.0")


def analyze(extraction: DocumentExtraction) -> AnalysisResult:
    """Run all rules against an extraction and return the analysis result."""
    errors: list[BillingError] = []
    benchmarks: list[PriceBenchmark] = []
    warnings: list[str] = []

    # Check coverage: how many line items have recognizable codes?
    total_items = len(extraction.line_items)
    items_with_codes = sum(1 for item in extraction.line_items if item.cpt_code or item.hcpcs_code)

    # Revenue-code-only bill detection (BLOCKER finding)
    if total_items > 0 and items_with_codes == 0:
        warnings.append(
            "This bill appears to use revenue codes rather than CPT/HCPCS procedure codes. "
            "Our analysis requires procedure codes to check for errors. "
            "Request an itemized bill with CPT codes from your provider."
        )
    elif total_items > 2 and items_with_codes < total_items / 2:
        warnings.append(
            f"Only {items_with_codes} of {total_items} line items have recognizable "
            f"procedure codes. Analysis may be incomplete."
        )

    # Run rules
    errors.extend(find_duplicate_charges(extraction))
    errors.extend(find_unbundled_codes(extraction))
    errors.extend(find_mue_violations(extraction))

    price_errors, price_benchmarks = find_price_outliers(extraction)
    errors.extend(price_errors)
    benchmarks.extend(price_benchmarks)

    # Count how many codes had Medicare rate data
    codes_checked = len(
        {
            item.cpt_code or item.hcpcs_code
            for item in extraction.line_items
            if item.cpt_code or item.hcpcs_code
        }
    )
    codes_with_rates = len({b.cpt_code for b in benchmarks})
    codes_without = codes_checked - codes_with_rates

    if codes_without > 0:
        warnings.append(
            f"{codes_without} of {codes_checked} procedure codes had no Medicare "
            f"rate data for price comparison."
        )

    # Data vintage warning
    data_year = get_data_year()
    from datetime import date as _date

    current_year = str(_date.today().year)
    if data_year != current_year:
        warnings.append(
            f"Medicare rates are from CY{data_year}. "
            f"Your bill may use {current_year} rates, which could differ."
        )

    total_overcharge = sum(
        (e.estimated_overcharge for e in errors if e.estimated_overcharge is not None),
        Decimal("0"),
    )

    return AnalysisResult(
        extraction=extraction,
        errors=errors,
        price_benchmarks=benchmarks,
        total_estimated_overcharge=total_overcharge,
        warnings=warnings,
        data_year=data_year,
        codes_checked=codes_checked,
        codes_without_rates=codes_without,
    )


# ---------------------------------------------------------------------------
# Rule: Duplicate charges
# ---------------------------------------------------------------------------


def find_duplicate_charges(extraction: DocumentExtraction) -> list[BillingError]:
    """Flag identical CPT code + date of service appearing more than once.

    Skips bilateral procedures (modifier -50, -LT, -RT) which legitimately
    have the same code on the same date for different anatomic sites.
    """
    errors: list[BillingError] = []
    seen: dict[tuple[str, str | None], list[int]] = defaultdict(list)

    for i, item in enumerate(extraction.line_items):
        code = item.cpt_code or item.hcpcs_code
        if code is None:
            continue
        # Skip if bilateral modifier present — legitimately same code, same date
        if set(item.modifier_codes) & BILATERAL_MODIFIERS:
            continue
        date_str = str(item.date_of_service) if item.date_of_service else None
        seen[(code, date_str)].append(i)

    for (code, date_str), indices in seen.items():
        if len(indices) > 1:
            billed = extraction.line_items[indices[0]].billed_amount
            overcharge = billed * (len(indices) - 1) if billed else None
            date_desc = f" on {date_str}" if date_str else ""
            errors.append(
                BillingError(
                    error_type=ErrorType.DUPLICATE_CHARGE,
                    severity=Severity.ERROR,
                    description=(
                        f"CPT {code} billed {len(indices)} times{date_desc}. "
                        f"Possible duplicate charge."
                    ),
                    affected_line_indices=indices,
                    estimated_overcharge=overcharge,
                )
            )

    return errors


# ---------------------------------------------------------------------------
# Rule: NCCI unbundled codes
# ---------------------------------------------------------------------------


def find_unbundled_codes(extraction: DocumentExtraction) -> list[BillingError]:
    """Flag code pairs that should be bundled per NCCI edits.

    O(n) algorithm: build a code->indices map, then check each NCCI pair.
    """
    errors: list[BillingError] = []
    items = extraction.line_items

    # Build code -> list of line indices (O(n))
    code_indices: dict[str, list[int]] = defaultdict(list)
    for i, item in enumerate(items):
        code = item.cpt_code or item.hcpcs_code
        if code is not None:
            code_indices[code].append(i)

    # Load NCCI edits from data layer (SQLite or fallback)
    ncci_edits = get_all_ncci_edits()

    # Check each NCCI pair against the bill's codes (O(E) where E = edit count)
    for col1, col2, modifier_indicator in ncci_edits:
        if col1 not in code_indices or col2 not in code_indices:
            continue

        col1_idx = code_indices[col1][0]
        col2_idx = code_indices[col2][0]
        item_col1 = items[col1_idx]
        item_col2 = items[col2_idx]
        modifier_exception = modifier_indicator == 1

        if modifier_exception:
            mods = set(item_col1.modifier_codes) | set(item_col2.modifier_codes)
            if mods & MODIFIER_59_FAMILY:
                errors.append(
                    BillingError(
                        error_type=ErrorType.UNBUNDLED_CODES,
                        severity=Severity.INFO,
                        description=(
                            f"CPT {col1} and {col2} are an NCCI edit pair. "
                            f"Modifier present — verify documentation supports "
                            f"distinct procedure."
                        ),
                        affected_line_indices=[col1_idx, col2_idx],
                    )
                )
                continue

        errors.append(
            BillingError(
                error_type=ErrorType.UNBUNDLED_CODES,
                severity=Severity.ERROR,
                description=(
                    f"CPT {col2} is a component of {col1} "
                    f"and should not be billed separately (NCCI edit). "
                    f"Possible unbundling."
                ),
                affected_line_indices=[col1_idx, col2_idx],
                estimated_overcharge=item_col2.billed_amount,
            )
        )

    return errors


# ---------------------------------------------------------------------------
# Rule: MUE (Medically Unlikely Edits)
# ---------------------------------------------------------------------------


def find_mue_violations(extraction: DocumentExtraction) -> list[BillingError]:
    """Flag when total units for a CPT code exceed the MUE limit per day.

    Aggregates units across all line items with the same code + date.
    """
    errors: list[BillingError] = []

    # Aggregate: (code, date) -> (total_units, [line_indices])
    aggregated: dict[tuple[str, str | None], tuple[int, list[int]]] = {}
    for i, item in enumerate(extraction.line_items):
        code = item.cpt_code or item.hcpcs_code
        if code is None:
            continue
        date_key = str(item.date_of_service) if item.date_of_service else None
        key = (code, date_key)
        if key in aggregated:
            total, indices = aggregated[key]
            aggregated[key] = (total + item.units, [*indices, i])
        else:
            aggregated[key] = (item.units, [i])

    for (code, _date_key), (total_units, indices) in aggregated.items():
        max_units = get_mue_limit(code)
        if max_units is None:
            continue
        if total_units > max_units:
            errors.append(
                BillingError(
                    error_type=ErrorType.MUE_EXCEEDED,
                    severity=Severity.WARNING,
                    description=(
                        f"CPT {code}: {total_units} total units billed, "
                        f"max {max_units} per day. "
                        f"Possible billing error."
                    ),
                    affected_line_indices=indices,
                )
            )

    return errors


# ---------------------------------------------------------------------------
# Rule: Price outliers vs Medicare rates
# ---------------------------------------------------------------------------


def find_price_outliers(
    extraction: DocumentExtraction,
) -> tuple[list[BillingError], list[PriceBenchmark]]:
    """Compare billed amounts against Medicare national rates."""
    errors: list[BillingError] = []
    benchmarks: list[PriceBenchmark] = []

    for i, item in enumerate(extraction.line_items):
        code = item.cpt_code or item.hcpcs_code
        if code is None or item.billed_amount is None or item.billed_amount <= 0:
            continue
        medicare_rate = get_medicare_rate(code)
        if medicare_rate is None or medicare_rate == 0:
            continue

        ratio = float(item.billed_amount / medicare_rate)
        benchmarks.append(
            PriceBenchmark(
                line_index=i,
                cpt_code=code,
                code_description=get_code_description(code),
                billed_amount=item.billed_amount,
                medicare_rate=medicare_rate,
                ratio=round(ratio, 2),
            )
        )

        dollar_diff = item.billed_amount - medicare_rate
        if (
            item.billed_amount > medicare_rate * PRICE_OUTLIER_THRESHOLD
            and dollar_diff >= PRICE_OUTLIER_MIN_DIFFERENCE
        ):
            errors.append(
                BillingError(
                    error_type=ErrorType.PRICE_OUTLIER,
                    severity=Severity.WARNING,
                    description=(
                        f"CPT {code}: billed ${item.billed_amount}, "
                        f"Medicare rate ${medicare_rate} "
                        f"({ratio:.1f}x). "
                        f"Significantly above Medicare benchmark."
                    ),
                    affected_line_indices=[i],
                    details={
                        "medicare_rate": str(medicare_rate),
                        "ratio": f"{ratio:.1f}",
                    },
                )
            )

    return errors, benchmarks
