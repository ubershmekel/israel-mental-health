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
build a tool that pulls the data on a schedule, and give people a way to
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
  region = Israel (`geo=IL`), weekly resolution.
- Optionally cross-reference with **Google Trends' own Hebrew/English
  autocomplete & related-queries** to expand/validate the keyword lists over
  time.
- Future: layer in public data mentioned in the hackathon's "מיפוי נתונים
  קיימים" step (e.g. Ministry of Health, Kann Social/117 hotline volumes,
  CBS surveys) for validation, not as the primary signal.

### Why Google Trends

- Free, no auth wall for basic pulls, updated continuously, granular by
  region/time, and Hebrew-language support out of the box.
- Weaknesses to keep in mind: relative (not absolute) volume, indices are
  re-normalized per query batch (need an "anchor term" to stitch batches
  together consistently), small daily samples get noisy, and results are
  sensitive to exact phrasing/spelling (Hebrew has multiple valid spellings
  for the same term — need to test variants).

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
                           │ weekly fetch, per keyword batch
                           ▼
                 ┌───────────────────┐
                 │  Ingest script     │  scripts/fetch_trends.py
                 │  - batches keywords│
                 │  - rescales w/     │
                 │    anchor term     │
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
                 │  - time series     │
                 │  - per-indicator   │
                 │  - keyword drill-  │
                 │    down            │
                 └───────────────────┘
```

### Database schema (draft)

- `keywords(id, term, language, indicator, is_anchor, active)`
- `raw_observations(id, keyword_id, week_start, value, batch_id, fetched_at)`
- `indicator_scores(id, indicator, week_start, score)` — computed table
- `composite_index(week_start, score)` — computed table

SQLite is enough for this scale (a few hundred keywords × weekly points).
Can move to Parquet/DuckDB later if we add finer time resolution or more
regions.

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
  - [ ] `scripts/fetch_trends.py` — pytrends ingestion with anchor-based
        rescaling, writes to SQLite
  - [ ] `scripts/build_index.py` — per-indicator + composite scoring
  - [ ] `app/dashboard.py` — Streamlit exploration UI (time series, filter
        by indicator/keyword/language, compare to known events)
  - [ ] Scheduled run (cron / GitHub Actions) for weekly refresh
- [ ] **Step 5 — Pilot & validate**: run for a few months, sanity-check
      spikes against known events (wars, holidays, terror attacks, COVID
      waves), compare trend direction against any available survey data.

## Getting started (once code exists)

```bash
pip install -r requirements.txt
python scripts/fetch_trends.py      # populate data/trends.db
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
