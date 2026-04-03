"""Generate realistic medical encounters.

Each encounter represents a patient visit with procedures, diagnoses,
and charges. Uses CMS fee schedule distributions for realistic pricing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Procedure:
    """A single medical procedure in an encounter."""

    cpt_code: str
    description: str
    base_medicare_rate: Decimal
    icd10_codes: list[str] = field(default_factory=list)
    units: int = 1


@dataclass
class Encounter:
    """A complete patient encounter with procedures and charges."""

    encounter_type: str
    patient_name: str
    patient_dob: date
    provider_name: str
    provider_npi: str
    service_date: date
    procedures: list[Procedure] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Procedure pools (realistic CPT codes, descriptions, Medicare rates)
# ---------------------------------------------------------------------------

_OFFICE_VISITS: list[Procedure] = [
    Procedure("99212", "Office visit, established, straightforward", Decimal("57.46"), ["Z00.00"]),
    Procedure("99213", "Office visit, established, low complexity", Decimal("95.42"), ["M54.5"]),
    Procedure(
        "99214", "Office visit, established, moderate complexity", Decimal("139.81"), ["E11.9"]
    ),
    Procedure("99215", "Office visit, established, high complexity", Decimal("188.54"), ["J06.9"]),
]

_ER_VISITS: list[Procedure] = [
    Procedure("99281", "ED visit, self-limited/minor", Decimal("22.98"), ["R51.9"]),
    Procedure("99282", "ED visit, low/moderate severity", Decimal("50.84"), ["S61.419A"]),
    Procedure("99283", "ED visit, moderate severity", Decimal("81.52"), ["R10.9"]),
    Procedure("99284", "ED visit, high severity", Decimal("140.95"), ["R07.9"]),
    Procedure("99285", "ED visit, high severity, threat to life", Decimal("211.43"), ["I21.9"]),
]

_LABS: list[Procedure] = [
    Procedure("85025", "Complete blood count (CBC) with differential", Decimal("8.46"), ["D64.9"]),
    Procedure("80053", "Comprehensive metabolic panel", Decimal("11.22"), ["E87.6"]),
    Procedure("80048", "Basic metabolic panel", Decimal("8.68"), ["E87.6"]),
    Procedure("84443", "Thyroid stimulating hormone (TSH)", Decimal("17.99"), ["E03.9"]),
    Procedure("82565", "Creatinine, blood", Decimal("5.89"), ["N18.9"]),
]

_IMAGING: list[Procedure] = [
    Procedure("71046", "Chest X-ray, 2 views", Decimal("28.18"), ["R05.9"]),
    Procedure("73562", "X-ray knee, 3 views", Decimal("28.80"), ["M17.11"]),
    Procedure("93000", "Electrocardiogram (EKG), 12-lead", Decimal("17.26"), ["R00.0"]),
]

_PROCEDURES: list[Procedure] = [
    Procedure("36415", "Venipuncture", Decimal("3.00")),
    Procedure("96372", "Therapeutic injection, subcutaneous/IM", Decimal("16.94")),
    Procedure("99070", "Supplies and materials", Decimal("10.00")),
]

_HOSPITAL_NAMES: list[str] = [
    "Memorial Regional Hospital",
    "St. Joseph Medical Center",
    "University Health System",
    "Riverside Community Hospital",
    "Cedar Valley Medical Center",
    "Pacific Northwest Medical Group",
    "Lakewood General Hospital",
    "Mountain View Health",
]

_FIRST_NAMES: list[str] = [
    "Jane",
    "Maria",
    "James",
    "Robert",
    "Patricia",
    "Linda",
    "Michael",
    "David",
    "Jennifer",
    "Sarah",
    "Carlos",
    "Wei",
    "Ahmed",
    "Priya",
    "Kenji",
    "Fatima",
    "Olga",
    "Emmanuel",
]

_LAST_NAMES: list[str] = [
    "Rodriguez",
    "Smith",
    "Johnson",
    "Williams",
    "Chen",
    "Patel",
    "Kim",
    "Garcia",
    "Martinez",
    "Lee",
    "Brown",
    "Davis",
    "Wilson",
    "Taylor",
    "Anderson",
    "Thomas",
    "Jackson",
    "Nguyen",
]


def generate_encounter(rng: random.Random, encounter_type: str | None = None) -> Encounter:
    """Generate a single realistic medical encounter.

    Args:
        rng: Seeded random instance for reproducibility.
        encounter_type: One of 'office', 'er', 'lab'. Random if None.
    """
    if encounter_type is None:
        encounter_type = rng.choice(["office", "er", "lab"])

    patient_name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"
    patient_dob = date(
        rng.randint(1945, 2005),
        rng.randint(1, 12),
        rng.randint(1, 28),
    )
    provider_name = rng.choice(_HOSPITAL_NAMES)
    provider_npi = "".join(str(rng.randint(0, 9)) for _ in range(10))
    service_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 180))

    procedures = _build_procedures(rng, encounter_type)

    return Encounter(
        encounter_type=encounter_type,
        patient_name=patient_name,
        patient_dob=patient_dob,
        provider_name=provider_name,
        provider_npi=provider_npi,
        service_date=service_date,
        procedures=procedures,
    )


def _build_procedures(rng: random.Random, encounter_type: str) -> list[Procedure]:
    """Build a realistic set of procedures for an encounter type."""
    procedures: list[Procedure] = []

    if encounter_type == "office":
        procedures.append(rng.choice(_OFFICE_VISITS))
        if rng.random() < 0.6:
            procedures.append(rng.choice(_LABS))
        if rng.random() < 0.3:
            procedures.append(rng.choice(_IMAGING))
        if rng.random() < 0.5:
            procedures.append(Procedure("36415", "Venipuncture", Decimal("3.00")))

    elif encounter_type == "er":
        procedures.append(rng.choice(_ER_VISITS))
        procedures.append(rng.choice(_LABS))
        if rng.random() < 0.7:
            procedures.append(
                Procedure("71046", "Chest X-ray, 2 views", Decimal("28.18"), ["R05.9"])
            )
        if rng.random() < 0.5:
            procedures.append(Procedure("93000", "EKG, 12-lead", Decimal("17.26"), ["R00.0"]))
        procedures.append(Procedure("36415", "Venipuncture", Decimal("3.00")))

    elif encounter_type == "lab":
        num_labs = rng.randint(2, 4)
        selected = rng.sample(_LABS, min(num_labs, len(_LABS)))
        procedures.extend(selected)
        procedures.append(Procedure("36415", "Venipuncture", Decimal("3.00")))

    return procedures
