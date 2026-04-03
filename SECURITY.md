# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in MedBill, please report it responsibly.

**Email:** security@medbill.dev (or open a [private security advisory](https://github.com/MarcoCornejo/medbill/security/advisories/new) on GitHub)

**Response time:** We aim to acknowledge reports within 48 hours and provide a fix within 7 days for critical issues.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

**Do not** open a public issue for security vulnerabilities.

## Health Data Handling

MedBill processes medical billing documents that may contain Protected Health Information (PHI). Our architecture is designed to make data retention **impossible**, not just unlikely:

- **No storage:** Documents are processed in memory and immediately purged after results are returned. There is no database, filesystem cache, or log that retains document content.
- **No transmission:** In the default local/self-hosted configuration, no data leaves the user's device. The web application processes documents server-side in ephemeral memory.
- **No logging of content:** Application logs record processing metadata (document type, page count, timing) but **never** document content, extracted text, patient names, or any field values.
- **Anonymous counters only:** The only persisted data is aggregate impact counters (total documents scanned, total errors found) with no link to individual users or documents.

## HIPAA Statement

MedBill is a client-side / self-hosted tool. In its default configuration, it does not meet the HIPAA definition of a "covered entity" or "business associate" because it does not store, transmit, or maintain PHI. Users deploying MedBill in a clinical or organizational setting should conduct their own compliance review.

## Supported Versions

| Version | Supported |
|---|---|
| Latest release | Yes |
| Previous minor | Best effort |
| Older | No |

## Dependencies

We use Dependabot to monitor dependencies for known vulnerabilities. Critical dependency updates are merged within 48 hours.
