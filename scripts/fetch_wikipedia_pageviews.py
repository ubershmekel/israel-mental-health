"""
Fetch daily views of selected Hebrew Wikipedia mental-health articles.

The Wikimedia Analytics API is official, free, and requires no API key.
It has per-article data from 2015-07-01 onward. Results are absolute daily
view counts, so they are stored separately from normalized Google Trends
scores in data/wikipedia_pageviews.db.

Examples:

    # One request for one article and no database writes
    python fetch_wikipedia_pageviews.py --test

    # Previous 365 complete days for all configured articles
    python fetch_wikipedia_pageviews.py

    # Complete available history (2015-07-01 through yesterday)
    python fetch_wikipedia_pageviews.py --full-history

    # An explicit inclusive range
    python fetch_wikipedia_pageviews.py --start 2023-01-01 --end 2023-12-31

The API reports all readers of Hebrew Wikipedia. It cannot limit an
individual article's views to readers physically located in Israel.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import wikipedia_db
from wikipedia_pages import PAGES

API_ROOT = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
PROJECT = "he.wikipedia"
ACCESS = "all-access"
# Excludes self-declared spiders and traffic classified as automated.
AGENT = "user"
GRANULARITY = "daily"
EARLIEST_DATE = date(2015, 7, 1)
RECENT_DAYS = 365
CHUNK_DAYS = 365
MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 2
PAUSE_SECONDS = 0.2
REQUEST_TIMEOUT_SECONDS = 30

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
DEFAULT_USER_AGENT = (
    "IsraelMentalHealthIndex/0.1 "
    "(public-interest research; contact via project repository)"
)


class Logger:
    """Write messages to stdout and a UTF-8 run log."""

    def __init__(self, run_id: str):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOGS_DIR / f"wikipedia_{run_id}.log"
        self._fh = open(self.log_path, "a", encoding="utf-8")

    def write(self, message: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
        print(line)
        self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date '{value}'; expected YYYY-MM-DD"
        ) from exc


def date_chunks(start: date, end: date):
    """Yield inclusive chunks that stay within the API's practical range."""
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS - 1), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def pageviews_url(article: str, start: date, end: date) -> str:
    encoded_article = quote(article.replace(" ", "_"), safe="")
    return (
        f"{API_ROOT}/{PROJECT}/{ACCESS}/{AGENT}/{encoded_article}/"
        f"{GRANULARITY}/{start:%Y%m%d}/{end:%Y%m%d}"
    )


def retry_after_seconds(exc: HTTPError, attempt: int) -> float:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header:
        try:
            return max(float(header), 0)
        except ValueError:
            pass
    return BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))


def fetch_pageviews(
    article: str,
    start: date,
    end: date,
    user_agent: str,
    log: Logger,
) -> list[dict]:
    """Fetch and validate one article/chunk response, with bounded retries."""
    url = pageviews_url(article, start, end)
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": user_agent},
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("API response has no 'items' list")
            return items
        except HTTPError as exc:
            # AQS returns 404 when a valid article has no series for the
            # requested historical window (for example, before a title was
            # created). Preserve that as missing data rather than inventing
            # zero-view observations.
            if exc.code == 404:
                log.write(
                    f"  no pageview series for '{article}' in "
                    f"{start}..{end}; storing no observations"
                )
                return []
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt == MAX_RETRIES:
                raise
            wait = retry_after_seconds(exc, attempt)
            log.write(
                f"  HTTP {exc.code} (attempt {attempt}/{MAX_RETRIES}); "
                f"retrying in {wait:g}s"
            )
            time.sleep(wait)
        except (URLError, TimeoutError) as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            log.write(
                f"  request failed (attempt {attempt}/{MAX_RETRIES}): "
                f"{exc}; retrying in {wait}s"
            )
            time.sleep(wait)

    raise RuntimeError("unreachable")


def store_pageviews(
    conn,
    page_id: int,
    items: list[dict],
    fetched_at: str,
) -> int:
    rows = []
    for item in items:
        timestamp = str(item["timestamp"])
        if len(timestamp) < 8:
            raise ValueError(f"invalid API timestamp: {timestamp!r}")
        period_start = datetime.strptime(timestamp[:8], "%Y%m%d").date().isoformat()
        rows.append(
            (
                page_id,
                period_start,
                item.get("granularity", GRANULARITY),
                int(item["views"]),
                item.get("access", ACCESS),
                item.get("agent", AGENT),
                fetched_at,
            )
        )

    conn.executemany(
        """
        INSERT INTO wikipedia_pageviews
            (page_id, period_start, granularity, views, access, agent, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (page_id, period_start, granularity, access, agent)
        DO UPDATE SET
            views = excluded.views,
            fetched_at = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def resolve_range(args, yesterday: date) -> tuple[date, date]:
    if args.full_history and (args.start or args.end):
        raise ValueError("--full-history cannot be combined with --start or --end")
    if bool(args.start) != bool(args.end):
        raise ValueError("--start and --end must be supplied together")

    if args.full_history:
        start, end = EARLIEST_DATE, yesterday
    elif args.start:
        start, end = args.start, args.end
    else:
        end = yesterday
        start = max(EARLIEST_DATE, end - timedelta(days=RECENT_DAYS - 1))

    if start < EARLIEST_DATE:
        raise ValueError(
            f"Pageviews data begins on {EARLIEST_DATE}; got start={start}"
        )
    if end > yesterday:
        raise ValueError(
            f"end must be a complete day ({yesterday} or earlier); got {end}"
        )
    if start > end:
        raise ValueError(f"start ({start}) must not be after end ({end})")
    return start, end


def run_test(user_agent: str, log: Logger, yesterday: date) -> None:
    page = PAGES[0]
    start = max(EARLIEST_DATE, yesterday - timedelta(days=6))
    log.write(
        f"TEST MODE: one request, article='{page['article']}', "
        f"range={start}..{yesterday}; no database writes"
    )
    items = fetch_pageviews(page["article"], start, yesterday, user_agent, log)
    total = sum(int(item["views"]) for item in items)
    log.write(f"TEST PASSED: received {len(items)} daily rows, {total} total views")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Make one seven-day request without writing to the database.",
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help=f"Fetch all data since {EARLIEST_DATE}.",
    )
    parser.add_argument("--start", type=parse_date, help="Inclusive start (YYYY-MM-DD).")
    parser.add_argument("--end", type=parse_date, help="Inclusive end (YYYY-MM-DD).")
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("WIKIMEDIA_USER_AGENT", DEFAULT_USER_AGENT),
        help="Descriptive Wikimedia User-Agent (or set WIKIMEDIA_USER_AGENT).",
    )
    args = parser.parse_args()

    yesterday = date.today() - timedelta(days=1)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = Logger(run_id)
    try:
        if args.test:
            run_test(args.user_agent, log, yesterday)
            return 0

        try:
            start, end = resolve_range(args, yesterday)
        except ValueError as exc:
            parser.error(str(exc))

        conn = wikipedia_db.connect()
        total_rows = 0
        try:
            chunks = list(date_chunks(start, end))
            log.write(
                f"Fetching {len(PAGES)} articles for {start}..{end} "
                f"in {len(chunks)} chunk(s) each; project={PROJECT}, "
                f"access={ACCESS}, agent={AGENT}"
            )
            for page_index, page in enumerate(PAGES, start=1):
                page_id = wikipedia_db.upsert_page(
                    conn, project=PROJECT, **page
                )
                conn.commit()
                article_rows = 0
                log.write(
                    f"[{page_index}/{len(PAGES)}] {page['article']} "
                    f"({page['label_en']})"
                )
                for chunk_index, (chunk_start, chunk_end) in enumerate(
                    chunks, start=1
                ):
                    log.write(
                        f"  chunk {chunk_index}/{len(chunks)}: "
                        f"{chunk_start}..{chunk_end}"
                    )
                    items = fetch_pageviews(
                        page["article"],
                        chunk_start,
                        chunk_end,
                        args.user_agent,
                        log,
                    )
                    count = store_pageviews(
                        conn,
                        page_id,
                        items,
                        datetime.now(timezone.utc).isoformat(),
                    )
                    article_rows += count
                    total_rows += count
                    log.write(f"    upserted {count} daily observations")
                    if chunk_index < len(chunks):
                        time.sleep(PAUSE_SECONDS)
                log.write(f"  article complete: {article_rows} observations")
                if page_index < len(PAGES):
                    time.sleep(PAUSE_SECONDS)
        finally:
            conn.close()

        log.write(
            f"Done. Upserted {total_rows} observations into "
            f"{wikipedia_db.DB_PATH}"
        )
        return 0
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
        log.write(f"FAILED: {exc}")
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
