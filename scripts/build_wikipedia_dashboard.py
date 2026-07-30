"""Build a standalone HTML view of the Wikipedia Pageviews database."""

import calendar
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "wikipedia_pageviews.db"
TEMPLATE_PATH = ROOT / "scripts" / "wikipedia_dashboard.template.html"
FRAGMENT_PATH = (
    ROOT
    / ".codex"
    / "visualizations"
    / date.today().strftime("%Y/%m/%d")
    / "wikipedia-pageviews.html"
)
OUTPUT_PATH = ROOT / "reports" / "wikipedia-pageviews.html"
RENDER_SCRIPT = (
    Path.home()
    / ".codex"
    / "plugins"
    / "cache"
    / "openai-bundled"
    / "visualize"
    / "1.0.12"
    / "skills"
    / "visualize"
    / "scripts"
    / "render.py"
)


def month_sequence(start: str, end: str):
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    while (year, month) <= (end_year, end_month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year += 1
            month = 1


def load_data() -> dict:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} does not exist; run fetch_wikipedia_pageviews.py first"
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        bounds = conn.execute(
            """
            SELECT MIN(period_start) AS first_day, MAX(period_start) AS last_day
            FROM wikipedia_pageviews
            """
        ).fetchone()
        if not bounds["first_day"]:
            raise ValueError("Wikipedia Pageviews database contains no observations")

        # Exclude the current/incomplete calendar month from comparisons.
        last_complete_month_date = date.fromisoformat(
            bounds["last_day"]
        ).replace(day=1)
        last_complete_month_date = (
            last_complete_month_date.replace(day=1)
            if last_complete_month_date > date.today().replace(day=1)
            else last_complete_month_date
        )
        previous_month_end = last_complete_month_date.fromordinal(
            last_complete_month_date.toordinal() - 1
        )
        last_month = previous_month_end.strftime("%Y-%m")
        first_month = bounds["first_day"][:7]
        months = list(month_sequence(first_month, last_month))

        pages = conn.execute(
            """
            SELECT id, article, label_en
            FROM wikipedia_pages
            WHERE active = 1
            ORDER BY id
            """
        ).fetchall()

        series = []
        for index, page in enumerate(pages, start=1):
            rows = conn.execute(
                """
                SELECT SUBSTR(period_start, 1, 7) AS month,
                       SUM(views) AS views,
                       COUNT(*) AS observed_days
                FROM wikipedia_pageviews
                WHERE page_id = ? AND period_start < ?
                GROUP BY SUBSTR(period_start, 1, 7)
                """,
                (page["id"], f"{date.today():%Y-%m}-01"),
            ).fetchall()
            by_month = {
                row["month"]: {
                    "views": row["views"],
                    "days": row["observed_days"],
                }
                for row in rows
            }
            values = []
            for month in months:
                year, month_number = map(int, month.split("-"))
                expected_days = calendar.monthrange(year, month_number)[1]
                observed = by_month.get(month)
                # A partial month is missing data, not a low-volume month.
                if not observed or observed["days"] < expected_days * 0.8:
                    values.append([month, None, observed["days"] if observed else 0])
                else:
                    values.append([month, observed["views"], observed["days"]])
            series.append(
                {
                    "article": page["article"],
                    "label": page["label_en"],
                    "color": index,
                    "values": values,
                }
            )
    finally:
        conn.close()

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "firstMonth": first_month,
        "lastMonth": last_month,
        "series": series,
    }


def main() -> int:
    data = json.dumps(load_data(), ensure_ascii=False, separators=(",", ":"))
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    marker = "__WIKIPEDIA_PAGEVIEWS_DATA__"
    if template.count(marker) != 1:
        raise ValueError(f"expected exactly one {marker} marker in {TEMPLATE_PATH}")

    FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAGMENT_PATH.write_text(template.replace(marker, data), encoding="utf-8")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(RENDER_SCRIPT),
            str(FRAGMENT_PATH),
            str(OUTPUT_PATH),
        ],
        check=True,
    )
    # The renderer inherits Windows line-ending behavior; keep the tracked
    # artifact LF-only so `git diff --check` remains clean cross-platform.
    rendered = OUTPUT_PATH.read_text(encoding="utf-8")
    OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
