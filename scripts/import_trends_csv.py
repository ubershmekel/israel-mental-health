"""
Import a Google Trends "Download CSV" export into data/trends.db.

Automated scraping (pytrends, then trendspyg) turned out to be more
trouble than it's worth: aggressive/erratic blocking and a flaky
post-render "replay" step that no amount of retry tuning made reliable.
Manually browsing https://trends.google.com/trends/explore and clicking
"Download CSV" on the Interest over time chart is simpler and gives the
exact same numbers, just without the automation headache.

Usage:
    python import_trends_csv.py <csv_file> --language he --indicator crisis

The keyword's term is read from the CSV's own header, so you don't need
to retype it. --language and --indicator classify it for our schema.

Two CSV header shapes have been seen in practice, both handled here:
    "Time","<term>"                 - no geo in the header; geo comes from
                                       --geo (default IL) or the filename
                                       (Google names files like
                                       time_series_IL_<range>.csv)
    Day/Week/Month,"<term>: (Geo)"  - geo embedded in the column header
Resolution (daily/weekly/monthly) is inferred from the actual gap between
the first two data rows, not trusted from the header label alone.
"""

import argparse
import csv
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import db

# Windows consoles often default to cp1252, which can't encode Hebrew terms.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADER_WITH_GEO_RE = re.compile(r"^(.*?):\s*\(([^)]+)\)\s*$")
FILENAME_GEO_RE = re.compile(r"time_series_([A-Za-z-]+)_", re.IGNORECASE)


def parse_period(date_str: str) -> str:
    """Normalize a CSV date value (YYYY-MM-DD or YYYY-MM) to a period_start."""
    date_str = date_str.strip()
    if re.fullmatch(r"\d{4}-\d{2}", date_str):
        return datetime.strptime(date_str, "%Y-%m").date().isoformat()
    return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()


def infer_resolution(first_period: str, second_period: str) -> str:
    delta_days = (datetime.fromisoformat(second_period) - datetime.fromisoformat(first_period)).days
    if delta_days >= 27:
        return "monthly"
    if delta_days >= 6:
        return "weekly"
    return "daily"


def parse_value(value_str: str):
    """Google shows '<1' for nonzero-but-sub-1% interest; treat as 0."""
    value_str = value_str.strip()
    if not value_str:
        return None
    try:
        return int(value_str)
    except ValueError:
        if value_str.startswith("<"):
            return 0
        return None


def find_header_row(lines: list[str]) -> int:
    """
    Google's export is either just the header on line 1 ("Time",<term>), or
    has a few preamble lines (Category:, blank, term) before a Day/Week/Month
    header. Accept either.
    """
    for i, line in enumerate(lines):
        first_cell = line.split(",", 1)[0].strip().strip('"')
        if first_cell in ("Day", "Week", "Month", "Time"):
            return i
    raise ValueError(
        "Could not find a Time/Day/Week/Month header row - is this a Google "
        "Trends 'Interest over time' CSV export?"
    )


def geo_from_filename(path: Path):
    match = FILENAME_GEO_RE.search(path.name)
    return match.group(1).upper() if match else None


def parse_csv(path: Path, geo_override: str | None):
    text = path.read_text(encoding="utf-8-sig")
    lines = [l for l in text.splitlines() if l.strip()]
    header_idx = find_header_row(lines)
    header_line = lines[header_idx]

    reader = csv.reader(io.StringIO(header_line))
    _date_col, term_col = next(reader)
    term_col = term_col.strip()

    match = HEADER_WITH_GEO_RE.match(term_col)
    if match:
        term, geo = match.group(1).strip(), match.group(2).strip()
    else:
        term = term_col
        geo = geo_override or geo_from_filename(path) or "unknown"

    rows = []
    skipped = 0
    for line in lines[header_idx + 1:]:
        parts = next(csv.reader(io.StringIO(line)))
        if len(parts) < 2:
            continue
        value = parse_value(parts[1])
        if value is None:
            skipped += 1
            continue
        rows.append((parse_period(parts[0]), value))

    rows.sort(key=lambda r: r[0])
    return term, geo, rows, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file", type=Path, help="Path to the downloaded Google Trends CSV")
    parser.add_argument("--language", required=True, choices=["he", "en"])
    parser.add_argument("--indicator", required=True,
                         choices=["autonomy", "competence", "relatedness", "crisis"])
    parser.add_argument("--geo", default=None,
                         help="Override geo (default: read from filename, else 'unknown')")
    parser.add_argument("--mode-label", default=None,
                         help="Override the auto-generated mode tag (rarely needed)")
    args = parser.parse_args()

    if not args.csv_file.exists():
        print(f"File not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    term, geo, rows, skipped = parse_csv(args.csv_file, args.geo)
    if not rows:
        print(f"No usable rows parsed from {args.csv_file} (term={term!r})", file=sys.stderr)
        sys.exit(1)

    resolution = infer_resolution(rows[0][0], rows[1][0]) if len(rows) > 1 else "unknown"
    span = f"{rows[0][0]}:{rows[-1][0]}"
    mode = args.mode_label or f"csv-{resolution}:{geo}:{span}"

    conn = db.connect()
    keyword_id = db.upsert_keyword(conn, term, args.language, args.indicator, False)
    conn.commit()

    fetched_at = datetime.now(timezone.utc).isoformat()
    # Deterministic (not random) so re-importing the same term+mode updates
    # the existing rows in place instead of inserting duplicates - the
    # uniqueness constraint is (keyword_id, period_start, batch_id), so a
    # fresh random id every run would otherwise duplicate every point.
    batch_id = f"csv-import:{keyword_id}:{mode}"
    conn.executemany(
        """
        INSERT INTO raw_observations
            (keyword_id, period_start, value, batch_id, fetched_at, mode)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (keyword_id, period_start, batch_id) DO UPDATE SET
            value = excluded.value,
            fetched_at = excluded.fetched_at,
            mode = excluded.mode
        """,
        [(keyword_id, period, value, batch_id, fetched_at, mode) for period, value in rows],
    )
    conn.commit()
    conn.close()

    max_value = max(v for _, v in rows)
    nonzero = sum(1 for _, v in rows if v > 0)
    print(f"Imported {len(rows)} {resolution} points for '{term}' ({args.language}, "
          f"{args.indicator}), geo={geo}, mode='{mode}'. "
          f"Max value: {max_value}, nonzero points: {nonzero}/{len(rows)}."
          + (f" Skipped {skipped} unparseable row(s)." if skipped else ""))


if __name__ == "__main__":
    main()
