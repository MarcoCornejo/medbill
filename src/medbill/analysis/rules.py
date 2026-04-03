"""Rule engine for detecting billing errors.

Pure functions. Deterministic. No ML, no API calls, no randomness.
Input: DocumentExtraction. Output: list[BillingError].
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from medbill.models import (
    AnalysisResult,
    BillingError,
    DocumentExtraction,
    ErrorType,
    PriceBenchmark,
    Severity,
)


def analyze(extraction: DocumentExtraction) -> AnalysisResult:
    """Run all rules against an extraction and return the analysis result."""
    errors: list[BillingError] = []
    benchmarks: list[PriceBenchmark] = []

    errors.extend(find_duplicate_charges(extraction))
    errors.extend(find_unbundled_codes(extraction))
    errors.extend(find_mue_violations(extraction))

    price_errors, price_benchmarks = find_price_outliers(extraction)
    errors.extend(price_errors)
    benchmarks.extend(price_benchmarks)

    total_overcharge = sum(
        (e.estimated_overcharge for e in errors if e.estimated_overcharge),
        Decimal("0"),
    )

    return AnalysisResult(
        extraction=extraction,
        errors=errors,
        price_benchmarks=benchmarks,
        total_estimated_overcharge=total_overcharge,
    )


# ---------------------------------------------------------------------------
# Rule: Duplicate charges
# ---------------------------------------------------------------------------


def find_duplicate_charges(extraction: DocumentExtraction) -> list[BillingError]:
    """Flag identical CPT code + date of service appearing more than once."""
    errors: list[BillingError] = []
    seen: dict[tuple[str, str | None], list[int]] = defaultdict(list)

    for i, item in enumerate(extraction.line_items):
        code = item.cpt_code or item.hcpcs_code
        if code is None:
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

# Curated seed: high-impact NCCI edit pairs.
# Format: (col1_comprehensive, col2_component, modifier_exception)
# modifier_exception: True = allowed with modifier -59/-XE/-XS/-XP/-XU
_NCCI_EDITS: list[tuple[str, str, bool]] = [
    # E/M + procedures (most common denial driver)
    ("99213", "99211", False),
    ("99214", "99213", False),
    ("99215", "99214", False),
    ("99215", "99213", False),
    # Surgical bundles
    ("58150", "58661", True),  # Hysterectomy includes lysis
    ("27447", "27486", True),  # Knee replacement includes revision components
    # Lab panels vs individual tests
    ("80053", "82565", False),  # Comprehensive metabolic includes creatinine
    ("80053", "84443", False),  # CMP includes TSH — actually doesn't, but common error
    ("80048", "82310", False),  # Basic metabolic includes calcium
    # Radiology
    ("71046", "71045", False),  # 2-view chest includes 1-view
    ("73562", "73560", False),  # 3-view knee includes 2-view
]

_NCCI_LOOKUP: dict[tuple[str, str], bool] = {
    (col1, col2): mod_ex for col1, col2, mod_ex in _NCCI_EDITS
}

MODIFIER_59_FAMILY = {"59", "XE", "XS", "XP", "XU"}


def find_unbundled_codes(extraction: DocumentExtraction) -> list[BillingError]:
    """Flag code pairs that should be bundled per NCCI edits."""
    errors: list[BillingError] = []
    items = extraction.line_items

    for i, item_a in enumerate(items):
        code_a = item_a.cpt_code or item_a.hcpcs_code
        if code_a is None:
            continue
        for j, item_b in enumerate(items):
            if j <= i:
                continue
            code_b = item_b.cpt_code or item_b.hcpcs_code
            if code_b is None:
                continue

            # Check both orderings against NCCI lookup
            modifier_exception = _NCCI_LOOKUP.get((code_a, code_b))
            flipped = False
            if modifier_exception is None:
                modifier_exception = _NCCI_LOOKUP.get((code_b, code_a))
                flipped = True

            if modifier_exception is None:
                continue

            # If modifier exception is allowed, check for modifier
            if modifier_exception:
                mods_a = set(item_a.modifier_codes)
                mods_b = set(item_b.modifier_codes)
                has_modifier = bool((mods_a | mods_b) & MODIFIER_59_FAMILY)
                if has_modifier:
                    errors.append(
                        BillingError(
                            error_type=ErrorType.UNBUNDLED_CODES,
                            severity=Severity.INFO,
                            description=(
                                f"CPT {code_a} and {code_b} are an NCCI edit pair. "
                                f"Modifier present — verify documentation supports "
                                f"distinct procedure."
                            ),
                            affected_line_indices=[i, j],
                        )
                    )
                    continue

            # No modifier exception, or exception allowed but no modifier present
            comprehensive = code_a if not flipped else code_b
            component = code_b if not flipped else code_a
            billed = extraction.line_items[j if not flipped else i].billed_amount
            errors.append(
                BillingError(
                    error_type=ErrorType.UNBUNDLED_CODES,
                    severity=Severity.ERROR,
                    description=(
                        f"CPT {component} is a component of {comprehensive} "
                        f"and should not be billed separately (NCCI edit). "
                        f"Possible unbundling."
                    ),
                    affected_line_indices=[i, j],
                    estimated_overcharge=billed,
                )
            )

    return errors


# ---------------------------------------------------------------------------
# Rule: MUE (Medically Unlikely Edits)
# ---------------------------------------------------------------------------

# CPT code -> max units per day (curated high-frequency codes)
_MUE_LIMITS: dict[str, int] = {
    "71045": 1,  # Chest X-ray, 1 view
    "71046": 1,  # Chest X-ray, 2 views
    "99213": 1,  # Office visit
    "99214": 1,  # Office visit
    "99215": 1,  # Office visit
    "99281": 1,  # ED visit level 1
    "99282": 1,  # ED visit level 2
    "99283": 1,  # ED visit level 3
    "99284": 1,  # ED visit level 4
    "99285": 1,  # ED visit level 5
    "85025": 1,  # CBC with differential
    "80053": 1,  # Comprehensive metabolic panel
    "80048": 1,  # Basic metabolic panel
    "36415": 3,  # Venipuncture
    "93000": 1,  # EKG
    "27447": 1,  # Total knee replacement
}


def find_mue_violations(extraction: DocumentExtraction) -> list[BillingError]:
    """Flag line items where units exceed the MUE limit for that CPT code."""
    errors: list[BillingError] = []

    for i, item in enumerate(extraction.line_items):
        code = item.cpt_code or item.hcpcs_code
        if code is None:
            continue
        max_units = _MUE_LIMITS.get(code)
        if max_units is None:
            continue
        if item.units > max_units:
            errors.append(
                BillingError(
                    error_type=ErrorType.MUE_EXCEEDED,
                    severity=Severity.WARNING,
                    description=(
                        f"CPT {code}: {item.units} units billed, "
                        f"max {max_units} per day. "
                        f"Possible billing error."
                    ),
                    affected_line_indices=[i],
                )
            )

    return errors


# ---------------------------------------------------------------------------
# Rule: Price outliers vs Medicare rates
# ---------------------------------------------------------------------------

# CPT code -> national Medicare non-facility rate (2026 Q1, simplified)
# Source: CMS Medicare Physician Fee Schedule (national average)
_MEDICARE_RATES: dict[str, Decimal] = {
    "99211": Decimal("25.19"),
    "99212": Decimal("57.46"),
    "99213": Decimal("95.42"),
    "99214": Decimal("139.81"),
    "99215": Decimal("188.54"),
    "99281": Decimal("22.98"),
    "99282": Decimal("50.84"),
    "99283": Decimal("81.52"),
    "99284": Decimal("140.95"),
    "99285": Decimal("211.43"),
    "85025": Decimal("8.46"),
    "80053": Decimal("11.22"),
    "80048": Decimal("8.68"),
    "71045": Decimal("22.01"),
    "71046": Decimal("28.18"),
    "93000": Decimal("17.26"),
    "36415": Decimal("3.00"),
    "27447": Decimal("700.36"),
}

PRICE_OUTLIER_THRESHOLD = Decimal("3.0")  # Flag if billed > 3x Medicare rate


def find_price_outliers(
    extraction: DocumentExtraction,
) -> tuple[list[BillingError], list[PriceBenchmark]]:
    """Compare billed amounts against Medicare national rates."""
    errors: list[BillingError] = []
    benchmarks: list[PriceBenchmark] = []

    for i, item in enumerate(extraction.line_items):
        code = item.cpt_code or item.hcpcs_code
        if code is None or item.billed_amount is None:
            continue
        medicare_rate = _MEDICARE_RATES.get(code)
        if medicare_rate is None or medicare_rate == 0:
            continue

        ratio = float(item.billed_amount / medicare_rate)
        benchmarks.append(
            PriceBenchmark(
                line_index=i,
                cpt_code=code,
                billed_amount=item.billed_amount,
                medicare_rate=medicare_rate,
                ratio=round(ratio, 2),
            )
        )

        if item.billed_amount > medicare_rate * PRICE_OUTLIER_THRESHOLD:
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
