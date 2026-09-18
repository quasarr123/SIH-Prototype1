"""
database/db.py
---------------
Thin data-access layer around SQLite.

Why SQLite for the POC: zero setup, single file, good enough for
tens of thousands of fare rows. The functions below are written so
that swapping to PostgreSQL later only means changing the connection
function (`get_connection`) — every caller just uses plain SQL /
pandas, no SQLite-specific syntax is used elsewhere in the project.

Phase 4 additions: `init_db()` now migrates existing databases so the
audit-trail columns (lead_time_days, booking_class, fare_type,
scrape_id, raw_fare_value, source_url, validation_status, flag_reason)
are added to an already-created `fares` table, plus a `scrape_runs`
audit table. `save_validation_results()` writes the cleaning module's
per-row validation verdict back to the DB, which is what makes every
stored fare traceable to "did it pass quality checks".
"""

import sqlite3
from pathlib import Path
from typing import Iterable, Dict, Any

import pandas as pd

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DB_PATH  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Columns (beyond the original seven) that may need to be added to an
# existing `fares` table when the POC was previously run with the
# pre-audit schema. Order matters only for readability.
_FARE_ADDITIONAL_COLUMNS = [
    ("lead_time_days", "INTEGER"),
    ("booking_class", "TEXT DEFAULT 'economy'"),
    ("fare_type", "TEXT DEFAULT 'non_refundable'"),
    ("scrape_id", "TEXT"),
    ("raw_fare_value", "TEXT"),
    ("source_url", "TEXT"),
    ("validation_status", "TEXT DEFAULT 'pending'"),
    ("flag_reason", "TEXT"),
]


def get_connection() -> sqlite3.Connection:
    """Open (and create, if needed) the SQLite database file."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn


def _existing_fare_columns(conn: sqlite3.Connection) -> set:
    rows = conn.execute("PRAGMA table_info(fares)").fetchall()
    return {row[1] for row in rows}


def _migrate(conn: sqlite3.Connection) -> None:
    """
    Add the Phase-4 audit columns to a `fares` table created by an older
    version of the schema (before the columns existed). Safe to call on a
    fresh database too — each ADD COLUMN is guarded by a PRAGMA check.
    """
    existing = _existing_fare_columns(conn)
    for name, ddl in _FARE_ADDITIONAL_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE fares ADD COLUMN {name} {ddl}")


def init_db() -> None:
    """
    Create the fares/scrape_runs tables if they don't exist, and MIGRATE
    an older `fares` table by adding the Phase-4 audit columns.

    Ordering matters: an existing pre-audit table lacks e.g. `scrape_id`,
    so running the full schema (which builds an index on it) fails. In
    that case we ALTER-add the missing columns first, then re-apply the
    idempotent DDL.
    """
    conn = get_connection()
    try:
        with open(SCHEMA_PATH, "r") as f:
            ddl = f.read()
        try:
            conn.executescript(ddl)
        except sqlite3.OperationalError:
            # Pre-existing database from before the audit-trail schema:
            # migrate the columns, then re-apply the DDL (CREATE TABLE IF
            # NOT EXISTS / CREATE INDEX IF NOT EXISTS are both idempotent).
            _migrate(conn)
            conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()


def insert_fares(records: Iterable[Dict[str, Any]]) -> int:
    """
    Bulk-insert fare records.

    Each record is a dict with keys:
        source, airline, origin, destination, travel_date,
        search_datetime, fare_price
    and the Phase-3/4 audit fields (all optional):
        lead_time_days, booking_class, fare_type,
        scrape_id, raw_fare_value, source_url

    Returns the number of rows inserted.
    """
    records = list(records)
    if not records:
        return 0

    conn = get_connection()
    try:
        cur = conn.executemany(
            """
            INSERT INTO fares
                (source, airline, origin, destination,
                 travel_date, search_datetime, fare_price,
                 lead_time_days, booking_class, fare_type,
                 scrape_id, raw_fare_value, source_url)
            VALUES
                (:source, :airline, :origin, :destination,
                 :travel_date, :search_datetime, :fare_price,
                 :lead_time_days, :booking_class, :fare_type,
                 :scrape_id, :raw_fare_value, :source_url)
            """,
            records,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def save_validation_results(df: pd.DataFrame) -> int:
    """
    Write the cleaning module's validation verdict back to the database
    (Phase 4 audit trail): sets validation_status and flag_reason per
    row by `id`. Rows without an `id` column are skipped.
    Returns the number of rows updated.
    """
    if df is None or df.empty or "id" not in df.columns:
        return 0

    rows = [
        (
            row["validation_status"],
            row.get("flag_reason") or "",
            row["id"],
        )
        for _, row in df.iterrows()
    ]
    if not rows:
        return 0

    conn = get_connection()
    try:
        cur = conn.executemany(
            "UPDATE fares SET validation_status = ?, flag_reason = ? WHERE id = ?",
            rows,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def log_scrape_run(
    scrape_id: str,
    source: str,
    origin: str | None = None,
    destination: str | None = None,
    travel_date: str | None = None,
    status: str = "completed",
    records_expected: int = 0,
    records_found: int = 0,
    notes: str = "",
) -> int:
    """Record one collection run in the audit table. Returns new row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO scrape_runs
                (scrape_id, source, origin, destination, travel_date,
                 status, records_expected, records_found, notes)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scrape_id, source, origin, destination, travel_date,
                status, records_expected, records_found, notes,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def fetch_scrape_runs(limit: int = 50) -> pd.DataFrame:
    """Return recent collection-run audit rows (latest first)."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM scrape_runs ORDER BY id DESC LIMIT ?", conn,
            params=(limit,),
        )
    finally:
        conn.close()
    return df


def fetch_all_fares() -> pd.DataFrame:
    """Return every fare row as a pandas DataFrame."""
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM fares", conn)
    finally:
        conn.close()

    if not df.empty:
        df["travel_date"] = pd.to_datetime(df["travel_date"])
        df["search_datetime"] = pd.to_datetime(df["search_datetime"])
    return df


def row_count() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM fares").fetchone()[0]
    finally:
        conn.close()


def clear_all_fares() -> None:
    """Wipe the fares + run-audit tables — used when regenerating from scratch."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM fares")
        conn.execute("DELETE FROM scrape_runs")
        conn.commit()
    finally:
        conn.close()