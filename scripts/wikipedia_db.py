"""SQLite storage for raw Wikipedia Pageviews observations."""

import sqlite3
from pathlib import Path

DB_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "wikipedia_pageviews.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS wikipedia_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    article TEXT NOT NULL,
    language TEXT NOT NULL,
    indicator TEXT NOT NULL,
    label_en TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE (project, article)
);

CREATE TABLE IF NOT EXISTS wikipedia_pageviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES wikipedia_pages (id),
    period_start TEXT NOT NULL,
    granularity TEXT NOT NULL,
    views INTEGER NOT NULL CHECK (views >= 0),
    access TEXT NOT NULL,
    agent TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE (page_id, period_start, granularity, access, agent)
);

CREATE INDEX IF NOT EXISTS idx_wikipedia_pageviews_page_period
    ON wikipedia_pageviews (page_id, period_start);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_page(
    conn: sqlite3.Connection,
    *,
    project: str,
    article: str,
    language: str,
    indicator: str,
    label_en: str,
) -> int:
    conn.execute(
        """
        INSERT INTO wikipedia_pages
            (project, article, language, indicator, label_en)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (project, article) DO UPDATE SET
            language = excluded.language,
            indicator = excluded.indicator,
            label_en = excluded.label_en,
            active = 1
        """,
        (project, article, language, indicator, label_en),
    )
    row = conn.execute(
        """
        SELECT id FROM wikipedia_pages
        WHERE project = ? AND article = ?
        """,
        (project, article),
    ).fetchone()
    return row[0]
