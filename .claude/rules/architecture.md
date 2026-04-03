---
name: System Architecture
description: Processing pipeline, layer responsibilities, and key design decisions
type: reference
globs: ["**/*.py", "**/*.md", "Makefile", "pyproject.toml"]
---

## Processing Pipeline

```
Document (photo/PDF)
    → GLM-OCR (extraction) → Structured JSON
    → Rule Engine (analysis) → Error flags + price benchmarks
    → Templates/SLM (explanation) → Plain English + appeal letter
    → Results to user, document purged, anonymous counter +1
```

## Layer Responsibilities

### Layer 1: Document Extraction (GLM-OCR)
- Input: document image + extraction prompt (JSON schema)
- Output: structured JSON (patient name, provider, line items with codes and amounts, dates, totals)
- Runs locally on consumer hardware (~4GB VRAM, runs on MacBook M1/M2 8GB via Ollama)
- Base model: GLM-OCR (0.9B params, zai-org/GLM-OCR). Fine-tuned via LoRA for medical billing documents.
- GLM-OCR is a VLM (CogViT encoder + GLM-0.5B decoder), NOT just an OCR model. It has native JSON schema extraction, table understanding (77.6 on table tests), and scores 94.62 on OmniDocBench V1.5 (#1).
- Fallback: Qwen2.5-VL-3B if GLM-OCR proves insufficient after benchmarking. Granite-Docling-258M as future lightweight option.

### Layer 2: Rule Engine (Pure Python)
- Input: structured extraction JSON
- Output: list of flagged errors with confidence and explanation
- Uses CMS fee schedule for price benchmarking (charge vs Medicare allowed amount)
- Uses NCCI edits for unbundling detection
- Uses CPT code families for upcoding detection
- Deterministic — no model, no randomness, no API calls

### Layer 3: Explanation (Templates → SLM)
- V1: Jinja2 templates that slot in extracted values
- V2: Fine-tuned SLM (distilled from Claude) for more natural prose
- Generates: plain English summary, per-line explanations, appeal letter draft
- Appeal letters cite specific regulations (ACA, No Surprises Act) based on denial type

## Key Design Decisions

- **No LLM in core pipeline**: The processing must work fully offline with zero API cost
- **Rule engine over ML for error detection**: Billing rules are deterministic. NCCI edits use a curated ~1,500-pair dict lookup with boolean modifier exceptions. CMS fee schedule uses national rates in SQLite (~3-5MB). No ML needed for error detection.
- **Ephemeral processing**: No database for documents. SQLite only for anonymous impact counters.
- **Single language**: Python for everything — ML, API, CLI. No Node.js.
- **Server-rendered frontend**: Jinja2 + HTMX + Tailwind. No JS build step.

## Prompt Templates (for SLM/LLM explanation layer)

When writing prompts for the explanation layer:
- Write at 6th-grade reading level (Flesch-Kincaid)
- Never use medical jargon without parenthetical explanation
- Always include dollar amounts when discussing charges
- Always include deadlines when discussing appeals
- Say "this part isn't clear" when uncertain — never guess
- End with numbered next steps
