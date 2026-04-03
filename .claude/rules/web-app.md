---
name: Web Application Rules
description: FastAPI + HTMX patterns, template conventions, and privacy constraints
type: policy
globs: ["src/medbill/web/**", "src/medbill/web/templates/**", "src/medbill/web/static/**"]
---

## Stack

- FastAPI with Jinja2Templates for server-side rendering
- HTMX for dynamic behavior (no JS framework, no build step)
- Tailwind CSS (CDN in dev, future: purged static build)
- Zero client-side tracking: no cookies, no analytics JS, no session IDs

## Privacy-Critical Upload Flow

The scan endpoint follows a strict memory-safety pattern:
1. Read upload into `content: bytes` with size limit check
2. Close the UploadFile immediately (releases temp spool)
3. Wrap in `io.BytesIO` for the extractor
4. After extraction: `file_bytes.close()` + `del content, file_bytes`
5. Never write uploaded content to disk, database, or log

When modifying the scan endpoint, preserve ALL of these steps. Missing any one creates a data leak.

## Template Conventions

- Templates live in `src/medbill/web/templates/`
- Static assets in `src/medbill/web/static/`
- Every page must include the disclaimer: "This tool is not legal or medical advice."
- Dollar amounts: always format to 2 decimal places
- Use HTMX attributes (`hx-post`, `hx-target`, `hx-swap`) instead of JS event handlers

## Extractor is Swappable

`_extractor` in app.py follows the `Extractor` Protocol from `core/ocr.py`.
`MockExtractor` is used in dev. Future: `GlmOcrExtractor` for production.
Never hardcode extraction logic in the web layer.
