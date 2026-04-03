# MedBill

**Open-source AI that scans your medical bills, finds errors, and fights back.**

---

Studies suggest a significant percentage of medical bills contain errors — some estimates put it as high as 80%, though the true rate varies. Americans carry $220 billion in medical debt. Insurance companies deny 73 million claims per year — yet fewer than 1% are appealed, even though **more than half are reversed when people do appeal.**

MedBill is free, open-source software that reads your medical bills, explains the charges in plain English, flags billing errors, and drafts appeal letters for denied claims. It runs entirely on your device. Nothing is stored. Ever.

## How It Works

```
Upload bill photo/PDF
        │
        ▼
┌──────────────────┐
│  Qwen2.5-VL-3B         │  Extracts text and structure from document
│  (on-device)     │  Fine-tuned for medical billing layouts
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Rule Engine      │  Flags errors using CMS data:
│  (deterministic)  │  duplicates, unbundling, upcoding, price outliers
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Explanation      │  Plain English summary at 6th-grade reading level
│  + Appeal Letter  │  Draft appeal citing relevant regulations
└──────────────────┘
```

**No cloud. No API calls. No data leaves your device.**

## What MedBill Does

- **Reads your bill** — OCR extraction of line items, CPT/HCPCS codes, amounts, dates
- **Finds errors** — Duplicate charges, unbundled codes (NCCI edits), upcoding, price outliers vs. Medicare rates
- **Explains charges** — Plain English translation of every line item and medical code
- **Drafts appeals** — Draft appeal letters for denied claims, citing ACA and No Surprises Act protections (requires human review before submission)

## Quick Start

```bash
git clone https://github.com/MarcoCornejo/medbill.git
cd medbill
make setup    # Installs Python dependencies via uv
make dev      # Starts local web interface at http://localhost:8000
```

Or via CLI:

```bash
pip install medbill
medbill scan bill.pdf
medbill appeal denial.pdf
```

## Privacy

MedBill is built on a simple principle: **your medical documents are none of our business.**

- Documents are processed in memory and immediately purged
- No accounts, no logins, no cookies
- No data is transmitted anywhere
- Fully functional offline
- Self-hostable via Docker
- The only data we collect: anonymous aggregate counters (documents scanned, errors found) — never content

## Project Structure

```
medbill/
├── src/medbill/      # Core library (OCR, rules, explanations)
├── medbillgen/          # Synthetic medical document generator
├── medbillbench/        # Benchmark for medical billing document AI
├── training/            # Fine-tuning pipeline (Qwen2.5-VL-3B via LoRA)
├── docs/                # Architecture, benchmark methodology, fine-tuning guide
└── tests/
```

### Four Layers

| Layer | What | Why |
|---|---|---|
| **MedBillGen** | Synthetic document generator | Training data factory — photorealistic bills, EOBs, denial letters |
| **MedBillBench** | Public benchmark (500 docs) | First benchmark for medical billing document understanding |
| **MedBill-OCR** | Fine-tuned Qwen2.5-VL-3B (LoRA) | Specialized extraction model, runs on consumer hardware |
| **MedBill App** | Web + CLI interface | The product people actually use |

## Project Status

This project is under active development. Current phase: **foundation and data pipeline.**

- [x] Project architecture and documentation
- [ ] MedBillGen: synthetic document generator
- [ ] MedBillBench: evaluation benchmark
- [ ] MedBill-OCR: fine-tuned model
- [ ] Web application
- [ ] CLI tool
- [ ] Docker image

See [docs/PRD.md](docs/PRD.md) for the full roadmap.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines.

Especially welcome:
- New hospital bill and EOB layout templates
- Benchmark submissions (run your model on MedBillBench)
- Spanish language support (large US population need)
- Real-world validation and feedback

## License

Apache 2.0 — free for everyone, forever. See [LICENSE](LICENSE).

MedBillBench dataset: CC-BY-4.0.
