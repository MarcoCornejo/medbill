"""CMS reference data access layer.

Loads Medicare rates, NCCI edits, and MUE limits from the bundled
SQLite database. Falls back to hardcoded defaults if DB not found.
"""

from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "cms.db"


def _get_connection() -> sqlite3.Connection | None:
    """Get a read-only connection to the CMS database."""
    if not DB_PATH.exists():
        logger.warning("CMS database not found at %s. Using hardcoded defaults.", DB_PATH)
        return None
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def get_medicare_rate(hcpcs: str) -> Decimal | None:
    """Look up the national Medicare non-facility rate for a CPT/HCPCS code."""
    conn = _get_connection()
    if conn is None:
        return _FALLBACK_RATES.get(hcpcs)
    try:
        row = conn.execute(
            "SELECT national_rate FROM medicare_rates WHERE hcpcs = ?", (hcpcs,)
        ).fetchone()
        return Decimal(str(row[0])) if row else None
    finally:
        conn.close()


def get_code_description(hcpcs: str) -> str | None:
    """Look up the CMS short description for a CPT/HCPCS code."""
    conn = _get_connection()
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT short_description FROM medicare_rates WHERE hcpcs = ?", (hcpcs,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_ncci_edit(col1: str, col2: str) -> int | None:
    """Look up NCCI edit for a code pair. Returns modifier_indicator or None."""
    conn = _get_connection()
    if conn is None:
        return _FALLBACK_NCCI.get((col1, col2))
    try:
        row = conn.execute(
            "SELECT modifier_indicator FROM ncci_edits WHERE col1 = ? AND col2 = ?",
            (col1, col2),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_all_ncci_edits() -> list[tuple[str, str, int]]:
    """Get all NCCI edit pairs for the O(n) rule engine lookup."""
    conn = _get_connection()
    if conn is None:
        return [(c1, c2, mi) for (c1, c2), mi in _FALLBACK_NCCI.items()]
    try:
        return conn.execute("SELECT col1, col2, modifier_indicator FROM ncci_edits").fetchall()
    finally:
        conn.close()


def get_mue_limit(hcpcs: str) -> int | None:
    """Look up the MUE max units per day for a CPT/HCPCS code."""
    conn = _get_connection()
    if conn is None:
        return _FALLBACK_MUE.get(hcpcs)
    try:
        row = conn.execute("SELECT max_units FROM mue_limits WHERE hcpcs = ?", (hcpcs,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# Fallback data (same as what was hardcoded in rules.py)
_FALLBACK_RATES: dict[str, Decimal] = {
    "99211": Decimal("25.19"),
    "99212": Decimal("57.46"),
    "99213": Decimal("95.42"),
    "99214": Decimal("139.81"),
    "99215": Decimal("188.54"),
    "99281": Decimal("22.98"),
    "99282": Decimal("50.84"),
    "99283": Decimal("81.52"),
    "99284": Decimal("140.95"),
    "99285": Decimal("211.43"),
    "85025": Decimal("8.46"),
    "80053": Decimal("11.22"),
    "80048": Decimal("8.68"),
    "71045": Decimal("22.01"),
    "71046": Decimal("28.18"),
    "93000": Decimal("17.26"),
    "36415": Decimal("3.00"),
    "84443": Decimal("17.99"),
    "82310": Decimal("5.73"),
    "82565": Decimal("5.89"),
    "27447": Decimal("700.36"),
}

_FALLBACK_NCCI: dict[tuple[str, str], int] = {
    ("99213", "99211"): 0,
    ("99214", "99213"): 0,
    ("99215", "99214"): 0,
    ("99215", "99213"): 0,
    ("58150", "58661"): 1,
    ("80053", "82565"): 0,
    ("80048", "82310"): 0,
    ("71046", "71045"): 0,
    ("73562", "73560"): 0,
}

_FALLBACK_MUE: dict[str, int] = {
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
