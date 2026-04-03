---
name: Pydantic Model Conventions
description: Patterns for data models that form the contract between pipeline layers
type: policy
globs: ["src/medbill/models.py", "medbillgen/encounter.py"]
---

## Model Hierarchy

models.py defines the contracts between all three layers:
- OCR layer outputs `DocumentExtraction`
- Rule engine consumes `DocumentExtraction`, produces `AnalysisResult`
- Explanation layer consumes `AnalysisResult`

Never add a model without understanding which layer boundary it serves.

## Patterns to Follow

- All money fields: `Decimal`, never `float`. Use `Decimal("0.01")` quantization.
- All enums: `StrEnum` (not `Enum`), uppercase values matching the class name pattern.
- Optional fields: use `X | None = None`, not `Optional[X]`.
- List fields: always `Field(default_factory=list)`, never `= []`.
- Nested defaults: `Field(default_factory=ModelClass)` (e.g., `Totals`, `DenialInfo`).
- No `Any` types anywhere in models.py.
- Properties (not fields) for computed values (`error_count`, `has_errors`).

## medbillgen Uses Dataclasses, Not Pydantic

`Encounter` and `Procedure` in medbillgen are `@dataclass`, not `BaseModel`.
`Procedure` is `frozen=True`. `InjectedError` is a plain `@dataclass`.
medbillgen imports Pydantic models FROM medbill for output, but its internal types are dataclasses.

## Adding New Error Types

1. Add the variant to `ErrorType` enum in models.py
2. Add the detection function in `analysis/rules.py`
3. Wire it into the `analyze()` function
4. Add error injection in `medbillgen/errors.py`
5. Add tests covering detection and non-detection (with modifiers if applicable)
