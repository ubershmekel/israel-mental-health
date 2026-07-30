# Israel Mental Health Trends Index

A data project that turns Google Search Trends into a proxy index for
national mental health / psychological resilience in Israel, grounded in
**Self-Determination Theory (SDT)**.

## Background

This project grew out of the "גיבוש מדד לאומי לחוסן ולבריאות נפשית" hackathon
(Talpiot). The hackathon's roadmap defines five workstreams:

1. **הגדרות וגבולות גזרה** — Definitions & scope
2. **מיפוי נתונים קיימים** — Mapping existing data sources
3. **זיהוי אינדיקטורים** — Identifying indicators
4. **אפיון ופיתוח כלי** — Tool characterization & development
5. **התנסות ותיקוף** — Piloting & validation

This repo is our attempt at steps 3–5: pick concrete, trackable indicators,
build a tool that backfills their historical trend and gives people a way to
explore it.

## Theoretical framework: Self-Determination Theory

SDT holds that psychological well-being depends on satisfying three basic
needs. We treat search-trend volume for carefully chosen keywords as a rough,
population-level proxy signal for each need. This is **not** a clinical
measure — it's a directional, aggregate indicator, similar in spirit to
Google Flu Trends. It should be validated against known ground truth
(surveys, crisis-line volume, etc.) before being trusted.

| SDT need | What it means | What we look for in search behavior |
|---|---|---|
| **Autonomy** (אוטונומיה) | Feeling like your choices/behavior are self-endorsed, not coerced | Searches about control over one's life, decision paralysis, feeling trapped, job/life freedom |
| **Competence / Ability** (מסוגלות) | Feeling effective, capable of mastering challenges | Searches about burnout, overwhelm, "how to cope", self-improvement, help-seeking for functioning problems |
| **Relatedness / Belonging** (שייכות) | Feeling connected to and cared about by others | Searches about loneliness, isolation, relationship breakdown, community/support-group seeking |

We also track a small set of **crisis / distress indicators** (anxiety,
depression, suicide-related, panic attacks) as a cross-cutting severity
signal, since these don't map to a single SDT need but are highly relevant
to national mental health monitoring.

## Data source

- **Google Trends** (via [pytrends](https://github.com/GeneralMills/pytrends)
  or the official
  [Trends API (Alpha)](https://developers.google.com/search/blog/2025/07/trends-api)
  when available) — relative search interest (0–100) for keyword sets,
  region = Israel (`geo=IL`), full available history (Trends data starts
  **2004**, so a `timeframe=2004-01-01 2026-07-30` pull gets ~20 years).
- Optionally cross-reference with **Google Trends' own Hebrew/English
  autocomplete & related-queries** to expand/validate the keyword lists over
  time.
- Future: layer in public data mentioned in the hackathon's "מיפוי נתונים
  קיימים" step (e.g. Ministry of Health, Kann Social/117 hotline volumes,
  CBS surveys) for validation, not as the primary signal.

### Wikipedia Pageviews

Wikimedia's official Analytics API provides an independent, absolute-volume
signal for selected Hebrew mental-health articles. Per-article history starts
on 2015-07-01. This signal covers all readers of Hebrew Wikipedia worldwide;
the API does not provide an Israel-only geographic filter for an individual
article.

### Why Google Trends

- Free, no auth wall for basic pulls, deep historical coverage back to 2004,
  granular by region/time, and Hebrew-language support out of the box.
- Weaknesses to keep in mind:
  - **Relative, not absolute** volume — each request is independently
    normalized 0–100.
  - **Resolution drops as the time window grows.** Google Trends returns
    daily granularity only for windows under ~90 days; a multi-year request
    like ours is auto-aggregated to **weekly** points for ranges up to ~5
    years, and to **monthly** points beyond that. A 20-year pull means
    **monthly resolution** (~240 points per keyword), not weekly.
  - **Re-normalization across batches**: since values are only comparable
    within one request, and one request covers max 5 terms, we need a
    stable **anchor term** included in every batch (or Trends' own
    overlapping-window rescaling approach) to stitch all keywords onto one
    common scale across the full 20-year span.
  - Small volumes get noisy (rare Hebrew phrasings may show as 0 for long
    stretches then spike), and results are sensitive to exact
    phrasing/spelling (Hebrew has multiple valid spellings for the same
    term — need to test variants).
  - Rate limiting: pytrends hits Google's public endpoint, which throttles
    aggressively — a full backfill across many keyword batches needs
    retries/backoff and will take a while to run, but since this is a
    one-time historical pull (not a recurring job) that's a one-off cost.

## Seed keyword lists (draft — to be refined in step 3 above)

Each indicator needs: an English list, a Hebrew list, and an "anchor" term
(a stable, unrelated high-volume term like "מזג אוויר" / "weather") used in
every batch to rescale scores onto a common axis, since Google Trends only
returns relative values within a single request of ≤5 terms.

### Autonomy (אוטונומיה)

| English | Hebrew |
|---|---|
| feeling trapped | תחושת מלכוד |
| lost control of my life | איבדתי שליטה על החיים |
| decision fatigue | עייפות החלטות |
| quit my job | להתפטר מהעבודה |
| burnout no choice | אין לי ברירה |

### Competence / Ability (מסוגלות)

| English | Hebrew |
|---|---|
| burnout symptoms | תסמיני שחיקה |
| can't cope | לא מסתדר/ת |
| how to stop procrastinating | איך להפסיק לדחיין |
| feeling overwhelmed | תחושת עומס |
| imposter syndrome | תסמונת המתחזה |

### Relatedness / Belonging (שייכות)

| English | Hebrew |
|---|---|
| feeling lonely | מרגיש/ה בודד/ה |
| loneliness help | עזרה לבדידות |
| no friends | אין לי חברים |
| support group near me | קבוצת תמיכה |
| social isolation | בידוד חברתי |

### Crisis / distress (cross-cutting severity signal)

| English | Hebrew |
|---|---|
| anxiety attack | התקף חרדה |
| depression symptoms | תסמיני דיכאון |
| suicide hotline | קו חם התאבדות |
| panic attack help | עזרה בהתקף פאניקה |
| ער"ן (crisis line brand term, Hebrew-only) | ער"ן |

> Keyword lists are intentionally short to start. Expand via Google Trends
> "related queries" output once the pipeline is running, and validate each
> candidate term doesn't have an unrelated dominant meaning (e.g. ambiguous
> words that spike for reasons unrelated to mental health).

## Architecture

```
                 ┌───────────────────┐
                 │  Google Trends     │
                 │  (pytrends)        │
                 └─────────┬─────────┘
                           │ one-time backfill, 2004→today,
                           │ per keyword batch (≤5 terms + anchor)
                           ▼
                 ┌───────────────────┐
                 │  Backfill script   │  scripts/fetch_trends.py
                 │  - batches keywords│
                 │  - full-history    │
                 │    timeframe pull  │
                 │  - rescales w/     │
                 │    anchor term     │
                 │  - retry/backoff   │
                 │    for rate limits │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  SQLite DB         │  data/trends.db
                 │  raw_observations  │
                 │  keywords          │
                 │  indicators        │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  Aggregation       │  scripts/build_index.py
                 │  - normalize       │
                 │  - avg per         │
                 │    indicator       │
                 │  - composite index │
                 └─────────┬─────────┘
                           ▼
                 ┌───────────────────┐
                 │  Dashboard         │  app/dashboard.py (Streamlit)
                 │  - 20yr time series│
                 │  - per-indicator   │
                 │  - keyword drill-  │
                 │    down            │
                 │  - event overlays  │
                 │    (wars, COVID…)  │
                 └───────────────────┘
```

The backfill script is designed to be **re-run occasionally** (not on a
fixed schedule) to append recent months once new Trends data becomes
available — it should be idempotent (upsert by keyword + month) so re-runs
just extend/refresh the tail of the series rather than re-pulling everything.

### Database schema (draft)

- `keywords(id, term, language, indicator, is_anchor, active)`
- `raw_observations(id, keyword_id, month_start, value, batch_id, fetched_at)`
- `indicator_scores(id, indicator, month_start, score)` — computed table
- `composite_index(month_start, score)` — computed table

SQLite is enough for this scale (a few dozen keywords × ~240 monthly points
each = low thousands of rows). Can move to Parquet/DuckDB later if we add
finer time resolution or more regions.

## Roadmap

- [ ] **Step 1 — Definitions & scope**: finalize what "index" means, what
      time resolution, what geographic granularity (national only, or
      per-district?), and what we explicitly will *not* claim (this is not
      a diagnostic tool).
- [ ] **Step 2 — Map existing data**: list public MH-adjacent datasets
      (Ministry of Health, CBS, hotline call volumes) to use for validation.
- [ ] **Step 3 — Indicators**: finalize keyword lists above with a subject-
      matter reviewer; test Hebrew spelling variants; pick anchor term(s).
- [ ] **Step 4 — Tool**:
  - [ ] `scripts/fetch_trends.py` — pytrends historical backfill
        (`timeframe='2004-01-01 <today>'`), anchor-based rescaling, retry/
        backoff for rate limits, idempotent upsert into SQLite
  - [ ] `scripts/build_index.py` — per-indicator + composite scoring
  - [ ] `app/dashboard.py` — Streamlit exploration UI (20-year time series,
        filter by indicator/keyword/language, compare to known events)
  - [ ] Manual/occasional re-run (not scheduled) to extend the series as
        new months of Trends data become available
- [ ] **Step 5 — Pilot & validate**: sanity-check spikes against known
      historical events (wars, holidays, terror attacks, COVID waves),
      compare trend direction against any available survey data across the
      full 20-year window.

## Getting started

```bash
python -m venv .venv
.venv/Scripts/activate      # or: source .venv/bin/activate  (macOS/Linux)
pip install -r requirements.txt
```

### Running the fetcher on any machine (do these in order)

Google blocks scraper-like traffic aggressively, so **always start with a
connectivity test** before running a real batch job — especially the first
time on a new machine or network:

```bash
cd scripts
python fetch_trends.py --test
```

This sends **exactly one request** (`weather`, most recent 12 months) and
tells you immediately whether the environment can reach Google Trends at
all, without risking a real batch. Check `logs/fetch_<timestamp>.log` for
the result.

Once the test passes, run the default (cheap) pass — most recent 12 months
for every keyword batch, ~10 requests total, paced ~25s apart:

```bash
python fetch_trends.py
```

Many mental-health search phrases will legitimately have **zero volume**
when restricted to `geo=IL` — that's an expected result, not a failure.
Every run writes:

- `logs/fetch_<timestamp>.log` — a full run log (every request, retry, and
  outcome)
- `logs/fetch_<timestamp>_report.txt` — a per-keyword summary table (max
  value seen, and whether it had any IL search volume at all)

Read the report before spending a full historical pull on a keyword that
turned out to have no signal. Once you know which keywords are worth it,
pull their full ~20-year history (comes back at ~yearly resolution for a
window this wide):

```bash
python fetch_trends.py --full-history
```

Results are written to `data/trends.db` immediately after each batch (not
buffered to the end), and re-running is safe — rows are upserted, so a
partial or interrupted run never duplicates data and can just be re-run to
pick up where it left off.

### Wikipedia Pageviews collector

The independent Wikipedia collector uses only Python's standard library and
writes absolute daily counts to `data/wikipedia_pageviews.db`, deliberately
separate from Google Trends' normalized 0-100 observations.

```bash
cd scripts
python fetch_wikipedia_pageviews.py --test
python fetch_wikipedia_pageviews.py
python fetch_wikipedia_pageviews.py --full-history
```

The default run refreshes the previous 365 complete days. The full-history
run fetches 2015-07-01 through yesterday in API-friendly yearly chunks.
For recurring or shared use, identify the project with a User-Agent containing
a contact URL or email:

```bash
set WIKIMEDIA_USER_AGENT=IsraelMentalHealthIndex/0.1 (contact@example.org)
python fetch_wikipedia_pageviews.py --full-history
```

### Next steps (not built yet)

```bash
python scripts/build_index.py       # compute indicator + composite scores
streamlit run app/dashboard.py      # explore
```

## Ethical & methodological notes

- Aggregate, anonymous search volume only — no individual-level data exists
  in Google Trends by design.
- Treat this as a *screening/monitoring signal*, not a diagnosis of the
  population. Communicate uncertainty and known confounders (news-driven
  spikes, seasonality, holidays) alongside any published number.
- Be explicit in any public-facing output that correlation between search
  volume and true prevalence is unproven and indicator-specific.
