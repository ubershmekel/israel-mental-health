"""SQLite schema and connection helper for the trends database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trends.db"

SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_raw_observations_keyword
    ON raw_observations (keyword_id);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
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
