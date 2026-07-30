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

  2. Default run - most recent 12 months for every keyword. Cheap, and
     lets you see (via the report file) which keywords have any IL search
     volume at all before committing to a full historical pull:
         python fetch_trends.py

  3. Full history - once you know which keywords have signal, pull the
     full ~20-year range (comes back at ~yearly resolution for a window
     this wide):
         python fetch_trends.py --full-history

Uses trendspyg (https://pypi.org/project/trendspyg/) instead of pytrends.
pytrends calls Google's internal API directly and got blocked with an
immediate 429 on almost every multi-keyword request in testing, even with
a browser User-Agent and slow pacing. trendspyg instead drives a real
headless Chrome browser to read the same chart a human would see, which
looks like genuine browser traffic rather than a scraper and reliably
avoided the block in testing. Trade-off: much slower per call (~10-30s,
it's rendering a real page) - fine for a one-off backfill, not for
anything latency-sensitive.

Every request queries exactly one keyword ALONE (self-normalized, no
anchor term). An earlier version paired each keyword with a "weather"
anchor for future rescaling, but that rounds any niche mental-health
phrase down to 0 every time (Trends normalizes to the larger term's peak,
and weather dwarfs everything). Querying alone tells us honestly whether a
term has any real search pattern at all; a properly scaled rescaling step
is a separate follow-up once we know which keywords have real signal.

Each request is stored to SQLite immediately after it's fetched (not
buffered to the end), and every run appends a timestamped log + a final
report to logs/, so a crash or a block never loses prior progress and
always leaves a record of what happened. Re-running skips keywords
already fetched for the current mode (see --force).

Still deliberately paced (one request every ~15s on top of trendspyg's own
~10-30s browser render time) - a full run is ~40 requests, so there is no
reason to hurry.
"""

import argparse
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import trendspyg

import db
from keywords import batches

DEFAULT_GEO = "IL"
FULL_HISTORY_START = "2004-01-01"
RECENT_TIMEFRAME = "today 12-m"
PAUSE_BETWEEN_REQUESTS_SECONDS = 15
TRENDSPYG_MAX_RETRIES = 5
TRENDSPYG_RETRY_WAIT = 10.0

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


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


def fetch_keyword(term: str, timeframe: str, geo: str, log: Logger):
    """
    Fetch interest_over_time for one keyword via trendspyg. trendspyg
    already retries internally past Google's soft-throttle (up to
    TRENDSPYG_MAX_RETRIES chart-load attempts), so no extra outer retry
    loop is needed here.
    """
    return trendspyg.download_google_trends_interest_over_time(
        term, geo=geo, timeframe=timeframe,
        max_retries=TRENDSPYG_MAX_RETRIES, retry_wait=TRENDSPYG_RETRY_WAIT,
    )


def store_observations(conn, series, keyword_id: int, batch_id: str, mode: str):
    """Write rows immediately (called right after each fetch, not buffered)."""
    if not series:
        return 0, 0

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    max_value = 0
    for point in series:
        period_str = point["date"][:10]  # ISO8601 -> YYYY-MM-DD
        value = int(point["value"])
        rows.append((keyword_id, period_str, value, batch_id, fetched_at, mode))
        max_value = max(max_value, value)

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
        rows,
    )
    conn.commit()
    return max_value, len(rows)


def run_test(geo: str, log: Logger):
    """Exactly one request, minimal footprint - use this on a new machine."""
    log.write(f"TEST MODE: single request, term='weather', geo={geo}, "
              f"timeframe={RECENT_TIMEFRAME}")
    try:
        series = fetch_keyword("weather", RECENT_TIMEFRAME, geo, log)
    except Exception as exc:
        log.write(f"TEST FAILED: {exc}")
        sys.exit(1)

    if not series:
        log.write("TEST RESULT: request succeeded but returned no data (unexpected for 'weather').")
    else:
        log.write(f"TEST RESULT: success. Got {len(series)} points.")
        log.write(f"  first: {series[0]}")
        log.write(f"  last:  {series[-1]}")
    log.write("Connectivity test passed - safe to run a full job.")


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
    parser.add_argument("--force", action="store_true",
                         help="Re-fetch keywords even if already stored for this mode "
                              "(default: skip keywords that already have data).")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = Logger(run_id)

    if args.test:
        run_test(args.geo, log)
        log.close()
        return

    # "solo" tags requests as single-keyword/no-anchor (current shape), distinct
    # from earlier anchor-paired pytrends runs whose stored 0s were an artifact
    # of pairing with an oversized "weather" anchor, not real absence of data.
    if args.full_history:
        timeframe = f"{args.start} {args.end}"
        mode = f"solo-full:{args.geo}:{args.start}:{args.end}"
    else:
        timeframe = RECENT_TIMEFRAME
        mode = f"solo-recent:{args.geo}"

    conn = db.connect()

    batch_list = list(batches())
    log.write(f"Fetching up to {len(batch_list)} single-keyword requests (trendspyg) "
              f"for timeframe '{timeframe}', geo={args.geo}, mode='{mode}', "
              f"paced {PAUSE_BETWEEN_REQUESTS_SECONDS}s apart"
              + (" (--force: re-fetching even if already stored)" if args.force else
                 " (already-fetched keywords for this mode will be skipped)"))

    report_rows = []  # (term, language, indicator, max_value, status)
    total_rows = 0
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 3
    for i, batch in enumerate(batch_list, start=1):
        kw = batch["keywords"][0]
        term = kw["term"]
        log.write(f"[{i}/{len(batch_list)}] ({batch['language']}) '{term}'")

        keyword_id = db.upsert_keyword(conn, term, kw["language"], kw["indicator"], False)
        conn.commit()

        # Resume support: skip keywords already fetched for this mode unless --force.
        existing = db.existing_max_value(conn, keyword_id, mode)
        if existing is not None and not args.force:
            log.write(f"  already have data for '{term}' (mode={mode}, "
                      f"max_value={existing}) - skipping, no request sent")
            has_data = "YES" if existing > 0 else "no data in geo"
            report_rows.append((term, kw["language"], kw["indicator"], existing,
                                 f"{has_data} (cached)"))
            continue

        try:
            series = fetch_keyword(term, timeframe, args.geo, log)
        except Exception as exc:
            log.write(f"  request {i} FAILED: {exc}. "
                      f"Progress so far is already saved to {db.DB_PATH}.")
            report_rows.append((term, kw["language"], kw["indicator"], None, "ERROR"))
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.write(f"  {consecutive_failures} consecutive failures - stopping the "
                          f"run rather than keep hammering Google. Re-run later to resume "
                          f"(already-fetched keywords won't be re-fetched needlessly).")
                break
            if i < len(batch_list):
                time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)
            continue

        consecutive_failures = 0
        max_value, n = store_observations(conn, series, keyword_id, uuid.uuid4().hex, mode)
        total_rows += n
        log.write(f"  stored {n} observations")

        has_data = "YES" if max_value > 0 else "no data in geo"
        report_rows.append((term, kw["language"], kw["indicator"], max_value, has_data))
        if max_value == 0:
            log.write(f"    '{term}': no search volume found for geo={args.geo}")

        if i < len(batch_list):
            time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)

    conn.close()
    log.write(f"Done. {total_rows} total observations written to {db.DB_PATH}")

    report_path = LOGS_DIR / f"fetch_{run_id}_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Fetch run {run_id}  timeframe={timeframe}  geo={args.geo}\n")
        f.write(f"{'term':40} {'lang':5} {'indicator':12} {'max_value':10} status\n")
        for term, language, indicator, max_value, status in report_rows:
            mv = "" if max_value is None else str(max_value)
            f.write(f"{term:40} {language:5} {indicator:12} {mv:10} {status}\n")
    log.write(f"Report written to {report_path}")
    log.close()


if __name__ == "__main__":
    main()
