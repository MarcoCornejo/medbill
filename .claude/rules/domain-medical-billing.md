---
name: Medical Billing Domain Knowledge
description: Terminology, codes, regulations, and domain context for medical billing document processing
type: reference
globs: ["**/*.py", "**/*.md"]
---

## Medical Billing Codes

- **CPT** (Current Procedural Terminology): 5-digit codes for medical procedures. Owned by AMA. Example: 99213 (office visit, established patient, moderate complexity).
- **HCPCS** (Healthcare Common Procedure Coding System): Level I = CPT. Level II = alphanumeric codes for supplies, equipment, drugs. Example: J0585 (botulinum toxin injection).
- **ICD-10**: Diagnosis codes. Format: letter + digits (e.g., M54.5 = low back pain). Required on every claim to justify procedures.
- **CARC** (Claim Adjustment Reason Codes): Why a payer adjusted a charge. Example: CO-4 = "procedure code inconsistent with modifier."
- **RARC** (Remittance Advice Remark Codes): Supplemental explanation for adjustments.
- **NCCI/CCI Edits**: CMS-published rules defining which procedure code pairs cannot be billed together (unbundling detection).

## Key Regulations

- **HIPAA**: Governs Protected Health Information (PHI). Our synthetic data approach means HIPAA does not apply to training/test data.
- **No Surprises Act** (2022): Protects patients from surprise out-of-network bills in emergency and certain non-emergency situations.
- **ACA Appeal Rights** (42 U.S.C. Section 300gg-19): Patients have the right to internal and external review of insurance claim denials.
- **CMS Transparency Rule**: Hospitals must publish machine-readable price files. Data is public but inconsistent.
- **501(r)**: Nonprofit hospitals must offer financial assistance policies.

## Document Types

- **Medical Bill**: Hospital/provider statement showing charges for services rendered. Contains: patient info, provider info, service dates, line items with CPT/HCPCS codes, charges, adjustments, patient responsibility.
- **EOB** (Explanation of Benefits): Insurance company statement showing what was billed, what was allowed, what insurance paid, and what the patient owes. NOT a bill.
- **Denial Letter**: Insurance notification that a claim was denied, with reason codes and appeal instructions.

## Common Billing Errors

### Implemented (V1 scope)
- **Duplicate charges**: Same CPT code + same date of service appearing twice
- **Unbundling**: Billing component codes separately when a bundled code exists (detected via NCCI edits — note: NCCI edits have Column 1/2 pairs, modifier exceptions, and temporal effective dates; this is NOT a simple lookup table)
- **Upcoding**: Billing a higher-complexity code than the service warrants (e.g., 99215 instead of 99213)
- **Balance billing**: Charging the patient the difference between billed and allowed amounts for in-network services (illegal in most cases)
- **Expired codes**: Using CPT codes retired in previous years

### Known gaps (future phases)
- **Modifier misuse**: Incorrect use of modifiers -25, -59, -XE/-XS/-XP/-XU (top denial driver nationally)
- **Place of service errors**: POS 11 vs 22 vs 23 pricing discrepancies
- **Units of service errors**: Wrong quantity billed (especially infusions, PT, anesthesia time)
- **Timely filing violations**: Claims submitted past payer deadline
- **Coordination of benefits errors**: Common with dual-coverage patients
- **Gender/age-specific mismatches**: Procedure inappropriate for patient demographics
- **Frequency limitations**: Services exceeding allowed frequency (e.g., colonoscopy every 10 years)

### Known regulation gaps (for appeal letter generation)
- ERISA (29 U.S.C. Section 1133) for employer-sponsored plans
- Medicare Secondary Payer rules
- State prompt-pay statutes
- Mental Health Parity and Addiction Equity Act (MHPAEA)

## Data Sources (All Public Domain)

- CMS Medicare Physician Fee Schedule — maps CPT to Medicare allowed amounts
- CMS Hospital Transparency Files — mandated price data
- NCCI/CCI Edits — quarterly publication of bundling rules
- ICD-10 code set — WHO/CMS, freely available
- CARC/RARC codes — published by X12/CMS
- CPT descriptions — owned by AMA, requires license. Use HCPCS Level I descriptions from CMS where possible.
