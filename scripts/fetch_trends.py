"""
Backfill ~20 years of Israel Google Trends data for the mental health
indicator keywords defined in keywords.py.

This is a one-time (or occasionally re-run) historical pull, not a
scheduled job: Google Trends only returns real-time-ish data for short
windows, so a 2004-to-today request comes back at ~yearly resolution.
Re-running this script later will pick up newer years too, since rows
are upserted (unique on keyword_id + period_start + batch_id) rather than
duplicated.

Deliberately paced slow (a handful of requests per minute, well under
Google's block threshold) since this is a small one-off backfill (~10
batches total) and getting the scraping IP flagged would be far more
costly than a few extra minutes of runtime.

Usage:
    python scripts/fetch_trends.py
    python scripts/fetch_trends.py --start 2004-01-01 --geo IL
"""

import argparse
import sys
import time
import uuid
from datetime import date, datetime, timezone

from pytrends.request import TrendReq

import db
from keywords import batches

DEFAULT_START = "2004-01-01"
DEFAULT_GEO = "IL"
MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 45
PAUSE_BETWEEN_BATCHES_SECONDS = 25

# Google blocks the default python-requests User-Agent outright (immediate
# 429 on the very first request, unrelated to actual rate limiting). A
# browser-like UA is required.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch_batch(pytrends: TrendReq, terms: list[str], timeframe: str, geo: str):
    """Fetch interest_over_time for one batch, retrying on rate limits."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload(terms, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
            return df
        except Exception as exc:  # pytrends raises different errors across versions
            wait = BASE_BACKOFF_SECONDS * attempt
            print(f"  fetch failed (attempt {attempt}/{MAX_RETRIES}): {exc}. "
                  f"Retrying in {wait}s...", file=sys.stderr)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(wait)


def store_observations(conn, df, keyword_ids: dict, batch_id: str):
    if df is None or df.empty:
        return 0

    df = df.drop(columns=["isPartial"], errors="ignore")
    fetched_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for period_start, row in df.iterrows():
        period_str = period_start.strftime("%Y-%m-%d")
        for term, value in row.items():
            keyword_id = keyword_ids[term]
            rows.append((keyword_id, period_str, int(value), batch_id, fetched_at))

    conn.executemany(
        """
        INSERT INTO raw_observations
            (keyword_id, period_start, value, batch_id, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (keyword_id, period_start, batch_id) DO UPDATE SET
            value = excluded.value,
            fetched_at = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START,
                         help="Backfill start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=date.today().isoformat(),
                         help="Backfill end date (YYYY-MM-DD)")
    parser.add_argument("--geo", default=DEFAULT_GEO,
                         help="Google Trends geo code (default: IL)")
    args = parser.parse_args()

    timeframe = f"{args.start} {args.end}"
    conn = db.connect()
    pytrends = TrendReq(
        hl="en-US", tz=0,
        requests_args={"headers": {"User-Agent": USER_AGENT}},
    )

    batch_list = list(batches())
    print(f"Fetching {len(batch_list)} batches for timeframe {timeframe}, geo={args.geo}")

    total_rows = 0
    for i, batch in enumerate(batch_list, start=1):
        terms = [batch["anchor"]["term"]] + [kw["term"] for kw in batch["keywords"]]
        print(f"[{i}/{len(batch_list)}] ({batch['language']}) {terms}")

        # Ensure every keyword in this batch has a row + id before storing.
        keyword_ids = {}
        for kw in batch["keywords"] + [batch["anchor"]]:
            is_anchor = kw is batch["anchor"]
            keyword_ids[kw["term"]] = db.upsert_keyword(
                conn, kw["term"], kw["language"], kw["indicator"], is_anchor
            )
        conn.commit()

        df = fetch_batch(pytrends, terms, timeframe, args.geo)
        batch_id = uuid.uuid4().hex
        n = store_observations(conn, df, keyword_ids, batch_id)
        total_rows += n
        print(f"  stored {n} observations")

        if i < len(batch_list):
            time.sleep(PAUSE_BETWEEN_BATCHES_SECONDS)

    conn.close()
    print(f"Done. {total_rows} total observations written to {db.DB_PATH}")


if __name__ == "__main__":
    main()
