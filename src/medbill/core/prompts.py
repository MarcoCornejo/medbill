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
