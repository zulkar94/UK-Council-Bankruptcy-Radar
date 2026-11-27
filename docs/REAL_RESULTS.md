# Backtest on real MHCLG data

Run on 27 November 2026 with the MHCLG revenue outturn multi-year data set (`Revenue_Outturn_time_series_data_v4.csv`, 2017-18 to 2025-26) and the events in `data/reference/distress_events.csv`.

## Setup

- **Councils:** 367 English councils (codes E06 to E10), built from the outturn file. Police, fire, national parks and combined authorities are excluded.
- **Signals available:** reserves (unallocated and earmarked), DSG deficit, interest payable, social care share, net revenue expenditure. About 99% of council-years have them, except DSG at 87%.
- **Signals missing:** external borrowing, commercial property and core spending power. They aren't in this file, so 0% coverage.
- **Events:** 8 Section 114 notices and 165 EFS rows covering every round from 2020-21 to 2026-27, across 55 councils. Event list treated as complete up to 23 February 2026.
- **EFS dates:** the pages for the 2020-21 to 2023-24 rounds were republished on 29 February 2024 without original decision dates. Each row therefore carries the earliest plausible date and its basis (`date_basis` column). An early date can only make the backtest harder, because it marks a council as already distressed sooner; it can never give a model credit for distress that was already public.
- **Horizon:** 2 years from a 1 December decision date.
- **Evaluated years:** 2022 and 2023 only. Earlier years lack three years of training history, and later years' outcome windows haven't closed.
- **Population:** 642 at-risk council-years, of which 33 (5.1%) went on to an event within two years. 28 distinct first events fall inside the evaluation window.

The rule weights were fixed before any real data was loaded. Results are reported for every k tried, not just the best.

## Results

| Flagged per year (k) | Model | Precision | Lift vs random | Recall | Events caught (of 28) |
|---|---|---|---|---|---|
| 10 | rules_v1 | 0.05 | 1.0x | 0.03 | 1 |
| 10 | reserves_only | 0.05 | 1.0x | 0.03 | 1 |
| 10 | hgb | 0.05 | 1.0x | 0.03 | 3 |
| 20 | rules_v1 | 0.30 | 5.8x | 0.36 | 10 |
| 20 | reserves_only | 0.10 | 1.9x | 0.12 | 4 |
| 20 | hgb | 0.10 | 1.9x | 0.12 | 7 |
| 30 | rules_v1 | 0.20 | 3.9x | 0.36 | 11 |
| 30 | reserves_only | 0.08 | 1.6x | 0.15 | 5 |
| 30 | hgb | 0.08 | 1.6x | 0.15 | 9 |
| 50 | rules_v1 | 0.13 | 2.5x | 0.39 | 11 |
| 50 | reserves_only | 0.14 | 2.7x | 0.42 | 12 |
| 50 | hgb | 0.07 | 1.4x | 0.21 | 10 |

"Events caught" counts councils flagged in any evaluation year before their first event. Precision and recall count council-years.

Adding the earlier EFS rounds (2020-21 to 2024-25) changed little. Precision at 20 rose from 0.23 to 0.30, and the earlier rounds moved several councils (Croydon, Slough, Nottingham, Lambeth) to an earlier first event.

## What this says

1. **The transparent score has some signal.** Flagging 20 councils a year, it caught 10 of the 28 that went on to need support, at about six times the random rate.
2. **It isn't stable.** At top 10 it's no better than random. With two evaluation years, one or two councils changing rank moves the headline. Treat it as indicative.
3. **The ML model adds little.** It beats random at most k but never beats the transparent score except on events caught at top 10. With about 20 training positives, that's expected.
4. **Reserves alone are weaker** up to k = 30, and level with the score at k = 50.

## Why the top 10 misses

Event rates differ hugely by tier. In 2023, 11 of 53 unitaries and 5 of 30 London boroughs went on to an event, against 1 of 178 districts and 1 of 24 counties. The score ranks councils within their tier, so each tier's weakest councils compete equally. Counties and districts with low reserves fill the top 10, and the real cases sit just below.

The obvious fix is to weight each tier by its historical event rate, learned from training years only. It hasn't been added. The idea came from looking at the evaluation-year rankings, so testing it on those same years would overstate it. It needs a fresh evaluation year (2024, once its window closes in December 2026).

**Flagged in advance (top 20):** Bradford, Enfield, Haringey, Havering, Middlesbrough, Shropshire, Southampton, Stoke-on-Trent, West Berkshire, Woking.

**Missed:**
- **Commercial borrowing** (Thurrock and others). That needs the borrowing and investment tables, which aren't loaded yet.
- **Equal pay liabilities and governance** (Birmingham). Neither is visible in outturn returns.
- **New councils** (Cumberland, Somerset, Westmorland and Furness, West Northamptonshire). They were created in 2021 or 2023, so there are few or no earlier rows to flag.

These are public outcomes, so naming them is a factual record. The current watchlist isn't published, because a score with this precision shouldn't be used to label councils that are still trading.

## Gaps that would most improve it

1. **Borrowing and commercial investment** (MHCLG borrowing and investment live tables). This would fill the debt and commercial signals.
2. **Tier-aware ranking**, tested on 2024 once its outcome window closes.
3. **Core spending power** from the finance settlements. Debt ratios use net revenue expenditure until then.

## Reproduce

```bash
council-radar init-db
council-radar extract-councils ro_multi_year data/raw/Revenue_Outturn_time_series_data_v4.csv
council-radar load-councils data/raw/councils.csv
council-radar ingest ro_multi_year data/raw/Revenue_Outturn_time_series_data_v4.csv
council-radar load-events data/reference/distress_events.csv
for k in 10 20 30 50; do council-radar backtest --k $k --observed-until 2026-02-23; done
```
