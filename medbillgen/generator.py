"""Orchestrate synthetic document generation.

Produces DocumentExtraction objects with ground-truth annotations.
Output is JSON files matching the medbill schema.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from medbill.models import (
    DocumentExtraction,
    DocumentType,
    LineItem,
    Totals,
)
from medbillgen.encounter import Encounter, generate_encounter
from medbillgen.errors import inject_errors


def generate_batch(
    count: int,
    seed: int = 42,
    output_dir: Path | None = None,
    error_rate: float = 0.3,
) -> list[dict[str, object]]:
    """Generate a batch of synthetic medical billing documents.

    Returns list of dicts with 'extraction' and 'injected_errors' keys.
    Optionally writes JSON files to output_dir.
    """
    rng = random.Random(seed)
    results: list[dict[str, object]] = []

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        encounter = generate_encounter(rng)
        injected = inject_errors(encounter, rng, error_rate=error_rate)
        extraction = _encounter_to_extraction(encounter, rng)

        record: dict[str, object] = {
            "extraction": json.loads(extraction.model_dump_json()),
            "injected_errors": [asdict(e) for e in injected],
            "metadata": {
                "encounter_type": encounter.encounter_type,
                "seed": seed,
                "index": i,
            },
        }
        results.append(record)

        if output_dir:
            out_file = output_dir / f"doc_{i:05d}.json"
            out_file.write_text(json.dumps(record, indent=2, default=str))

    return results


def _encounter_to_extraction(encounter: Encounter, rng: random.Random) -> DocumentExtraction:
    """Convert an Encounter into a DocumentExtraction."""
    markup_factor = Decimal(str(round(rng.uniform(1.5, 6.0), 2)))

    line_items: list[LineItem] = []
    for proc in encounter.procedures:
        billed = (proc.base_medicare_rate * markup_factor).quantize(Decimal("0.01"))
        allowed = proc.base_medicare_rate
        adjustment = (billed - allowed).quantize(Decimal("0.01"))
        copay_pct = Decimal(str(round(rng.uniform(0.1, 0.3), 2)))
        patient_resp = (allowed * copay_pct).quantize(Decimal("0.01"))

        line_items.append(
            LineItem(
                cpt_code=proc.cpt_code,
                description=proc.description,
                icd10_codes=list(proc.icd10_codes),
                units=proc.units,
                date_of_service=encounter.service_date,
                billed_amount=billed,
                allowed_amount=allowed,
                adjustment_amount=adjustment,
                patient_responsibility=patient_resp,
            )
        )

    total_billed = sum(
        (item.billed_amount for item in line_items if item.billed_amount),
        Decimal("0"),
    )
    total_allowed = sum(
        (item.allowed_amount for item in line_items if item.allowed_amount),
        Decimal("0"),
    )
    total_patient = sum(
        (item.patient_responsibility for item in line_items if item.patient_responsibility),
        Decimal("0"),
    )
    insurance_paid = total_allowed - total_patient

    return DocumentExtraction(
        document_type=DocumentType.MEDICAL_BILL,
        patient_name=encounter.patient_name,
        patient_dob=encounter.patient_dob,
        provider_name=encounter.provider_name,
        provider_npi=encounter.provider_npi,
        claim_number=f"CLM-{encounter.service_date.year}-{rng.randint(10000, 99999)}",
        service_dates=[encounter.service_date],
        line_items=line_items,
        totals=Totals(
            total_billed=total_billed,
            total_allowed=total_allowed,
            total_patient_responsibility=total_patient,
            insurance_paid=insurance_paid,
        ),
    )
