# CLAUDE.md — MedBill

Open-source, privacy-first medical bill scanner. Finds billing errors, explains charges in plain English, generates draft appeal letters. Runs entirely on-device.

## Package Management

Use `uv` for everything. Never `pip install` directly. Never `--break-system-packages`.

## Key Commands

```bash
make setup    # Install all deps via uv
make dev      # Start local dev server (http://localhost:8000)
```

## Code Conventions

- **Docstrings**: Google style. Only on public APIs.
- **Commits**: Conventional (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `data:`, `train:`)
- **No `Any` types.** Be explicit with type hints.

## Project Layout

New source code goes in these locations:
- `src/medbill/` — core library (extraction, analysis, explanation)
- `src/medbill/web/` — FastAPI app, Jinja2 templates, static assets
- `medbillgen/` — synthetic document generator (separate package)
- `medbillbench/` — benchmark framework (separate package)
- `training/` — fine-tuning scripts and configs
- `tests/` — all tests (mirror src/ structure)

## Testing

- Deterministic: pinned seeds (`42`), no network calls in unit tests
- Integration tests tagged separately (`pytest -m integration`)
- Only synthetic data in tests — never real patient data

## Verification (ALWAYS DO THIS)

Run `make lint && make test` before considering any task complete.

## What NOT to Do

- Don't add LLM API calls to the core processing pipeline — it must work fully offline
- Don't store any user data beyond anonymous counters
- Don't add Node.js or any JS build tooling — frontend is server-rendered
- Don't create files without tests
- Don't use `pip install` directly — always use `uv`
- Don't use `print()` for debugging — use the `logging` module
- Don't import from `medbillgen` in `src/medbill` — they are separate packages
- Don't log document content, extracted text, patient names, or dollar amounts from specific documents — see `.claude/rules/privacy.md`
