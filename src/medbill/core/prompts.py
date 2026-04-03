"""Extraction prompts for GLM-OCR medical billing document AI.

Design rationale:
- Single-pass extraction (not multi-pass) because GLM-OCR's 0.9B context
  cannot afford the overhead of classify-then-extract. Classification is
  a single field in the output, effectively free.
- Compact JSON schema (not Pydantic .model_json_schema()) because the full
  schema with $defs, descriptions, and constraints burns ~1,200 tokens.
  The flattened version below is ~350 tokens, leaving headroom for output.
- No few-shot examples. At 0.9B params with 4-8K context, few-shot examples
  compete directly with output space. The fine-tuned LoRA adapter provides
  implicit few-shot knowledge. For the base model, the schema itself is
  sufficiently instructive.
- Explicit "null if not found" instruction to suppress hallucination, which
  is the dominant failure mode for small VLMs on missing fields.
- Token budget: ~400 tokens prompt + ~3,600 tokens reserved for output.
  A bill with 15 line items produces ~2,500 output tokens.

Output handling:
- Try json.loads() directly first (GLM-OCR native extraction mode).
- Strip markdown fences (```json ... ```) if present.
- Strip leading/trailing whitespace and BOM.
- If partial JSON, attempt repair via truncation to last valid '}'.
- Feed result to DocumentExtraction.model_validate() which handles
  type coercion (str -> Decimal, str -> date) via Pydantic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from medbill.models import DocumentExtraction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The extraction prompt
# ---------------------------------------------------------------------------

# This is the exact text sent alongside the document image to GLM-OCR.
# It uses the model's native information-extraction mode: a system
# instruction followed by an inline JSON schema.
#
# Key design choices visible in the prompt text:
#   1. "Extract ... from this medical document" -- task framing
#   2. Inline flattened schema -- not $ref, not full Pydantic output
#   3. "null if not found" repeated for high-risk fields
#   4. Exact format specs for codes and amounts
#   5. No prose filler -- every token earns its place

EXTRACTION_PROMPT = """\
Extract all structured data from this medical document into JSON.

Schema:
{
  "document_type": "MEDICAL_BILL" | "EOB" | "DENIAL_LETTER",
  "patient_name": str | null,
  "patient_dob": "YYYY-MM-DD" | null,
  "provider_name": str | null,
  "provider_npi": str | null,
  "claim_number": str | null,
  "service_dates": ["YYYY-MM-DD"],
  "line_items": [
    {
      "cpt_code": "5-digit" | null,
      "hcpcs_code": "letter+4digits" | null,
      "icd10_codes": ["A00.0"],
      "modifier_codes": ["25","59"],
      "description": str | null,
      "units": int,
      "date_of_service": "YYYY-MM-DD" | null,
      "billed_amount": "0.00" | null,
      "allowed_amount": "0.00" | null,
      "adjustment_amount": "0.00" | null,
      "patient_responsibility": "0.00" | null
    }
  ],
  "totals": {
    "total_billed": "0.00" | null,
    "total_allowed": "0.00" | null,
    "total_adjustment": "0.00" | null,
    "total_patient_responsibility": "0.00" | null,
    "insurance_paid": "0.00" | null
  },
  "denial": {
    "is_denied": bool,
    "carc_codes": ["CO-4"],
    "rarc_codes": ["N115"],
    "denial_reason_text": str | null,
    "appeal_deadline": "YYYY-MM-DD" | null
  }
}

Rules:
- Use null for any field not found. Never guess.
- Dollar amounts: exact to the cent, as strings ("350.00").
- Codes: copy exactly as printed (CPT, HCPCS, ICD-10, CARC, RARC).
- Dates: YYYY-MM-DD format.
- Output valid JSON only, no explanation.\
"""

# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

# Regex to strip markdown code fences that some models wrap around JSON
_FENCE_RE = re.compile(
    r"^[\s]*```(?:json)?[\s]*\n?(.*?)[\s]*```[\s]*$",
    re.DOTALL,
)

# BOM that occasionally appears in model output
_BOM = "\ufeff"


def parse_extraction(raw: str) -> DocumentExtraction:
    """Parse raw model output into a validated DocumentExtraction.

    Handles:
    - Clean JSON
    - Markdown-fenced JSON (```json ... ```)
    - Leading/trailing whitespace and BOM
    - Truncated JSON (attempts brace-matching repair)

    Raises ValueError if the output cannot be parsed or validated.
    """
    cleaned = _clean_raw_output(raw)
    data = _parse_json(cleaned)
    data = _sanitize_model_output(data)
    return DocumentExtraction.model_validate(data)


def parse_extraction_lenient(raw: str) -> DocumentExtraction | None:
    """Like parse_extraction, but returns None instead of raising.

    Use this in production where a failed parse should trigger fallback
    logic rather than crash the request.
    """
    try:
        return parse_extraction(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Failed to parse model output: %s", type(exc).__name__)
        return None


def _clean_raw_output(raw: str) -> str:
    """Strip fences, BOM, and whitespace from raw model output."""
    text = raw.strip()
    if text.startswith(_BOM):
        text = text[len(_BOM) :]

    # Strip markdown code fences
    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()

    return text


# Values that are schema placeholders echoed back by the model
_PLACEHOLDER_VALUES = {
    "YYYY-MM-DD",
    "str",
    "str | null",
    "bool",
    "int",
    "5-digit",
    "letter+4digits",
    "A00.0",
}

# Date format normalization patterns
_DATE_FORMATS = [
    "%m/%d/%y",  # 01/02/05
    "%m/%d/%Y",  # 01/02/2005
    "%m-%d-%Y",  # 01-02-2005
    "%Y-%m-%d",  # 2005-01-02 (already correct)
]


def _normalize_date(value: str) -> str | None:
    """Try to parse various date formats into YYYY-MM-DD."""
    from datetime import datetime

    if value in _PLACEHOLDER_VALUES or not value.strip():
        return None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            # Handle 2-digit years: 00-30 -> 2000s, 31-99 -> 1900s
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000 if dt.year <= 30 else dt.year + 1900)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _sanitize_model_output(data: dict[str, Any]) -> dict[str, Any]:
    """Clean up common VLM output quirks before Pydantic validation.

    Handles:
    - Empty strings -> None (for optional fields)
    - Schema placeholder values -> None (model echoed the template)
    - Single values where lists expected -> wrapped in list
    - Hallucinated denial fields on non-denial documents
    """
    # Convert empty strings to None at top level
    for key in ("patient_name", "patient_dob", "provider_name", "provider_npi", "claim_number"):
        if isinstance(data.get(key), str) and (
            data[key].strip() == "" or data[key] in _PLACEHOLDER_VALUES
        ):
            data[key] = None

    # Normalize patient_dob date
    dob = data.get("patient_dob")
    if isinstance(dob, str):
        data["patient_dob"] = _normalize_date(dob)

    # service_dates: ensure it's a list and normalize dates
    sd = data.get("service_dates")
    if isinstance(sd, str):
        normalized = _normalize_date(sd)
        data["service_dates"] = [normalized] if normalized else []
    elif isinstance(sd, list):
        data["service_dates"] = [d for s in sd if isinstance(s, str) and (d := _normalize_date(s))]

    # Clean line items
    for item in data.get("line_items", []):
        if not isinstance(item, dict):
            continue
        # Null out placeholder codes
        for code_field in ("cpt_code", "hcpcs_code"):
            val = item.get(code_field)
            if isinstance(val, str) and (val in _PLACEHOLDER_VALUES or val.strip() == ""):
                item[code_field] = None
        # Clean placeholder lists
        for list_field in ("icd10_codes", "modifier_codes"):
            lst = item.get(list_field, [])
            if isinstance(lst, list):
                item[list_field] = [v for v in lst if v not in _PLACEHOLDER_VALUES]
        # Empty string description -> None
        desc = item.get("description")
        if isinstance(desc, str) and (desc.strip() == "" or desc in _PLACEHOLDER_VALUES):
            item["description"] = None
        # Normalize date_of_service
        dos = item.get("date_of_service")
        if isinstance(dos, str):
            item["date_of_service"] = _normalize_date(dos)
        # Fix units: if it looks like a dollar amount (has decimal), it's misplaced
        units_val = item.get("units")
        if isinstance(units_val, str):
            stripped = units_val.strip()
            if "." in stripped:
                # Model put a dollar amount in units — move to billed_amount if empty
                if not item.get("billed_amount") or item.get("billed_amount") == "0.00":
                    item["billed_amount"] = stripped
                item["units"] = 1
            elif stripped == "" or stripped in _PLACEHOLDER_VALUES:
                item["units"] = 1
            else:
                try:
                    item["units"] = int(stripped)
                except ValueError:
                    item["units"] = 1

    # Clean denial: if not explicitly denied, reset placeholder values
    denial = data.get("denial", {})
    if isinstance(denial, dict):
        for field in ("denial_reason_text", "appeal_deadline"):
            val = denial.get(field)
            if isinstance(val, str) and (val.strip() == "" or val in _PLACEHOLDER_VALUES):
                denial[field] = None
        # Clean placeholder codes from denial
        for code_list in ("carc_codes", "rarc_codes"):
            lst = denial.get(code_list, [])
            if isinstance(lst, list):
                denial[code_list] = [v for v in lst if v not in _PLACEHOLDER_VALUES]
        # If all denial fields are empty/placeholder, it's not a real denial
        if (
            not denial.get("carc_codes")
            and not denial.get("rarc_codes")
            and not denial.get("denial_reason_text")
        ):
            denial["is_denied"] = False

    # Clean totals empty strings
    totals = data.get("totals", {})
    if isinstance(totals, dict):
        for key, val in list(totals.items()):
            if isinstance(val, str) and val.strip() == "":
                totals[key] = None

    return data


def _parse_json(text: str) -> dict[str, Any]:
    """Parse JSON with fallback repair for truncated output.

    GLM-OCR (0.9B) occasionally runs out of generation tokens mid-output,
    producing valid JSON up to a truncation point. We attempt repair by
    finding the last valid closing brace.
    """
    # Fast path: valid JSON
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        msg = f"Expected JSON object, got {type(result).__name__}"
        raise ValueError(msg)
    except json.JSONDecodeError:
        pass

    # Repair path: truncated JSON -- find last balanced '}'
    repaired = _repair_truncated_json(text)
    if repaired is not None:
        try:
            result = json.loads(repaired)
            if isinstance(result, dict):
                logger.info("Recovered truncated JSON output via brace repair")
                return result
        except json.JSONDecodeError:
            pass

    msg = "Could not parse model output as JSON"
    raise ValueError(msg)


def _repair_truncated_json(text: str) -> str | None:
    """Attempt to repair truncated JSON by closing open braces/brackets.

    Strategy: walk backwards from the end to find the deepest point where
    adding closing delimiters produces valid JSON. This handles the common
    case where generation stops mid-line-item.

    Returns the repaired string, or None if repair is not feasible.
    """
    # Only attempt repair if it looks like it starts as JSON
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return None

    # Count unclosed delimiters
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape = False

    for char in stripped:
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            open_braces += 1
        elif char == "}":
            open_braces -= 1
        elif char == "[":
            open_brackets += 1
        elif char == "]":
            open_brackets -= 1

    if open_braces <= 0 and open_brackets <= 0:
        # Not a truncation issue
        return None

    # Trim trailing incomplete values (e.g., '"description": "Offi')
    # Find the last comma or colon that precedes the truncation
    trimmed = stripped.rstrip()

    # Remove trailing partial string value if mid-string
    if in_string:
        # Find the last unescaped quote that opened this string
        last_quote = trimmed.rfind('"')
        if last_quote > 0:
            # Back up to before the key-value pair
            before = trimmed[:last_quote].rstrip()
            if before.endswith(":"):
                # Remove the key too -- find the quote before the colon
                before = before[:-1].rstrip()
                key_quote = before.rfind('"')
                if key_quote > 0:
                    trimmed = before[:key_quote].rstrip().rstrip(",")
            elif before.endswith(","):
                trimmed = before[:-1]
            else:
                trimmed = before

    # Close remaining delimiters
    suffix = "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)
    return trimmed + suffix
