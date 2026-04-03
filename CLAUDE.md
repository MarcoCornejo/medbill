# CLAUDE.md -- MedBill

Open-source, privacy-first medical bill scanner. Finds billing errors, explains charges in plain English, generates draft appeal letters. Runs entirely on-device.

## Package Management

Use `uv` for everything. Never `pip install` directly. Never `--break-system-packages`.

## Key Commands

```bash
make setup    # Install all deps via uv
make dev      # Start local dev server (http://localhost:8000)
make lint     # ruff check + ruff format --check + mypy
make test     # pytest -v -x
make format   # Auto-format (ruff format + ruff check --fix)
```

## Code Conventions

- **Docstrings**: Google style. Only on public APIs.
- **Commits**: Conventional (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `data:`, `train:`)
- **No `Any` types.** Be explicit with type hints. mypy strict mode is on.
- **Decimal for money.** Never use float for dollar amounts. Compare to the cent.
- **Import as** `medbill.*` (e.g., `from medbill.models import ...`), never `src.medbill.*`.
- **medbillgen imports medbill models** but medbill must NEVER import from medbillgen.

## Verification (ALWAYS DO THIS)

Run `make lint && make test` before considering any task complete.

## What NOT to Do

- Don't add LLM API calls to the core processing pipeline -- it must work fully offline
- Don't store any user data beyond anonymous counters
- Don't add Node.js or any JS build tooling -- frontend is server-rendered
- Don't create files without tests
- Don't use `pip install` directly -- always use `uv`
- Don't use `print()` for debugging -- use the `logging` module
- Don't import from `medbillgen` in `src/medbill` -- they are separate packages
- Don't log document content, extracted text, patient names, or dollar amounts from specific documents -- see `.claude/rules/privacy.md`
