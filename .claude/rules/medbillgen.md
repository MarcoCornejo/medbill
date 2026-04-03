---
name: MedBillGen Synthetic Data Generator
description: Rules for the synthetic data generator package
type: policy
globs: ["medbillgen/**", "tests/test_medbillgen.py"]
---

## Purpose

MedBillGen generates synthetic medical billing documents with ground-truth error annotations.
It is used for: training data (LoRA fine-tune), benchmark evaluation, and test fixtures.
It is a SEPARATE package from medbill -- never import medbillgen from src/medbill/.

## Dependency Direction

medbillgen imports FROM medbill (models, types). medbill never imports FROM medbillgen.
This is a hard boundary. The core library must not depend on the generator.

## Reproducibility

- All randomness goes through a `random.Random(seed)` instance, never `random.random()`.
- Seed 42 is the default for training data. Seed 43 for validation.
- Same seed + same code = identical output. Tests assert exact values against pinned seeds.

## Error Injection Pattern

1. `generate_encounter()` creates a clean encounter
2. `inject_errors()` mutates it in place, returns `list[InjectedError]`
3. Each injector (`_inject_duplicate`, `_inject_unbundled`) has independent probability
4. `InjectedError` records exactly which indices were affected -- this is ground truth

When adding a new error type:
- Add `_inject_{type}()` in `errors.py`
- Wire it into `inject_errors()` with configurable probability
- The injected error's `error_type` string must match `ErrorType` enum values
- Add the corresponding detection rule in `analysis/rules.py`

## Pricing Realism

- `base_medicare_rate` on Procedure comes from CMS fee schedule
- Hospital markup is randomized (1.5x-6.0x) to simulate real-world variance
- Copay percentage is randomized (10%-30%)
- These ranges were chosen to match published CMS transparency data distributions
