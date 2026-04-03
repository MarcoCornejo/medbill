"""Tests for extraction prompt design and output parsing."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from medbill.core.prompts import (
    EXTRACTION_PROMPT,
    parse_extraction,
    parse_extraction_lenient,
)
from medbill.models import DocumentType

# ---------------------------------------------------------------------------
# Prompt design tests
# ---------------------------------------------------------------------------


class TestPromptDesign:
    """Verify the prompt meets constraints for GLM-OCR (0.9B)."""

    def test_prompt_is_concise(self) -> None:
        """Prompt must leave room for output in a 4-8K token window.

        Rough heuristic: 1 token ~ 4 chars for English/JSON.
        At 4K context, prompt should be under ~1,600 chars (~400 tokens).
        """
        # Generous upper bound: 2,000 chars allows ~500 tokens
        assert len(EXTRACTION_PROMPT) < 2000

    def test_prompt_contains_all_document_types(self) -> None:
        assert "MEDICAL_BILL" in EXTRACTION_PROMPT
        assert "EOB" in EXTRACTION_PROMPT
        assert "DENIAL_LETTER" in EXTRACTION_PROMPT

    def test_prompt_contains_null_instruction(self) -> None:
        assert "null" in EXTRACTION_PROMPT.lower()
        assert "never guess" in EXTRACTION_PROMPT.lower()

    def test_prompt_contains_exact_amount_instruction(self) -> None:
        assert "exact to the cent" in EXTRACTION_PROMPT.lower()

    def test_prompt_specifies_date_format(self) -> None:
        assert "YYYY-MM-DD" in EXTRACTION_PROMPT

    def test_prompt_contains_all_code_types(self) -> None:
        assert "CPT" in EXTRACTION_PROMPT
        assert "HCPCS" in EXTRACTION_PROMPT
        assert "ICD-10" in EXTRACTION_PROMPT
        assert "CARC" in EXTRACTION_PROMPT
        assert "RARC" in EXTRACTION_PROMPT

    def test_prompt_requests_json_only(self) -> None:
        assert "valid JSON only" in EXTRACTION_PROMPT

    def test_prompt_contains_denial_fields(self) -> None:
        assert "is_denied" in EXTRACTION_PROMPT
        assert "carc_codes" in EXTRACTION_PROMPT
        assert "appeal_deadline" in EXTRACTION_PROMPT

    def test_prompt_contains_line_item_fields(self) -> None:
        assert "cpt_code" in EXTRACTION_PROMPT
        assert "billed_amount" in EXTRACTION_PROMPT
        assert "allowed_amount" in EXTRACTION_PROMPT
        assert "patient_responsibility" in EXTRACTION_PROMPT


# ---------------------------------------------------------------------------
# Clean JSON parsing
# ---------------------------------------------------------------------------


def _make_valid_output() -> str:
    """Return a realistic model output as clean JSON."""
    return json.dumps(
        {
            "document_type": "MEDICAL_BILL",
            "patient_name": "Jane Rodriguez",
            "patient_dob": "1985-03-12",
            "provider_name": "Memorial Regional Hospital",
            "provider_npi": "1234567890",
            "claim_number": "CLM-2026-00847",
            "service_dates": ["2026-01-15"],
            "line_items": [
                {
                    "cpt_code": "99214",
                    "hcpcs_code": None,
                    "icd10_codes": ["M54.5"],
                    "modifier_codes": [],
                    "description": "Office visit, established patient, moderate",
                    "units": 1,
                    "date_of_service": "2026-01-15",
                    "billed_amount": "350.00",
                    "allowed_amount": "139.81",
                    "adjustment_amount": "210.19",
                    "patient_responsibility": "45.00",
                },
                {
                    "cpt_code": "85025",
                    "hcpcs_code": None,
                    "icd10_codes": [],
                    "modifier_codes": [],
                    "description": "Complete blood count (CBC) with differential",
                    "units": 1,
                    "date_of_service": "2026-01-15",
                    "billed_amount": "120.00",
                    "allowed_amount": "8.46",
                    "adjustment_amount": "111.54",
                    "patient_responsibility": "8.46",
                },
            ],
            "totals": {
                "total_billed": "470.00",
                "total_allowed": "148.27",
                "total_adjustment": "321.73",
                "total_patient_responsibility": "53.46",
                "insurance_paid": "94.81",
            },
            "denial": {
                "is_denied": False,
                "carc_codes": [],
                "rarc_codes": [],
                "denial_reason_text": None,
                "appeal_deadline": None,
            },
        }
    )


class TestParseCleanJson:
    def test_valid_json(self) -> None:
        raw = _make_valid_output()
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.MEDICAL_BILL
        assert result.patient_name == "Jane Rodriguez"
        assert result.patient_dob == date(1985, 3, 12)
        assert len(result.line_items) == 2
        assert result.line_items[0].cpt_code == "99214"
        assert result.line_items[0].billed_amount == Decimal("350.00")
        assert result.totals.total_billed == Decimal("470.00")
        assert result.denial.is_denied is False

    def test_eob_with_denial(self) -> None:
        raw = json.dumps(
            {
                "document_type": "EOB",
                "patient_name": "John Smith",
                "patient_dob": None,
                "provider_name": "City Medical Center",
                "provider_npi": None,
                "claim_number": "EOB-2026-12345",
                "service_dates": ["2026-02-20"],
                "line_items": [],
                "totals": {
                    "total_billed": "1500.00",
                    "total_allowed": "800.00",
                    "total_adjustment": "700.00",
                    "total_patient_responsibility": "200.00",
                    "insurance_paid": "600.00",
                },
                "denial": {
                    "is_denied": True,
                    "carc_codes": ["CO-4"],
                    "rarc_codes": ["N115"],
                    "denial_reason_text": "Procedure inconsistent with modifier",
                    "appeal_deadline": "2026-08-20",
                },
            }
        )
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.EOB
        assert result.denial.is_denied is True
        assert result.denial.carc_codes == ["CO-4"]
        assert result.denial.appeal_deadline == date(2026, 8, 20)

    def test_denial_letter(self) -> None:
        raw = json.dumps(
            {
                "document_type": "DENIAL_LETTER",
                "patient_name": "Maria Garcia",
                "patient_dob": None,
                "provider_name": None,
                "provider_npi": None,
                "claim_number": "DN-2026-99999",
                "service_dates": [],
                "line_items": [],
                "totals": {},
                "denial": {
                    "is_denied": True,
                    "carc_codes": ["CO-50"],
                    "rarc_codes": [],
                    "denial_reason_text": "Not medically necessary",
                    "appeal_deadline": "2026-04-30",
                },
            }
        )
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.DENIAL_LETTER
        assert result.denial.denial_reason_text == "Not medically necessary"

    def test_minimal_extraction(self) -> None:
        """Model returns only document_type, everything else null/empty."""
        raw = json.dumps(
            {
                "document_type": "MEDICAL_BILL",
                "patient_name": None,
                "patient_dob": None,
                "provider_name": None,
                "provider_npi": None,
                "claim_number": None,
                "service_dates": [],
                "line_items": [],
                "totals": {},
                "denial": {"is_denied": False},
            }
        )
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.MEDICAL_BILL
        assert result.patient_name is None
        assert result.line_items == []
        assert result.totals.total_billed is None


# ---------------------------------------------------------------------------
# Markdown-fenced JSON
# ---------------------------------------------------------------------------


class TestMarkdownFences:
    def test_json_fence(self) -> None:
        raw = "```json\n" + _make_valid_output() + "\n```"
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.MEDICAL_BILL
        assert result.patient_name == "Jane Rodriguez"

    def test_bare_fence(self) -> None:
        raw = "```\n" + _make_valid_output() + "\n```"
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.MEDICAL_BILL

    def test_fence_with_leading_whitespace(self) -> None:
        raw = "  \n```json\n" + _make_valid_output() + "\n```\n  "
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.MEDICAL_BILL


# ---------------------------------------------------------------------------
# BOM and whitespace
# ---------------------------------------------------------------------------


class TestWhitespaceAndBom:
    def test_bom_prefix(self) -> None:
        raw = "\ufeff" + _make_valid_output()
        result = parse_extraction(raw)
        assert result.document_type == DocumentType.MEDICAL_BILL

    def test_leading_trailing_whitespace(self) -> None:
        raw = "\n\n  " + _make_valid_output() + "  \n\n"
        result = parse_extraction(raw)
        assert result.patient_name == "Jane Rodriguez"


# ---------------------------------------------------------------------------
# Truncated JSON repair
# ---------------------------------------------------------------------------


class TestTruncatedJsonRepair:
    def test_truncated_after_first_line_item(self) -> None:
        """Model runs out of tokens mid-output."""
        raw = json.dumps(
            {
                "document_type": "MEDICAL_BILL",
                "patient_name": "Jane Rodriguez",
                "patient_dob": None,
                "provider_name": "Memorial Regional Hospital",
                "provider_npi": None,
                "claim_number": "CLM-2026-00847",
                "service_dates": ["2026-01-15"],
                "line_items": [
                    {
                        "cpt_code": "99214",
                        "hcpcs_code": None,
                        "icd10_codes": [],
                        "modifier_codes": [],
                        "description": "Office visit",
                        "units": 1,
                        "date_of_service": "2026-01-15",
                        "billed_amount": "350.00",
                        "allowed_amount": "139.81",
                        "adjustment_amount": "210.19",
                        "patient_responsibility": "45.00",
                    }
                ],
            }
        )
        # Simulate truncation: remove closing braces and add partial content
        # The complete JSON ends with: ...}]}
        # We truncate to remove the outer }, leaving an incomplete object
        truncated = raw[:-1]  # Remove final }
        # This should repair by re-adding the }
        result = parse_extraction(truncated)
        assert result.document_type == DocumentType.MEDICAL_BILL
        assert result.patient_name == "Jane Rodriguez"

    def test_truncated_mid_array(self) -> None:
        """Truncation happens inside the line_items array."""
        partial = (
            '{"document_type": "MEDICAL_BILL", '
            '"patient_name": "Test Patient", '
            '"service_dates": [], '
            '"line_items": [{"cpt_code": "99214", "units": 1, '
            '"billed_amount": "350.00"}]'
            # Missing closing brace for outer object
        )
        result = parse_extraction(partial)
        assert result.patient_name == "Test Patient"
        assert len(result.line_items) == 1


# ---------------------------------------------------------------------------
# Malformed / unparseable output
# ---------------------------------------------------------------------------


class TestMalformedOutput:
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse"):
            parse_extraction("")

    def test_plain_text_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse"):
            parse_extraction("I cannot extract data from this image.")

    def test_array_instead_of_object_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected JSON object"):
            parse_extraction('[{"document_type": "MEDICAL_BILL"}]')

    def test_invalid_document_type_raises(self) -> None:
        raw = json.dumps({"document_type": "PRESCRIPTION"})
        with pytest.raises(ValueError):
            parse_extraction(raw)


# ---------------------------------------------------------------------------
# Lenient parsing
# ---------------------------------------------------------------------------


class TestLenientParsing:
    def test_valid_input_returns_extraction(self) -> None:
        raw = _make_valid_output()
        result = parse_extraction_lenient(raw)
        assert result is not None
        assert result.document_type == DocumentType.MEDICAL_BILL

    def test_invalid_input_returns_none(self) -> None:
        result = parse_extraction_lenient("not json at all")
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        result = parse_extraction_lenient("")
        assert result is None


# ---------------------------------------------------------------------------
# Pydantic coercion edge cases
# ---------------------------------------------------------------------------


class TestPydanticCoercion:
    def test_amounts_as_strings_coerce_to_decimal(self) -> None:
        """GLM-OCR outputs amounts as strings per prompt instruction."""
        raw = json.dumps(
            {
                "document_type": "MEDICAL_BILL",
                "line_items": [
                    {
                        "cpt_code": "99214",
                        "billed_amount": "350.00",
                        "units": 1,
                    }
                ],
            }
        )
        result = parse_extraction(raw)
        assert result.line_items[0].billed_amount == Decimal("350.00")

    def test_amounts_as_numbers_coerce_to_decimal(self) -> None:
        """Some models output numeric values despite string instruction."""
        raw = json.dumps(
            {
                "document_type": "MEDICAL_BILL",
                "line_items": [
                    {
                        "cpt_code": "99214",
                        "billed_amount": 350.00,
                        "units": 1,
                    }
                ],
            }
        )
        result = parse_extraction(raw)
        assert result.line_items[0].billed_amount is not None

    def test_missing_optional_fields_default(self) -> None:
        """Model omits optional fields entirely (not null, just absent)."""
        raw = json.dumps(
            {
                "document_type": "MEDICAL_BILL",
            }
        )
        result = parse_extraction(raw)
        assert result.patient_name is None
        assert result.line_items == []
        assert result.totals.total_billed is None
        assert result.denial.is_denied is False
