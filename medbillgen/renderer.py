"""Render synthetic medical bills as images using Pillow.

Zero external dependencies beyond Pillow (already installed).
Produces clear, readable bill images for VLM benchmarking.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from medbill.models import DocumentExtraction

# Page dimensions (letter size at 150 DPI)
PAGE_W = 1275
PAGE_H = 1650
MARGIN = 80

# Addresses for synthetic providers
_ADDRESSES = [
    "1200 Healthcare Blvd, Suite 300, Anytown, US 12345",
    "500 Medical Center Dr, Building A, Springfield, US 67890",
    "8900 University Ave, 4th Floor, Riverside, US 34567",
]


def render_bill(
    extraction: DocumentExtraction,
    output_path: Path,
    seed: int = 42,
) -> Path:
    """Render a DocumentExtraction as a PNG image."""
    rng = random.Random(seed)
    img = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(img)

    # Use default font (available everywhere)
    try:
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 14
        )
        font_bold: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 16
        )
        font_small: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 11
        )
        font_title: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 22
        )
    except (OSError, AttributeError):
        font = ImageFont.load_default()
        font_bold = font
        font_small = font
        font_title = font

    y: float = MARGIN
    x = MARGIN
    max_x = PAGE_W - MARGIN

    def text(t: str, *, size: str = "normal", bold: bool = False, align: str = "left") -> None:
        nonlocal y
        f = {"title": font_title, "small": font_small, "normal": font_bold if bold else font}[size]
        if align == "right":
            bbox = draw.textbbox((0, 0), t, font=f)
            tw = bbox[2] - bbox[0]
            draw.text((max_x - tw, y), t, fill="black", font=f)
        else:
            draw.text((x, y), t, fill="black", font=f)
        y += getattr(f, "size", 14) + 6

    def line() -> None:
        nonlocal y
        draw.line([(x, y), (max_x, y)], fill="gray", width=1)
        y += 8

    # Header
    provider = extraction.provider_name or "General Hospital"
    text(provider.upper(), size="title", bold=True)
    text(rng.choice(_ADDRESSES), size="small")
    npi = extraction.provider_npi or f"{rng.randint(1000000000, 9999999999)}"
    text(f"NPI: {npi}", size="small")
    y += 4
    line()

    # Title
    y += 4
    text("PATIENT STATEMENT OF CHARGES", bold=True)
    y += 4
    line()

    # Patient info
    text(f"Patient:    {extraction.patient_name or 'Patient'}")
    if extraction.patient_dob:
        text(f"DOB:        {extraction.patient_dob}")
    text(f"Account #:  {extraction.claim_number or ''}")
    if extraction.service_dates:
        text(f"Service:    {extraction.service_dates[0]}")
    y += 8
    line()

    # Column headers
    cols = [x, x + 90, x + 170, x + 520, x + 580, x + 680, x + 790, x + 900]
    headers = [
        "Date",
        "CPT/HCPCS",
        "Description",
        "Qty",
        "Billed",
        "Allowed",
        "Adjust.",
        "You Owe",
    ]
    for ci, header in enumerate(headers):
        draw.text((cols[ci], y), header, fill="black", font=font_bold)
    y += 20
    line()

    # Line items
    for item in extraction.line_items:
        if y > PAGE_H - 250:
            break  # Don't overflow page

        dos = str(item.date_of_service or "")
        code = item.cpt_code or item.hcpcs_code or ""
        if item.modifier_codes:
            code += f"-{','.join(item.modifier_codes)}"
        desc = (item.description or "")[:38]
        units = str(item.units)
        billed = f"${float(item.billed_amount):.2f}" if item.billed_amount else ""
        allowed = f"${float(item.allowed_amount):.2f}" if item.allowed_amount else ""
        adj = f"${float(item.adjustment_amount):.2f}" if item.adjustment_amount else ""
        owe = f"${float(item.patient_responsibility):.2f}" if item.patient_responsibility else ""

        draw.text((cols[0], y), dos, fill="black", font=font_small)
        draw.text((cols[1], y), code, fill="black", font=font)
        draw.text((cols[2], y), desc, fill="black", font=font_small)
        draw.text((cols[3], y), units, fill="black", font=font_small)
        draw.text((cols[4], y), billed, fill="black", font=font)
        draw.text((cols[5], y), allowed, fill="black", font=font_small)
        draw.text((cols[6], y), adj, fill="black", font=font_small)
        draw.text((cols[7], y), owe, fill="black", font=font)
        y += 20

    y += 8
    line()

    # Totals
    y += 4
    totals = extraction.totals
    if totals.total_billed is not None:
        text(f"Total Charges:           ${float(totals.total_billed):.2f}", bold=True)
    if totals.total_allowed is not None:
        text(f"Insurance Allowed:       ${float(totals.total_allowed):.2f}")
    if totals.insurance_paid is not None:
        text(f"Insurance Paid:          ${float(totals.insurance_paid):.2f}")

    y += 12
    draw.rectangle([(x, y), (max_x, y + 50)], outline="black", width=2)
    amt = f"${float(totals.total_patient_responsibility or 0):.2f}"
    text("  PLEASE PAY THIS AMOUNT", bold=True)
    text(f"  {amt}", size="title", bold=True)

    # Footer
    y = PAGE_H - MARGIN - 40
    draw.text(
        (x, y),
        "If you have questions about this statement, please call our billing department.",
        fill="gray",
        font=font_small,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path))
    return output_path


def render_batch(
    extractions: list[dict[str, object]],
    output_dir: Path,
) -> list[Path]:
    """Render a batch of MedBillGen outputs as PNG images with ground truth."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for i, record in enumerate(extractions):
        ext = DocumentExtraction.model_validate(record["extraction"])
        doc_dir = output_dir / f"doc_{i:05d}"
        doc_dir.mkdir(exist_ok=True)

        img_path = doc_dir / "image.png"
        render_bill(ext, img_path, seed=42 + i)
        paths.append(img_path)

        gt_path = doc_dir / "ground_truth.json"
        gt_path.write_text(json.dumps(record["extraction"], indent=2, default=str))

        meta_path = doc_dir / "metadata.json"
        meta = {
            "index": i,
            "injected_errors": record.get("injected_errors", []),
            "metadata": record.get("metadata", {}),
        }
        meta_path.write_text(json.dumps(meta, indent=2, default=str))

    return paths
