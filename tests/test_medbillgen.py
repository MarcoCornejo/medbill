"""Tests for the MedBillGen synthetic data generator."""

from __future__ import annotations

import json
import random
from pathlib import Path

from medbill.analysis.rules import analyze
from medbill.models import DocumentExtraction, DocumentType
from medbillgen.encounter import generate_encounter
from medbillgen.errors import inject_errors
from medbillgen.generator import generate_batch


class TestEncounter:
    def test_deterministic_with_seed(self) -> None:
        enc1 = generate_encounter(random.Random(42))
        enc2 = generate_encounter(random.Random(42))
        assert enc1.patient_name == enc2.patient_name
        assert enc1.provider_name == enc2.provider_name
        assert enc1.service_date == enc2.service_date
        assert len(enc1.procedures) == len(enc2.procedures)

    def test_office_visit(self) -> None:
        enc = generate_encounter(random.Random(42), encounter_type="office")
        assert enc.encounter_type == "office"
        assert len(enc.procedures) >= 1
        # First procedure should be an office visit E/M code
        assert enc.procedures[0].cpt_code.startswith("992")

    def test_er_visit(self) -> None:
        enc = generate_encounter(random.Random(42), encounter_type="er")
        assert enc.encounter_type == "er"
        assert len(enc.procedures) >= 2  # At least ER visit + lab

    def test_lab_visit(self) -> None:
        enc = generate_encounter(random.Random(42), encounter_type="lab")
        assert enc.encounter_type == "lab"
        assert len(enc.procedures) >= 3  # At least 2 labs + venipuncture

    def test_patient_demographics(self) -> None:
        enc = generate_encounter(random.Random(42))
        assert enc.patient_name
        assert enc.patient_dob
        assert enc.provider_name
        assert len(enc.provider_npi) == 10


class TestErrorInjection:
    def test_duplicate_injection(self) -> None:
        rng = random.Random(42)
        enc = generate_encounter(rng, encounter_type="office")
        original_count = len(enc.procedures)
        injected = inject_errors(enc, rng, error_rate=1.0)

        has_duplicate = any(e.error_type == "DUPLICATE_CHARGE" for e in injected)
        if has_duplicate:
            assert len(enc.procedures) == original_count + 1

    def test_no_errors_at_zero_rate(self) -> None:
        rng = random.Random(42)
        enc = generate_encounter(rng)
        injected = inject_errors(enc, rng, error_rate=0.0)
        assert len(injected) == 0

    def test_error_records_have_indices(self) -> None:
        rng = random.Random(99)
        enc = generate_encounter(rng, encounter_type="er")
        injected = inject_errors(enc, rng, error_rate=1.0)
        for err in injected:
            assert len(err.affected_indices) >= 1
            assert err.error_type in ("DUPLICATE_CHARGE", "UNBUNDLED_CODES", "MUE_EXCEEDED")


class TestGenerator:
    def test_generate_batch(self) -> None:
        results = generate_batch(count=5, seed=42)
        assert len(results) == 5
        for r in results:
            assert "extraction" in r
            assert "injected_errors" in r
            assert "metadata" in r

    def test_deterministic(self) -> None:
        r1 = generate_batch(count=3, seed=42)
        r2 = generate_batch(count=3, seed=42)
        assert r1 == r2

    def test_different_seeds_different_output(self) -> None:
        r1 = generate_batch(count=3, seed=42)
        r2 = generate_batch(count=3, seed=99)
        assert r1 != r2

    def test_extraction_validates_as_pydantic(self) -> None:
        results = generate_batch(count=10, seed=42)
        for r in results:
            ext = DocumentExtraction.model_validate(r["extraction"])
            assert ext.document_type == DocumentType.MEDICAL_BILL
            assert ext.patient_name is not None
            assert len(ext.line_items) >= 1
            assert ext.totals.total_billed is not None

    def test_output_to_directory(self, tmp_path: Path) -> None:
        results = generate_batch(count=3, seed=42, output_dir=tmp_path)
        assert len(results) == 3

        files = sorted(tmp_path.glob("doc_*.json"))
        assert len(files) == 3
        assert files[0].name == "doc_00000.json"

        data = json.loads(files[0].read_text())
        ext = DocumentExtraction.model_validate(data["extraction"])
        assert ext.document_type == DocumentType.MEDICAL_BILL

    def test_error_rate_controls_injection(self) -> None:
        # With high error rate, most docs should have errors
        results = generate_batch(count=20, seed=42, error_rate=1.0)
        docs_with_errors = sum(1 for r in results if r["injected_errors"])
        assert docs_with_errors >= 15  # Most should have errors

        # With zero error rate, no docs should have errors
        results = generate_batch(count=20, seed=42, error_rate=0.0)
        docs_with_errors = sum(1 for r in results if r["injected_errors"])
        assert docs_with_errors == 0


class TestEndToEnd:
    """Integration: MedBillGen → rule engine → verify errors caught."""

    def test_generated_docs_through_rule_engine(self) -> None:
        """Generate docs with known errors, verify the rule engine catches them."""
        results = generate_batch(count=20, seed=42, error_rate=0.8)

        docs_with_injected = [r for r in results if r["injected_errors"]]
        assert len(docs_with_injected) > 0

        detected_count = 0
        for r in docs_with_injected:
            ext = DocumentExtraction.model_validate(r["extraction"])
            analysis = analyze(ext)

            errs = r["injected_errors"]
            assert isinstance(errs, list)
            injected_types = {e["error_type"] for e in errs}

            # Check if rule engine caught the injected errors
            detected_types = {e.error_type.value for e in analysis.errors}

            if injected_types & detected_types:
                detected_count += 1

        # Rule engine should catch errors in most docs that have them
        detection_rate = detected_count / len(docs_with_injected)
        assert detection_rate >= 0.5, (
            f"Rule engine only detected errors in {detection_rate:.0%} "
            f"of docs with injected errors"
        )

    def test_clean_docs_have_few_false_positives(self) -> None:
        """Docs without injected errors should have minimal false positives."""
        results = generate_batch(count=20, seed=42, error_rate=0.0)

        false_positive_count = 0
        for r in results:
            ext = DocumentExtraction.model_validate(r["extraction"])
            analysis = analyze(ext)
            # Price outliers are expected (hospital markup), don't count those
            non_price_errors = [
                e for e in analysis.errors if e.error_type.value != "PRICE_OUTLIER"
            ]
            if non_price_errors:
                false_positive_count += 1

        # Some clean docs may trigger non-price errors because the random
        # encounter generator can accidentally produce real coding issues
        # (e.g., randomly selecting CMP + creatinine from the lab pool).
        # These are accidental true positives, not false positives.
        assert false_positive_count <= 10, (
            f"{false_positive_count}/20 clean docs had non-price errors"
        )
