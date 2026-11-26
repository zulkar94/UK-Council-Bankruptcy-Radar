# UK Council Bankruptcy Radar

[![ci](https://github.com/zulkar94/UK-Council-Bankruptcy-Radar/actions/workflows/ci.yml/badge.svg)](https://github.com/zulkar94/UK-Council-Bankruptcy-Radar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)

An early-warning score for English councils at risk of a Section 114 notice or Exceptional Financial Support (EFS), built from public MHCLG and ONS data. It sits on a small shared core (`finance_ai_core`) that later finance AI projects will reuse.

> **Headline result:** not yet available for real councils. The backtest runs end to end on synthetic data (below), but real MHCLG data hasn't been loaded yet. When it has, this line will say how many councils that later needed support were flagged, and how far ahead.

## Status (v0.1)

| Done | Next |
|---|---|
| Shared core: evaluation harness, AI extraction with citation checks, portable upsert | Map real MHCLG revenue outturn headers (template provided) |
| Council Radar ingestion: CSV, XLSX and ODS; column maps in TOML; validation reports | Load ONS council list, borrowing and core spending power tables |
| ONS code succession (merges and splits), name matching for government lists | Section 25 statement extraction on 50 hand-labelled documents |
| Signals ranked within tier, transparent baseline score | Run the backtest on real data and publish the result |
| Walk-forward backtest: rules vs reserves-only vs HistGradientBoosting | Power BI report on the views in `sql/powerbi_views.sql` |
| Real reference labels: 8 Section 114 notices, 104 EFS decisions (2025-26 and 2026-27 rounds) | Earlier EFS rounds (2024-25 and before) |
| Tested on SQLite and PostgreSQL 16; 72 tests, 99% coverage | |

## Quickstart (synthetic sample, about 1 minute)

```bash
pip install -e ".[dev]"
council-radar init-db
council-radar load-councils data/sample/councils.csv
council-radar load-codemap data/sample/code_succession.csv
council-radar ingest sample_finance_year data/sample/finance_year.csv
council-radar load-events data/sample/events.csv
council-radar score --out exports/scores.csv
council-radar backtest --k 5 --observed-until 2025-03-31 --out exports/backtest.md
```

Defaults to a local SQLite file. For PostgreSQL set `FAI_DATABASE_URL=postgresql+psycopg://user:pass@host/db` and install `.[postgres]`, or run `docker compose up` after setting `POSTGRES_PASSWORD` in `.env`.

Everything in `data/sample/` is invented. Each synthetic council has a profile: healthy, distressed (finances drift, then an event two to three years later), recovering (drifts, then recovers with no event, which tempts false positives) or shock (an event with no warning in the numbers).

## Backtest

`council-radar backtest` compares three scorers on the same years and councils:

- **rules_v1:** the transparent weighted score.
- **reserves_only:** usable reserves relative to spending, nothing else. If a model can't beat this, it isn't worth its complexity.
- **hgb:** HistGradientBoosting with balanced class weights, retrained for each test year.

Timing rules:
- A financial year's figures count as known from 1 December after it ends.
- A row is positive if the council's first verified event falls within the horizon after that date.
- Rows after a council's first event are dropped.
- A model only trains on rows whose outcome window had closed by the test date.
- `--observed-until` says how far the event list is complete. Without it, the last event date is used, which is the cautious choice.

**On the synthetic sample** ([full report](docs/sample_backtest.md), top 5 flagged per year, 2020 to 2022):

| Model | Precision@5 | Recall@5 | Events caught | Median lead |
|---|---|---|---|---|
| rules_v1 | 0.53 | 0.57 | 6 of 9 | 400 days |
| reserves_only | 0.47 | 0.50 | 5 of 9 | 354 days |
| hgb | 0.40 | 0.43 | 6 of 9 | 350 days |

The ML model does not beat the transparent score here. With a few hundred rows and a handful of events that's the expected result, and the same could well hold on real data. The watchlist also shows the "recovering" councils near the top, which is the false-positive risk the README warns about. These numbers describe invented data and say nothing about real councils.

Everything in `data/sample/` is invented: names, codes (a `9xx` range that can't collide with real ONS codes) and figures. `scripts/make_sample_data.py` regenerates it with a fixed seed.

## Using real data

1. **Councils.** Download the Local Authority Districts and Counties names-and-codes lists from the ONS Open Geography Portal and save them as `councils.csv` with columns `ons_code,name`. Tier is inferred from the code prefix (E06 unitary, E07 district, E08 metropolitan, E09 London borough, E10 county).
2. **Code changes.** Add reorganisations to a succession CSV (`old_code,new_code,effective,weight`). Splits need weights that sum to 1, for example population shares.
3. **Finance.** Download the MHCLG revenue outturn multi-year data set, then:
   ```bash
   council-radar inspect data/raw/<file>
   ```
   Copy `src/council_radar/ingest/column_maps/ro_multi_year_TEMPLATE.toml`, replace each `TODO` with the real header, and ingest with `council-radar ingest path/to/your_map.toml data/raw/<file>`. Ingestion stops if codes or years fail validation; `--force` overrides it.
4. **Labels.** `council-radar load-events data/reference/distress_events.csv`. Names that don't match, or match more than one council, are listed rather than guessed.

Sources and caveats for each file are in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Design decisions

- **Compare within tier.** Districts don't run social care and counties don't collect most council tax. Every percentile is computed within (tier, year).
- **Baseline first.** The rule score uses weights fixed before looking at outcomes, and a reserves-only score sets the floor. With only eight Section 114 notices, fitting weights to them would be overfitting.
- **No leakage.** EFS events keep the date of the *first* decision for a year and the *latest* amount. Walk-forward splits leave a gap year, because outturn data is published months after year end.
- **AI output must cite its source.** Each extracted value carries a quote. If the quote isn't in the document, the value is dropped and its confidence set to zero. Document text is treated as data, never as instructions.
- **Pure domain code.** `council_radar/domain` and `finance_ai_core/eval` import no database or CLI code.

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Known limits

- The score is **relative**. Someone always tops each tier, so a percentile threshold will flag healthy councils in a healthy year. On the synthetic sample, a score of 75 or more flagged an undrifted council as early as the distressed ones. The backtest must report precision at k and false positives, not just hits.
- Labels cover the 2025-26 and 2026-27 EFS rounds only. Earlier rounds still need adding: until they are, some councils that really did need support in earlier years count as negatives, which drags down every model's score.
- The revenue outturn multi-year set starts in 2017-18. With a two-year horizon and three training years, only a couple of years can be evaluated, so treat early real results as indicative.
- Several Section 114 dates come from secondary sources and are marked `secondary` until checked against the council's own notice.
- This is a research tool. It describes financial risk signals and does not assess any council's governance or conduct.

## Layout

```
src/finance_ai_core/   config, db (base, engine, upsert), eval (metrics, splits), extraction
src/council_radar/     domain (codes, names, signals, rules, s25), backtest, ingest, db (models, repo), cli
data/reference/        real distress events with source URLs
data/sample/           synthetic panel for tests and demos
sql/                   Power BI views
tests/                 pytest suite
```

## Licence

MIT. See [LICENSE](LICENSE).
