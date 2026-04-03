# Contributing to MedBill

Thank you for your interest in helping people understand their medical bills. Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/MarcoCornejo/medbill.git
cd medbill

# Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
make setup

# Run tests
make test

# Start development server
make dev
```

## How to Contribute

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/MarcoCornejo/medbill/labels/good%20first%20issue). These are scoped, well-documented tasks suitable for new contributors.

### Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Make your changes
4. Run `make lint` and `make test`
5. Commit using [conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, etc.)
6. Open a pull request using the PR template

### What We're Looking For

- **New document templates** — Hospital bill and EOB layouts from different regions and providers
- **Benchmark submissions** — Run your model on MedBillBench and submit results
- **Spanish language support** — Translation of explanation templates and UI
- **Real-world validation** — Anonymized feedback on extraction accuracy
- **Bug fixes and improvements** — Always welcome

## Code Style

- **Python 3.12+** with type hints on all functions
- **Formatting:** `ruff format` (enforced in CI)
- **Linting:** `ruff check` (enforced in CI)
- **Type checking:** `mypy --strict` (enforced in CI)
- **Tests:** Every module has tests. New features require tests.
- **No `Any` types.** Be explicit.

## Privacy Rules

MedBill handles medical billing documents. When contributing:

- **Never** add logging that captures document content or PII
- **Never** add network calls in the core processing pipeline
- **Never** use real patient data in tests — only synthetic data from MedBillGen
- **Never** add tracking, analytics, or telemetry beyond anonymous aggregate counters

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add EOB template for Anthem BCBS
fix: correct NCCI edit lookup for modifier 59
docs: add benchmark submission guide
refactor: simplify price comparison logic
test: add edge cases for duplicate charge detection
data: update CMS fee schedule to 2026 Q2
train: add augmentation ablation results
```

## Questions?

Open a [discussion](https://github.com/MarcoCornejo/medbill/discussions) or reach out in issues. We're friendly.
