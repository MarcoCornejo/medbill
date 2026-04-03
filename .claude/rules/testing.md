---
name: Testing Standards
description: Test conventions, synthetic data requirements, and quality gates
type: policy
globs: ["tests/**", "**/*test*"]
---

## Test File Structure

- `tests/test_models.py` — Pydantic model construction, serialization, roundtrips
- `tests/test_rules.py` — individual rule functions + composed `analyze()` pipeline
- `tests/test_web.py` — FastAPI endpoints via `TestClient`
- `tests/test_cli.py` — CLI argument parsing and output verification
- `tests/test_medbillgen.py` — encounter generation, error injection, determinism
- `tests/test_e2e.py` — full pipeline: MedBillGen → rule engine → web/CLI → output validation

## Patterns

- Test classes: `class TestFeatureName` (no `unittest.TestCase`)
- Use helper factories to reduce boilerplate (e.g., `_bill(*items)` in test_rules.py)
- Web tests: `fastapi.testclient.TestClient` fixture
- Pin random seeds to `42` for reproducibility
- No network calls in unit tests
- `@pytest.mark.integration` marker registered but not yet applied to any tests

## Data Rules

- ONLY use synthetic data from MedBillGen or inline construction
- NEVER use real patient data, even "anonymized" samples
- `tests/fixtures/` does not exist yet — use inline data or MedBillGen for now

## Assertions

- Assert exact values, not ranges (deterministic pipeline + pinned seeds)
- Dollar amounts: compare `Decimal` to the cent (`assert amount == Decimal("3247.80")`)
- Extracted codes: exact string match, case-sensitive
- For floats (ratios): use `pytest.approx()` or round to 2 decimal places

## Quality Gates

- All new code must have tests
- Coverage target: 80% minimum (`fail_under = 80` in pyproject.toml)
- `make lint && make test` must pass before any commit
