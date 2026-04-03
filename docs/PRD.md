# BillShield — Product Requirements Document

**Version:** 0.3.0 (MVP-first approach)

## Philosophy

Build simple. Ship. Gather feedback. Iterate.

Each phase delivers a standalone, usable artifact. No phase depends on a future phase being complete.

## Phase 1: MedBillGen — Synthetic Document Generator (Weeks 1-2)

**Goal:** A working pipeline that generates photorealistic medical billing documents with ground-truth annotations.

| Task | Output |
|---|---|
| Download and process CMS fee schedule, CARC/RARC codes, ICD-10 mappings | `medbillgen/data/` |
| Build encounter generator (Synthea or CMS DE-SynPUF) | `encounter.py`, `coding.py`, `pricing.py` |
| Build demographics generator (Faker) | `demographics.py` |
| Create 9 HTML/CSS templates (3 per document type) | `templates/` |
| Build renderer (Playwright/Chromium HTML to PDF to Image) | `renderer.py` |
| Build augmentation pipeline | `augmentor.py` |
| Build error injection system | `errors.py` |
| Build auto-annotator | `annotator.py` |
| Expand to 25 templates, generate 5,000 training + 500 validation documents | Full dataset |
| Build CLI: `medbillgen generate --count 1000 --seed 42` | Standalone tool |

**Deliverable:** `make generate-data` produces 5,000 annotated synthetic documents.

**Ship:** Publish MedBillGen as standalone tool with README. Useful on its own for document AI research.

## Phase 2: MedBillBench — Benchmark (Week 3)

**Goal:** A rigorous evaluation framework with baselines.

| Task | Output |
|---|---|
| Generate 500 benchmark documents (held-out test set) | `medbillbench/data/test/` |
| Build hash manifest for integrity | `manifest.json` |
| Implement all metrics (MedBillScore, Code F1, Amount Accuracy, etc.) | `metrics.py` |
| Build evaluator framework with model runner protocol | `evaluator.py`, `runners/` |
| Implement GLM-OCR and Textract baselines | Initial runners |
| Generate leaderboard | `leaderboard.md` |
| Build CLI: `medbillbench evaluate --model glm-ocr` | Standalone tool |

**Deliverable:** `make evaluate-all` runs baselines and produces a leaderboard.

**Ship:** Publish MedBillBench on HuggingFace (CC-BY-4.0). Useful on its own for benchmarking document AI models.

## Phase 3: Fine-Tuning (Week 4)

**Goal:** A fine-tuned GLM-OCR adapter that beats the base model on MedBillBench.

| Task | Output |
|---|---|
| Convert MedBillGen output to LLaMA-Factory format | `prepare_data.py` |
| Run LoRA fine-tune | Best checkpoint |
| Run ablation studies (data scale, LoRA rank, augmentation, templates) | Ablation results |
| Error analysis notebook | `03_error_analysis.ipynb` |
| Export adapter for HuggingFace | `billshield-ocr-lora/` |

**Deliverable:** Published model adapter + benchmark results.

**Ship:** Publish BillShield-OCR on HuggingFace (MIT). Useful on its own for anyone doing medical document AI.

## Phase 4: Application (Weeks 5-7)

**Goal:** The consumer-facing product.

| Task | Output |
|---|---|
| OCR integration layer | `core/ocr.py` |
| Document classifier | `core/classifier.py` |
| Extractors (bill, EOB, denial) | `extractors/` |
| Rule engine (CMS price benchmark, NCCI edits, duplicate detection) | `analyzers/` |
| Plain English translator (templates) | `generators/plain_english.py` |
| Appeal letter generator (6 denial categories) | `generators/appeal_letter.py` |
| FastAPI endpoints: `/scan`, `/appeal`, `/health` | Working API |
| Web interface (Jinja2 + HTMX + Tailwind) | Full UI |
| CLI: `billshield scan`, `billshield appeal` | Working CLI |
| Anonymous impact counters (SQLite) | `/impact` endpoint |

**Deliverable:** Working app, self-hostable, privacy-first.

## Phase 5: Launch (Week 8)

| Task | Output |
|---|---|
| Dockerfile (multi-stage build) | Production container |
| Docker Compose for self-hosting | `docker-compose.yml` |
| Rate limiting + monitoring | Operational |
| Final leaderboard with all baselines | Published |
| Demo video (30s + 3min) | Launch assets |
| Technical blog post | Published |
| Launch: HN, Twitter, Reddit | Live |

## Success Metrics

- Documents scanned (aggregate counter)
- Errors flagged (aggregate counter)
- Total estimated savings flagged (aggregate)
- Appeal letters generated (aggregate)
- GitHub stars
- HuggingFace downloads (model + dataset)
- Press coverage
