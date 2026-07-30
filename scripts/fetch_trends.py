"""
Pull Israel Google Trends data for the mental health indicator keywords
defined in keywords.py.

Many of these keywords will likely come back with **zero search volume**
when restricted to geo=IL (small country, niche phrasing) - that's an
expected, useful result, not a bug. Every run writes a per-keyword report
so you can see which terms actually have signal before spending a full
historical pull on them.

Three ways to run this:

  1. Connectivity test (always do this first, especially on a new
     machine/network) - exactly ONE request, most recent 12 months only:
         python fetch_trends.py --test

  2. Default run - most recent 12 months for every batch. Cheap, and lets
     you see (via the report file) which keywords have any IL search
     volume at all before committing to a full historical pull:
         python fetch_trends.py

  3. Full history - once you know which keywords have signal, pull the
     full ~20-year range (comes back at ~yearly resolution for a window
     this wide):
         python fetch_trends.py --full-history

Every batch is stored to SQLite immediately after it's fetched (not
buffered to the end), and every run appends a timestamped log + a final
report to logs/, so a crash or a rate-limit block never loses prior
progress and always leaves a record of what happened.

Deliberately paced slow (one request every ~25s, well under Google's
block threshold) - this is a small one-off job (~10 batches for a full
run), so there is no reason to hurry and real risk in going fast.
"""

import argparse
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from pytrends.request import TrendReq

import db
from keywords import batches

DEFAULT_GEO = "IL"
FULL_HISTORY_START = "2004-01-01"
RECENT_TIMEFRAME = "today 12-m"
MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 45
PAUSE_BETWEEN_BATCHES_SECONDS = 25

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

# Google blocks the default python-requests User-Agent outright (immediate
# 429 on the very first request, unrelated to actual rate limiting). A
# browser-like UA is required.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class Logger:
    """Writes every message to both stdout and a timestamped log file."""

    def __init__(self, run_id: str):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOGS_DIR / f"fetch_{run_id}.log"
        self._fh = open(self.log_path, "a", encoding="utf-8")

    def write(self, msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        self._fh.write(line + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


def make_pytrends() -> TrendReq:
    return TrendReq(
        hl="en-US", tz=0,
        requests_args={"headers": {"User-Agent": USER_AGENT}},
    )


def fetch_batch(pytrends: TrendReq, terms: list[str], timeframe: str, geo: str, log: Logger):
    """Fetch interest_over_time for one batch, retrying on rate limits."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload(terms, timeframe=timeframe, geo=geo)
            return pytrends.interest_over_time()
        except Exception as exc:  # pytrends raises different errors across versions
            wait = BASE_BACKOFF_SECONDS * attempt
            log.write(f"  fetch failed (attempt {attempt}/{MAX_RETRIES}): {exc}. "
                      f"Retrying in {wait}s...")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(wait)


def store_observations(conn, df, keyword_ids: dict, batch_id: str):
    """Write rows immediately (called right after each fetch, not buffered)."""
    if df is None or df.empty:
        return {}, 0

    df = df.drop(columns=["isPartial"], errors="ignore")
    fetched_at = datetime.now(timezone.utc).isoformat()

    rows = []
    max_value_by_term = {term: 0 for term in df.columns}
    for period_start, row in df.iterrows():
        period_str = period_start.strftime("%Y-%m-%d")
        for term, value in row.items():
            value = int(value)
            keyword_id = keyword_ids[term]
            rows.append((keyword_id, period_str, value, batch_id, fetched_at))
            max_value_by_term[term] = max(max_value_by_term[term], value)

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
    return max_value_by_term, len(rows)


def run_test(geo: str, log: Logger):
    """Exactly one request, minimal footprint - use this on a new machine."""
    log.write(f"TEST MODE: single request, geo={geo}, timeframe={RECENT_TIMEFRAME}")
    pytrends = make_pytrends()
    term = "weather"
    try:
        df = fetch_batch(pytrends, [term], RECENT_TIMEFRAME, geo, log)
    except Exception as exc:
        log.write(f"TEST FAILED: {exc}")
        sys.exit(1)

    if df is None or df.empty:
        log.write("TEST RESULT: request succeeded but returned no data (unexpected for 'weather').")
    else:
        log.write(f"TEST RESULT: success. Got {len(df)} rows for '{term}'.")
        log.write(df.to_string())
    log.write("Connectivity test passed - safe to run a full batch job.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--test", action="store_true",
                         help="Run exactly one request to verify connectivity, then exit.")
    parser.add_argument("--full-history", action="store_true",
                         help=f"Pull the full {FULL_HISTORY_START}-to-today range instead of "
                              "just the most recent 12 months.")
    parser.add_argument("--start", default=FULL_HISTORY_START,
                         help="Backfill start date (YYYY-MM-DD), only used with --full-history")
    parser.add_argument("--end", default=date.today().isoformat(),
                         help="Backfill end date (YYYY-MM-DD), only used with --full-history")
    parser.add_argument("--geo", default=DEFAULT_GEO,
                         help="Google Trends geo code (default: IL)")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = Logger(run_id)

    if args.test:
        run_test(args.geo, log)
        log.close()
        return

    timeframe = f"{args.start} {args.end}" if args.full_history else RECENT_TIMEFRAME
    conn = db.connect()
    pytrends = make_pytrends()

    batch_list = list(batches())
    log.write(f"Fetching {len(batch_list)} batches for timeframe '{timeframe}', geo={args.geo}")

    report_rows = []  # (term, language, indicator, max_value, has_data)
    total_rows = 0
    for i, batch in enumerate(batch_list, start=1):
        terms = [batch["anchor"]["term"]] + [kw["term"] for kw in batch["keywords"]]
        log.write(f"[{i}/{len(batch_list)}] ({batch['language']}) {terms}")

        keyword_meta = {kw["term"]: kw for kw in batch["keywords"] + [batch["anchor"]]}
        keyword_ids = {}
        for term, kw in keyword_meta.items():
            is_anchor = kw is batch["anchor"]
            keyword_ids[term] = db.upsert_keyword(
                conn, kw["term"], kw["language"], kw["indicator"], is_anchor
            )
        conn.commit()

        try:
            df = fetch_batch(pytrends, terms, timeframe, args.geo, log)
        except Exception as exc:
            log.write(f"  batch {i} FAILED after all retries: {exc}. "
                      f"Progress so far is already saved to {db.DB_PATH}.")
            for term in terms:
                kw = keyword_meta[term]
                report_rows.append((term, kw["language"], kw["indicator"], None, "ERROR"))
            break  # stop the whole run rather than keep hammering Google

        max_value_by_term, n = store_observations(conn, df, keyword_ids, uuid.uuid4().hex)
        total_rows += n
        log.write(f"  stored {n} observations")

        for term in terms:
            kw = keyword_meta[term]
            max_value = max_value_by_term.get(term, 0)
            has_data = "YES" if max_value > 0 else "no data in geo"
            report_rows.append((term, kw["language"], kw["indicator"], max_value, has_data))
            if max_value == 0:
                log.write(f"    '{term}': no search volume found for geo={args.geo}")

        if i < len(batch_list):
            time.sleep(PAUSE_BETWEEN_BATCHES_SECONDS)

    conn.close()
    log.write(f"Done. {total_rows} total observations written to {db.DB_PATH}")

    report_path = LOGS_DIR / f"fetch_{run_id}_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Fetch run {run_id}  timeframe={timeframe}  geo={args.geo}\n")
        f.write(f"{'term':40} {'lang':5} {'indicator':12} {'max_value':10} status\n")
        for term, language, indicator, max_value, has_data in report_rows:
            mv = "" if max_value is None else str(max_value)
            f.write(f"{term:40} {language:5} {indicator:12} {mv:10} {has_data}\n")
    log.write(f"Report written to {report_path}")
    log.close()


if __name__ == "__main__":
    main()
