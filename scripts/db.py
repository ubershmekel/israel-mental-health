"""SQLite schema and connection helper for the trends database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trends.db"

TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL,
    language TEXT NOT NULL,
    indicator TEXT NOT NULL,
    is_anchor INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE (term, language)
);

CREATE TABLE IF NOT EXISTS raw_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords (id),
    period_start TEXT NOT NULL,
    value INTEGER NOT NULL,
    batch_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE (keyword_id, period_start, batch_id)
);
"""

INDEXES_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_raw_observations_keyword
    ON raw_observations (keyword_id);

CREATE INDEX IF NOT EXISTS idx_raw_observations_keyword_mode
    ON raw_observations (keyword_id, mode);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(TABLES_SCHEMA)

    # Migration: older DBs may predate the `mode` column. Must run before
    # creating indexes that reference it.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(raw_observations)")}
    if "mode" not in cols:
        conn.execute("ALTER TABLE raw_observations ADD COLUMN mode TEXT NOT NULL DEFAULT ''")
        conn.commit()

    conn.executescript(INDEXES_SCHEMA)
    return conn


def upsert_keyword(conn: sqlite3.Connection, term: str, language: str,
                    indicator: str, is_anchor: bool) -> int:
    conn.execute(
        """
        INSERT INTO keywords (term, language, indicator, is_anchor)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (term, language) DO UPDATE SET
            indicator = excluded.indicator,
            is_anchor = excluded.is_anchor
        """,
        (term, language, indicator, int(is_anchor)),
    )
    row = conn.execute(
        "SELECT id FROM keywords WHERE term = ? AND language = ?",
        (term, language),
    ).fetchone()
    return row[0]


def existing_max_value(conn: sqlite3.Connection, keyword_id: int, mode: str):
    """Highest stored value for this keyword+mode, or None if never fetched."""
    row = conn.execute(
        "SELECT MAX(value) FROM raw_observations WHERE keyword_id = ? AND mode = ?",
        (keyword_id, mode),
    ).fetchone()
    return row[0]  # None if no rows exist for this keyword+mode
