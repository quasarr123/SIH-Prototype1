"""
database/db.py
---------------
Thin data-access layer around SQLite.

Why SQLite for the POC: zero setup, single file, good enough for
tens of thousands of fare rows. The functions below are written so
that swapping to PostgreSQL later only means changing the connection
function (`get_connection`) — every caller just uses plain SQL /
pandas, no SQLite-specific syntax is used elsewhere in the project.
"""

import sqlite3
from pathlib import Path
from typing import Iterable, Dict, Any

import pandas as pd

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DB_PATH  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Open (and create, if needed) the SQLite database file."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn


def init_db() -> None:
    """Create the fares table if it doesn't already exist."""
    conn = get_connection()
    try:
        with open(SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


def insert_fares(records: Iterable[Dict[str, Any]]) -> int:
    """
    Bulk-insert fare records.

    Each record is a dict with keys:
        source, airline, origin, destination,
        travel_date, search_datetime, fare_price

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
                 travel_date, search_datetime, fare_price)
            VALUES
                (:source, :airline, :origin, :destination,
                 :travel_date, :search_datetime, :fare_price)
            """,
            records,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


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
    """Wipe the table — used when regenerating mock data from scratch."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM fares")
        conn.commit()
    finally:
        conn.close()
