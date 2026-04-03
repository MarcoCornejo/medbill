# Privacy Policy

**Last updated:** 2026-04-02

## Summary

BillShield processes medical billing documents entirely on-device or in ephemeral server memory. We do not store, transmit, or retain your documents or any data extracted from them.

## What We Process

When you use BillShield to scan a document:
- The document image is loaded into memory
- Text and structure are extracted by the OCR model
- Billing errors are detected by the rule engine
- A plain English explanation and/or draft appeal letter is generated
- Results are returned to you
- **The document and all extracted data are immediately purged from memory**

No step in this pipeline writes to disk, transmits over a network, or persists any document content.

## What We Collect

### Anonymous Impact Counters (Hosted Version Only)

If you use a hosted instance of BillShield, the following **anonymous aggregate counters** are incremented:

| Counter | Example |
|---|---|
| Documents scanned | +1 |
| Errors flagged | +3 |
| Estimated savings (cents) | +45000 |
| Appeals generated | +1 |

These counters are:
- **Not linked to any user, session, IP address, or device**
- **Not linked to any document content**
- **Aggregated by date only** (daily or weekly granularity)
- Stored in a local SQLite database on the server

No individual action can be traced back to a specific user.

### Self-Hosted Instances

Self-hosted BillShield instances have counters disabled by default. Operators may enable them for their own internal tracking.

### Server Access Logs

Web servers produce access logs containing IP addresses, which may constitute personal data under GDPR. For hosted instances:
- Access logs are rotated and deleted within 7 days
- Logs are not correlated with application data
- No log data is shared with third parties

Self-hosters should configure log rotation per their own privacy requirements.

## What We Do NOT Collect

- Document images or PDFs
- Extracted text or field values
- Patient names, dates of birth, addresses, or any PII
- Insurance IDs, member numbers, or group numbers
- Medical codes from individual documents
- IP addresses beyond server access logs
- Browser fingerprints
- Cookies (we use none)
- Analytics or tracking of any kind (no Google Analytics, no pixels, no beacons)

## Cookies

BillShield uses **zero cookies**. No session cookies, no tracking cookies, no third-party cookies.

## Children's Data

BillShield does not collect any personal data from users of any age. Medical bills involving minors are processed with the same ephemeral, no-storage architecture as all other documents.

## Third-Party Services

BillShield's core processing uses no third-party services. All processing happens locally or on the server you choose.

If an optional privacy-first analytics tool (e.g., Plausible, Umami) is enabled on a hosted instance, it will be self-hosted, cookieless, and compliant with GDPR without requiring consent banners.

## GDPR

For users in the European Economic Area or United Kingdom:
- **Legal basis**: Legitimate interest (Art. 6(1)(f)) for anonymous aggregate counters. No personal data is processed in the core application.
- **Data minimization**: We collect the absolute minimum — anonymous counters only.
- **Right to erasure**: No personal data is stored, so there is nothing to erase.
- **Data transfers**: No data is transferred outside the server processing your request.

## HIPAA

BillShield does not store, transmit, or maintain Protected Health Information (PHI). In its default configuration, it does not meet the definition of a HIPAA "covered entity" or "business associate." See [SECURITY.md](SECURITY.md) for details.

Organizations deploying BillShield in a clinical setting should conduct their own compliance review.

## Contact

Privacy questions: privacy@billshield.dev

## Changes

We will update this policy as the project evolves. Changes will be noted in the git history of this file.
