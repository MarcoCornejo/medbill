"""Build the CMS SQLite database from real CMS data files + curated seed data.

Downloads the CMS Medicare Physician Fee Schedule RVU file and builds
a SQLite database with national rates, NCCI edits, and MUE limits.

Usage:
    python scripts/build_cms_data.py              # Uses local/cached CMS file
    python scripts/build_cms_data.py --download    # Downloads fresh from CMS

The database is a build artifact (gitignored) at src/medbill/data/cms.db.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import urllib.request
import zipfile
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "src" / "medbill" / "data" / "cms.db"
CMS_RVU_URL = "https://www.cms.gov/files/zip/rvu25a.zip"
CMS_RVU_CACHE = Path(__file__).parent.parent / ".cache" / "rvu25a.zip"
CONVERSION_FACTOR = 32.3465  # CY2025 Medicare conversion factor

# ---------------------------------------------------------------------------
# NCCI edits (curated — CMS NCCI download URLs change frequently)
# ---------------------------------------------------------------------------

NCCI_EDITS: list[tuple[str, str, int]] = [
    ("99213", "99211", 0),
    ("99214", "99213", 0),
    ("99215", "99214", 0),
    ("99215", "99213", 0),
    ("58150", "58661", 1),
    ("80053", "82565", 0),
    ("80048", "82310", 0),
    ("71046", "71045", 0),
    ("73562", "73560", 0),
]

# ---------------------------------------------------------------------------
# MUE limits (curated from CMS MUE tables)
# ---------------------------------------------------------------------------

MUE_LIMITS: dict[str, int] = {
    "71045": 1,
    "71046": 1,
    "99213": 1,
    "99214": 1,
    "99215": 1,
    "99281": 1,
    "99282": 1,
    "99283": 1,
    "99284": 1,
    "99285": 1,
    "85025": 1,
    "80053": 1,
    "80048": 1,
    "36415": 1,
    "93000": 1,
    "27447": 1,
}

# ---------------------------------------------------------------------------
# Supplemental lab rates (not in MPFS — priced under CLFS)
# ---------------------------------------------------------------------------

LAB_RATES: dict[str, tuple[str, str]] = {
    "85025": ("8.46", "Complete cbc w/auto diff wbc"),
    "80053": ("11.22", "Comprehensive metabolic panel"),
    "80048": ("8.68", "Basic metabolic panel"),
    "84443": ("17.99", "Thyroid stimulating hormone"),
    "82565": ("5.89", "Creatinine blood"),
    "82310": ("5.73", "Calcium total"),
    "82947": ("4.98", "Glucose blood test"),
    "83036": ("11.78", "Hemoglobin a1c level"),
    "80061": ("13.39", "Lipid panel"),
    "81001": ("3.17", "Urinalysis nonauto w/scope"),
}


def _download_rvu_file() -> Path:
    """Download or use cached CMS RVU file."""
    if CMS_RVU_CACHE.exists():
        print(f"Using cached RVU file: {CMS_RVU_CACHE}")
        return CMS_RVU_CACHE

    CMS_RVU_CACHE.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading CMS RVU file from {CMS_RVU_URL}...")
    urllib.request.urlretrieve(CMS_RVU_URL, CMS_RVU_CACHE)
    print(f"Downloaded: {CMS_RVU_CACHE.stat().st_size / 1024 / 1024:.1f} MB")
    return CMS_RVU_CACHE


def _parse_rvu_file(zip_path: Path) -> list[tuple[str, float, str]]:
    """Parse CMS RVU ZIP and return (hcpcs, national_rate, description) tuples."""
    rates: list[tuple[str, float, str]] = []

    with zipfile.ZipFile(zip_path) as z:
        # Find the main RVU CSV (PPRRVU*.csv)
        csv_name = next(
            (n for n in z.namelist() if n.startswith("PPRRVU") and n.endswith(".csv")),
            None,
        )
        if csv_name is None:
            msg = f"No PPRRVU CSV found in {zip_path}"
            raise FileNotFoundError(msg)

        with z.open(csv_name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            lines = text.readlines()

    # Find header row (starts with "HCPCS")
    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("HCPCS")),
        None,
    )
    if header_idx is None:
        msg = "Could not find HCPCS header row"
        raise ValueError(msg)

    # Parse data rows (by position, not name — headers have duplicates)
    # Columns: 0=HCPCS, 1=MOD, 2=DESCRIPTION, 3=STATUS_CODE, ..., 11=NON-FAC_TOTAL
    seen_codes: set[str] = set()
    for row in csv.reader(lines[header_idx + 1 :]):
        if len(row) < 12 or not row[0].strip():
            continue

        hcpcs = row[0].strip()
        mod = row[1].strip()
        desc = row[2].strip()
        status = row[3].strip()
        nf_total_str = row[11].strip()

        # Skip modifier variants — use base code only
        if mod:
            continue
        # Skip if already seen (duplicates in file)
        if hcpcs in seen_codes:
            continue
        seen_codes.add(hcpcs)

        # Calculate national rate
        try:
            nf_total = float(nf_total_str) if nf_total_str else 0.0
        except ValueError:
            nf_total = 0.0

        if nf_total > 0 and status in ("A", "T", "R"):
            rate = round(nf_total * CONVERSION_FACTOR, 2)
            rates.append((hcpcs, rate, desc))

    return rates


def build_database() -> None:
    """Create the CMS SQLite database from real CMS data + curated seed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    # Download and parse CMS RVU file
    zip_path = _download_rvu_file()
    cms_rates = _parse_rvu_file(zip_path)

    conn = sqlite3.connect(str(DB_PATH))

    # Metadata table
    conn.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO metadata VALUES (?, ?)",
        ("cms_rvu_source", CMS_RVU_URL),
    )
    conn.execute(
        "INSERT INTO metadata VALUES (?, ?)",
        ("conversion_factor", str(CONVERSION_FACTOR)),
    )
    conn.execute(
        "INSERT INTO metadata VALUES (?, ?)",
        ("data_year", "2025"),
    )

    # Medicare rates table
    conn.execute("""
        CREATE TABLE medicare_rates (
            hcpcs TEXT PRIMARY KEY,
            national_rate REAL NOT NULL,
            short_description TEXT NOT NULL
        )
    """)

    # Insert CMS rates
    conn.executemany(
        "INSERT OR IGNORE INTO medicare_rates VALUES (?, ?, ?)",
        cms_rates,
    )

    # Insert supplemental lab rates (not in MPFS)
    conn.executemany(
        "INSERT OR REPLACE INTO medicare_rates VALUES (?, ?, ?)",
        [(code, float(rate), desc) for code, (rate, desc) in LAB_RATES.items()],
    )

    # NCCI edits table
    conn.execute("""
        CREATE TABLE ncci_edits (
            col1 TEXT NOT NULL,
            col2 TEXT NOT NULL,
            modifier_indicator INTEGER NOT NULL,
            PRIMARY KEY (col1, col2)
        )
    """)
    conn.executemany(
        "INSERT INTO ncci_edits VALUES (?, ?, ?)",
        NCCI_EDITS,
    )

    # MUE limits table
    conn.execute("""
        CREATE TABLE mue_limits (
            hcpcs TEXT PRIMARY KEY,
            max_units INTEGER NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO mue_limits VALUES (?, ?)",
        MUE_LIMITS.items(),
    )

    # Indexes
    conn.execute("CREATE INDEX idx_ncci_col1 ON ncci_edits(col1)")
    conn.execute("CREATE INDEX idx_ncci_col2 ON ncci_edits(col2)")

    conn.commit()

    # Stats
    rates_count = conn.execute("SELECT COUNT(*) FROM medicare_rates").fetchone()[0]
    ncci_count = conn.execute("SELECT COUNT(*) FROM ncci_edits").fetchone()[0]
    mue_count = conn.execute("SELECT COUNT(*) FROM mue_limits").fetchone()[0]
    conn.close()

    size_kb = DB_PATH.stat().st_size / 1024
    print(f"\nBuilt {DB_PATH}")
    print(f"  Medicare rates: {rates_count}")
    print(f"  NCCI edits: {ncci_count}")
    print(f"  MUE limits: {mue_count}")
    print(f"  Size: {size_kb:.0f} KB")


if __name__ == "__main__":
    build_database()
