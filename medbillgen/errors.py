"""Inject realistic billing errors into encounters.

Each error type has a configurable probability. Injected errors are
tracked so we can measure the rule engine's detection accuracy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from medbillgen.encounter import Encounter, Procedure

# E/M code families for upcoding injection
_EM_OFFICE = ["99212", "99213", "99214", "99215"]
_EM_ER = ["99281", "99282", "99283", "99284", "99285"]


@dataclass
class InjectedError:
    """Record of an error deliberately injected into an encounter."""

    error_type: str
    description: str
    affected_indices: list[int]


def inject_errors(
    encounter: Encounter,
    rng: random.Random,
    error_rate: float = 0.3,
) -> list[InjectedError]:
    """Inject billing errors into an encounter's procedures.

    Modifies encounter.procedures in place. Returns list of injected errors.
    """
    injected: list[InjectedError] = []

    if rng.random() < error_rate:
        err = _inject_duplicate(encounter, rng)
        if err:
            injected.append(err)

    if rng.random() < error_rate * 0.5:
        err = _inject_unbundled(encounter, rng)
        if err:
            injected.append(err)

    if rng.random() < error_rate * 0.4:
        err = _inject_mue_violation(encounter, rng)
        if err:
            injected.append(err)

    return injected


def _inject_duplicate(encounter: Encounter, rng: random.Random) -> InjectedError | None:
    """Duplicate a random procedure."""
    if not encounter.procedures:
        return None

    idx = rng.randint(0, len(encounter.procedures) - 1)
    original = encounter.procedures[idx]
    new_idx = len(encounter.procedures)
    encounter.procedures.append(original)

    return InjectedError(
        error_type="DUPLICATE_CHARGE",
        description=f"Duplicated CPT {original.cpt_code} (line {idx} -> {new_idx})",
        affected_indices=[idx, new_idx],
    )


def _inject_unbundled(encounter: Encounter, rng: random.Random) -> InjectedError | None:
    """Add a component code that should be bundled with an existing code."""
    for i, proc in enumerate(encounter.procedures):
        if proc.cpt_code == "80053":
            unbundled = Procedure(
                cpt_code="82565",
                description="Creatinine, blood (should be included in CMP)",
                base_medicare_rate=Decimal("5.89"),
                icd10_codes=["N18.9"],
            )
            new_idx = len(encounter.procedures)
            encounter.procedures.append(unbundled)
            return InjectedError(
                error_type="UNBUNDLED_CODES",
                description=f"Added CPT 82565 (component of 80053 at line {i})",
                affected_indices=[i, new_idx],
            )
    return None


def _inject_mue_violation(encounter: Encounter, rng: random.Random) -> InjectedError | None:
    """Set units above the MUE limit for a procedure."""
    for i, proc in enumerate(encounter.procedures):
        # Target single-unit procedures that have MUE limits
        if proc.cpt_code in ("71046", "85025", "80053", "93000") and proc.units == 1:
            inflated_units = rng.randint(3, 8)
            encounter.procedures[i] = Procedure(
                cpt_code=proc.cpt_code,
                description=proc.description,
                base_medicare_rate=proc.base_medicare_rate,
                icd10_codes=list(proc.icd10_codes),
                units=inflated_units,
            )
            return InjectedError(
                error_type="MUE_EXCEEDED",
                description=f"CPT {proc.cpt_code}: inflated units from 1 to {inflated_units}",
                affected_indices=[i],
            )
    return None
