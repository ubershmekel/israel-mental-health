# Israel Mental Health Trends Index

A data project exploring whether public search/pageview behavior can serve
as a directional proxy for national mental health in Israel, grounded in
**Self-Determination Theory (SDT)**.

**Bottom line after building and testing both pipelines:** Wikipedia
pageviews turned out to be the reliable signal. Google Trends keyword
search volume, restricted to `geo=IL`, was too sparse and noisy for almost
every SDT-indicator phrase we tried — see [Conclusion](#conclusion-google-trends-vs-wikipedia-pageviews)
below.

**Live visualization:** https://claude.ai/code/artifact/f3b65d3b-0cf6-4de5-b069-42d510e5d911

## Background

This project grew out of the "גיבוש מדד לאומי לחוסן ולבריאות נפשית" hackathon
(Talpiot). The hackathon's roadmap defines five workstreams:

1. **הגדרות וגבולות גזרה** — Definitions & scope
2. **מיפוי נתונים קיימים** — Mapping existing data sources
3. **זיהוי אינדיקטורים** — Identifying indicators
4. **אפיון ופיתוח כלי** — Tool characterization & development
5. **התנסות ותיקוף** — Piloting & validation

This repo is our attempt at steps 3–5: pick concrete, trackable indicators,
build a tool that backfills their historical trend, and give people a way
to explore it. What we actually learned along the way (a keyword-based
composite index isn't reliably buildable from Google Trends alone) is as
much the outcome as the code.

## Theoretical framework: Self-Determination Theory

SDT holds that psychological well-being depends on satisfying three basic
needs. The original plan was to treat search-trend volume for carefully
chosen keywords as a rough, population-level proxy signal for each need —
directional and aggregate, similar in spirit to Google Flu Trends, never a
clinical measure.

| SDT need | What it means | What we looked for in search behavior |
|---|---|---|
| **Autonomy** (אוטונומיה) | Feeling like your choices/behavior are self-endorsed, not coerced | Searches about control over one's life, decision paralysis, feeling trapped, job/life freedom |
| **Competence / Ability** (מסוגלות) | Feeling effective, capable of mastering challenges | Searches about burnout, overwhelm, "how to cope", self-improvement, help-seeking for functioning problems |
| **Relatedness / Belonging** (שייכות) | Feeling connected to and cared about by others | Searches about loneliness, isolation, relationship breakdown, community/support-group seeking |

Plus a cross-cutting **crisis / distress** bucket (anxiety, depression,
suicide-related, panic attacks) that doesn't map to a single SDT need but
is highly relevant to national mental health monitoring. **Crisis is the
only bucket that ended up with real data** — see below.

## Conclusion: Google Trends vs. Wikipedia Pageviews

We built full pipelines for both sources and tried ~48 SDT-indicator
keywords (English + Hebrew, all four buckets) against Google Trends
restricted to `geo=IL`. Result:

- **~30 keywords: literally zero volume.** Most literal-translation idioms
  ("feeling trapped", "תחושת מלכוד") just aren't things people search,
  especially filtered to one small country.
- **~16 keywords: a single-week blip.** Google Trends normalizes each
  request to the max value in range, so one anomalous week reads as
  "100" — that's noise, not a trend, and unusable for an index.
- **2 keywords: genuinely dense, usable data** — `התקף חרדה` (anxiety
  attack) and `עזרה נפשית` (mental health help), both Hebrew, both
  crisis-bucket. 200/271 and 167/271 nonzero months respectively across
  2004–2026. These are kept and shown in the visualization as a secondary,
  illustrative signal — not as inputs to any composite index.
- **Autonomy bucket: nothing.** None of the 10 autonomy phrases tested
  (English or Hebrew) showed real signal.

Meanwhile **Wikipedia pageviews for the same crisis topics were dense and
reliable from day one** — full daily data since 2015-07-01, real weekly/
monthly patterns, no blocking, no noise floor. See
[`scripts/fetch_wikipedia_pageviews.py`](scripts/fetch_wikipedia_pageviews.py).

**Takeaway for anyone continuing this work:** don't try to build a
Google-Trends-only composite SDT index from small-country keyword volume —
the noise floor is too high for all but a handful of high-volume crisis
terms. Wikipedia pageviews (or a similarly high-traffic, topic-specific
absolute-count source) is the more promising foundation; Google Trends is
worth checking per-term opportunistically, not as a systematic pipeline.

## Data sources

### Wikipedia Pageviews (primary signal)

Wikimedia's official Analytics API — free, no auth wall, no rate-limit
drama, **absolute** daily view counts (not normalized like Trends) for
selected Hebrew mental-health articles, since 2015-07-01. Covers all
Hebrew Wikipedia readers worldwide (no Israel-only filter for an
individual article), so read it as a language-community signal.

```bash
cd scripts
python fetch_wikipedia_pageviews.py --test        # one request, no writes
python fetch_wikipedia_pageviews.py                # previous 365 days
python fetch_wikipedia_pageviews.py --full-history  # 2015-07-01 → yesterday
```

Writes to `data/wikipedia_pageviews.db`. For recurring/shared use, set a
descriptive User-Agent:

```bash
set WIKIMEDIA_USER_AGENT=IsraelMentalHealthIndex/0.1 (contact@example.org)
python fetch_wikipedia_pageviews.py --full-history
```

Currently tracked articles (see [`scripts/wikipedia_pages.py`](scripts/wikipedia_pages.py)):
Anxiety attack, Clinical depression, PTSD — all crisis-bucket.

### Google Trends (secondary, manual-CSV only)

**We tried two automated scrapers and abandoned both** (see
[Abandoned: automated Trends scraping](#abandoned-automated-trends-scraping)).
The reliable path that remains is manual:

1. Browse to `https://trends.google.com/explore?geo=IL&q=<term>&date=all`
2. Click **Download CSV** under "Interest over time"
3. Import it:

```bash
cd scripts
python import_trends_csv.py "path/to/downloaded.csv" --language he --indicator crisis
```

`--language` (`he`/`en`) and `--indicator` (`autonomy`/`competence`/
`relatedness`/`crisis`) are required since the CSV itself doesn't carry
that classification. The importer reads the term straight from the CSV
header, infers resolution (daily/weekly/monthly) from the actual date
gaps in the data, and is idempotent — re-importing the same file updates
rows in place instead of duplicating them.

Only bother with this for terms you have some reason to expect have real
volume (see the Conclusion above) — most won't.

## Architecture

```
  Wikipedia Pageviews API          Google Trends (manual CSV download)
          │                                    │
          ▼                                    ▼
  fetch_wikipedia_pageviews.py       import_trends_csv.py
          │                                    │
          ▼                                    ▼
  data/wikipedia_pageviews.db          data/trends.db
          │                                    │
          └─────────────────┬──────────────────┘
                             ▼
                    HTML visualization
              (published artifact, see link above)
```

### Database schema

**`data/wikipedia_pageviews.db`**
- `wikipedia_pages(id, project, article, language, indicator, label_en, active)`
- `wikipedia_pageviews(id, page_id, period_start, granularity, views, access, agent, fetched_at)`

**`data/trends.db`**
- `keywords(id, term, language, indicator, is_anchor, active)`
- `raw_observations(id, keyword_id, period_start, value, batch_id, fetched_at, mode)`

`mode` tags how a row was obtained (e.g. `csv-monthly:IL:2004-01-01:2026-07-01`,
or a leftover `solo-recent:IL` / `solo-full:...` from the abandoned scraper
runs) so different collection methods/date-ranges never get silently mixed.

SQLite is enough at this scale (a few dozen keywords/articles × a few
hundred points each). Both DB files are gitignored — regenerate them by
re-running the fetchers/importer, or ask whoever ran them for a copy.

## Abandoned: automated Trends scraping

Kept in the repo (`scripts/fetch_trends.py`, `scripts/keywords.py`) for
reference, but **not the recommended path** — use manual CSV import
instead. Two libraries were tried, in order:

1. **[pytrends](https://github.com/GeneralMills/pytrends)** — calls
   Google's internal API directly. Got an immediate 429 on the default
   User-Agent; a browser-like UA fixed the first call, but multi-keyword
   "compare" requests kept getting blocked regardless of pacing.
2. **[trendspyg](https://pypi.org/project/trendspyg/)** — drives a real
   headless Chrome browser instead, which dodged the 429s. But its
   post-render "widget replay" step only retries 3× at a fixed 2-second
   interval internally (not configurable), and that step failed
   persistently on wide date ranges even after we added our own outer
   retry with real backoff. It also has no way to distinguish "Google
   shows a genuine 'not enough data' state" from "the page structure
   changed" — both raise the same error, which we worked around by
   pattern-matching the exception message (fragile).

Both are real, working libraries — this isn't a bug report against them,
just a note that browser-driven Trends scraping fights Google's anti-bot
measures constantly, and for a small-country, low-volume keyword set the
payoff (see Conclusion above) didn't justify the fight. If you want to
pick this back up: `python fetch_trends.py --test` still works as a
connectivity check, and `--only "<term>"` lets you target specific
keywords instead of the full ~41-keyword catalog.

## Seed keyword catalog

The full set of ~48 keywords tried (most came back empty or noisy) lives
in [`scripts/keywords.py`](scripts/keywords.py), organized by SDT
indicator. Kept for reference / as a starting point if someone wants to
try Wikipedia-style pageview signals for a broader article set, or
revisit Trends on a subset with more patience than we had.

## Roadmap status

- [x] **Definitions & scope** — an SDT-indicator search/pageview proxy,
      explicitly not diagnostic.
- [x] **Map existing data** — Wikipedia Pageviews API identified and
      integrated as the reliable source; Google Trends explored and
      found insufficient on its own.
- [x] **Indicators** — keyword catalog built and empirically tested
      against real `geo=IL` volume (see Conclusion).
- [x] **Tool** — `fetch_wikipedia_pageviews.py`, `import_trends_csv.py`,
      SQLite storage, published HTML visualization.
- [x] **Pilot** — spikes in the Wikipedia data checked against known
      events (COVID waves, Mount Meron disaster, October 7) — see the
      visualization's "Notable spikes" panel.
- [ ] **Open**: no ground-truth validation yet (surveys, hotline call
      volume) against either signal — flagged as a real limitation, not
      done here.

## Getting started

```bash
python -m venv .venv
.venv/Scripts/activate      # or: source .venv/bin/activate  (macOS/Linux)
pip install -r requirements.txt
```

Then see [Data sources](#data-sources) above for the Wikipedia fetcher and
the manual Trends CSV import workflow.

### Not built

```bash
python scripts/build_index.py       # compute indicator + composite scores
streamlit run app/dashboard.py      # interactive exploration UI
```
Deferred: with real data in hand from only 2 Trends keywords + 3 Wikipedia
articles, a formal composite-scoring script felt premature — the published
HTML visualization covers exploration for now.

## Ethical & methodological notes

- Aggregate, anonymous data only — no individual-level data exists in
  either source by design.
- Treat any of this as a *screening/monitoring signal*, never a diagnosis
  of the population. Communicate uncertainty and known confounders
  (news-driven spikes, seasonality, holidays) alongside any published
  number.
- Be explicit in any public-facing output that correlation between
  search/pageview volume and true prevalence is unproven and
  term-specific — several terms here turned out to have *no* usable
  signal at all, which is itself a finding worth keeping visible rather
  than quietly dropping.
