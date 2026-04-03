"""Build the CMS SQLite database from the current hardcoded data.

This script creates a SQLite database from the Medicare rates, NCCI edits,
and MUE limits currently hardcoded in rules.py. This is the V1 approach:
embed what we have, then expand with full CMS downloads later.

Usage:
    python scripts/build_cms_data.py
    # Creates src/medbill/data/cms.db

Future: This script will download CSV files from CMS.gov and parse them.
For now, it exports the curated seed data from rules.py into SQLite so
the rule engine can use a database instead of Python dicts.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "src" / "medbill" / "data" / "cms.db"

# ---------------------------------------------------------------------------
# Data (mirrored from rules.py — single source of truth moves to DB)
# ---------------------------------------------------------------------------

MEDICARE_RATES: dict[str, tuple[str, str]] = {
    # code: (rate, short_description)
    "99211": ("25.19", "Office visit, est, minimal"),
    "99212": ("57.46", "Office visit, est, straightforward"),
    "99213": ("95.42", "Office visit, est, low"),
    "99214": ("139.81", "Office visit, est, moderate"),
    "99215": ("188.54", "Office visit, est, high"),
    "99281": ("22.98", "ED visit, level 1"),
    "99282": ("50.84", "ED visit, level 2"),
    "99283": ("81.52", "ED visit, level 3"),
    "99284": ("140.95", "ED visit, level 4"),
    "99285": ("211.43", "ED visit, level 5"),
    "85025": ("8.46", "CBC with differential"),
    "80053": ("11.22", "Comprehensive metabolic panel"),
    "80048": ("8.68", "Basic metabolic panel"),
    "71045": ("22.01", "Chest X-ray, 1 view"),
    "71046": ("28.18", "Chest X-ray, 2 views"),
    "93000": ("17.26", "EKG, 12-lead"),
    "36415": ("3.00", "Venipuncture"),
    "84443": ("17.99", "TSH"),
    "82310": ("5.73", "Calcium, blood"),
    "82565": ("5.89", "Creatinine, blood"),
    "27447": ("700.36", "Total knee replacement"),
    "73562": ("28.80", "X-ray knee, 3 views"),
    "96372": ("16.94", "Therapeutic injection"),
}

NCCI_EDITS: list[tuple[str, str, int]] = [
    # (col1_comprehensive, col2_component, modifier_indicator)
    # 0 = never allowed together, 1 = allowed with modifier -59/-XE/-XS/-XP/-XU
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


def build_database() -> None:
    """Create the CMS SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))

    # Medicare rates table
    conn.execute("""
        CREATE TABLE medicare_rates (
            hcpcs TEXT PRIMARY KEY,
            national_rate REAL NOT NULL,
            short_description TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO medicare_rates VALUES (?, ?, ?)",
        [(code, float(rate), desc) for code, (rate, desc) in MEDICARE_RATES.items()],
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
    print(f"Built {DB_PATH}")
    print(f"  Medicare rates: {rates_count}")
    print(f"  NCCI edits: {ncci_count}")
    print(f"  MUE limits: {mue_count}")
    print(f"  Size: {size_kb:.1f} KB")


if __name__ == "__main__":
    build_database()
