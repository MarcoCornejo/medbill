# MedBill Architecture

## System Overview

MedBill is a four-layer system for medical billing document understanding. Each layer is independently useful and publishable.

```
┌─────────────────────────────────────────────────────────────┐
│                     BILLSHIELD SYSTEM                        │
│                                                              │
│  LAYER 1: MedBillGen ──── Synthetic Document Generator       │
│  Generates photorealistic medical bills, EOBs, denial        │
│  letters with ground-truth annotations for training.         │
│                                                              │
│  LAYER 2: MedBillBench ── Benchmark (500 documents)          │
│  First public benchmark for medical billing document AI.     │
│  Published on HuggingFace as CC-BY-4.0 dataset.              │
│                                                              │
│  LAYER 3: MedBill-OCR ── Fine-Tuned Qwen2.5-VL-3B (LoRA)       │
│  Specialized extraction model trained on MedBillGen,         │
│  evaluated on MedBillBench. ~50MB adapter.                   │
│                                                              │
│  LAYER 4: MedBill App ── Web + CLI Interface              │
│  Upload → Extract → Analyze → Explain → Appeal               │
└─────────────────────────────────────────────────────────────┘
```

## Processing Pipeline

```
Document (photo/PDF)
       │
       ▼
┌─────────────────┐
│   Qwen2.5-VL-3B       │  Fine-tuned for medical billing
│   (Extraction)  │  Runs locally, ~$0/document
└────────┬────────┘
         │ Structured JSON
         ▼
┌─────────────────┐
│  Rule Engine     │  CMS fee schedule, NCCI edits, code validation
│  (Analysis)      │  Pure Python, deterministic, zero cost
└────────┬────────┘
         │ Errors + price benchmarks
         ▼
┌─────────────────┐
│  Templates/SLM  │  Jinja2 templates (V1) or fine-tuned SLM (V2)
│  (Explanation)   │  Plain English + appeal letters
└────────┬────────┘
         │
         ▼
    Results to user
    Document purged from memory
    Anonymous counter incremented (+1)
```

## Layer 1: MedBillGen — Synthetic Document Generator

### Why Synthetic Data

HIPAA prohibits using real PHI without authorization. But we don't need real data — we need documents that are visually and structurally identical to real bills. Our synthetic documents are superior because:

- **Perfect ground truth** — every field value is known at generation time
- **Controlled distribution** — coverage across all document types, formats, error types
- **Controlled difficulty** — clean, moderately degraded, and heavily degraded variants
- **Zero legal risk** — fully synthetic data is not PHI

### Generation Pipeline

1. **Encounter generation** — Synthea or CMS DE-SynPUF for realistic patient encounters
2. **Coding & pricing** — CPT/HCPCS codes from specialty distributions, charges from CMS fee schedule with hospital markups (1.5x-8x Medicare)
3. **Demographics** — Faker for synthetic patient/provider information
4. **Template rendering** — Jinja2 HTML templates → Playwright/Chromium → PDF → image
5. **Augmentation** — rotation, blur, lighting, perspective warp, JPEG artifacts, fold creases, shadows
6. **Annotation** — auto-generated ground-truth JSON from template data
7. **Error injection** — deliberate billing errors (duplicates, unbundling, upcoding) with ground-truth labels

### Error Injection

| Error Type | Implementation | Frequency |
|---|---|---|
| Duplicate charge | Same CPT + same date appears twice | 15% |
| Unbundled codes | Bundled procedure split into components (NCCI edit pairs) | 10% |
| Upcoding | CPT replaced with higher-paying code in same family | 8% |
| Diagnosis mismatch | ICD-10 doesn't support billed procedure | 7% |
| Missing fields | Omit required fields (service date, NPI) | 10% |

### Templates

25 templates built from publicly available sources:
- 12 hospital bill layouts (academic, community, urgent care, ED, etc.)
- 7 insurer EOB formats (UHC, Anthem, Aetna, Cigna, Humana, Medicare, generic BCBS)
- 6 denial letter categories (medical necessity, out-of-network, prior auth, timely filing, not covered, coding error)

## Layer 2: MedBillBench — Benchmark

500 annotated documents. First public benchmark for medical billing document understanding.

### Composition

| Document Type | Count | Templates |
|---|---|---|
| Medical bill | 200 | 12 hospital layouts |
| EOB | 200 | 7 insurer formats |
| Denial letter | 100 | 6 denial categories |

### MedBillScore (Composite Metric, 0-100)

```
MedBillScore = (
    0.10 * Classification Accuracy +
    0.25 * Code Extraction F1 +
    0.25 * Amount Accuracy +
    0.15 * Date Extraction F1 +
    0.10 * Name Extraction F1 +
    0.10 * Structural Accuracy +
    0.05 * Denial Field F1
) * 100
```

Full benchmark methodology: [BENCHMARK.md](BENCHMARK.md)

## Layer 3: MedBill-OCR — Fine-Tuned Model

LoRA fine-tune of Qwen2.5-VL-3B (0.9B) via LLaMA-Factory.

- **Rank**: 16, **Alpha**: 32
- **Training**: 4,000 synthetic documents, 3 epochs
- **Adapter size**: ~50MB
- **Hardware**: Single A100 (4-6 hours) or RTX 4090 (8 hours)

Full fine-tuning methodology: [FINE_TUNING.md](FINE_TUNING.md)

## Layer 4: MedBill App

### Web Interface
- FastAPI backend serving Jinja2 templates
- HTMX for interactivity (upload, progress, results)
- Tailwind CSS for styling
- Zero JavaScript build step, zero Node.js

### CLI
- `medbill scan bill.pdf` — extract and analyze
- `medbill appeal denial.pdf` — generate appeal letter
- Distributed via PyPI (`pip install medbill`)

### Privacy Architecture
- Documents processed in memory, purged after results returned
- No accounts, no cookies, no tracking
- SQLite for anonymous aggregate counters only
- Self-hostable via Docker

## Design Principles

1. **Privacy is non-negotiable.** No user data is stored. The architecture makes retention impossible, not just unlikely.
2. **Offline-first.** Core processing works with zero network calls. No LLM API dependency.
3. **Accuracy over completeness.** Better to flag 5 real errors than 5 real plus 3 false positives. "We're not sure about this charge" is valid output.
4. **Plain language is the product.** Every output at 6th-grade reading level. If the translation is harder to read than the original, we failed.
5. **Frugal architecture.** Zero cost at rest. No external database. Single Python runtime. Single Docker container.
