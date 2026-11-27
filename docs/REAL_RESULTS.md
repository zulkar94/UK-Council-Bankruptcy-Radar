# Backtest on real MHCLG data

Run on 27 November 2026 with the MHCLG revenue outturn multi-year data set (`Revenue_Outturn_time_series_data_v4.csv`, 2017-18 to 2025-26) and the events in `data/reference/distress_events.csv`.

## Setup

- **Councils:** 367 English councils (codes E06 to E10), built from the outturn file. Police, fire, national parks and combined authorities are excluded.
- **Signals available:** reserves (unallocated and earmarked), DSG deficit, interest payable, social care share, net revenue expenditure. About 99% of council-years have them, except DSG at 87%.
- **Signals missing:** external borrowing, commercial property and core spending power. They aren't in this file, so 0% coverage.
- **Events:** 8 Section 114 notices and 95 EFS decisions (2025-26 and 2026-27 rounds) across 46 councils. Event list treated as complete up to 23 February 2026.
- **Horizon:** 2 years from a 1 December decision date.
- **Evaluated years:** 2022 and 2023 only. Earlier years lack three years of training history, and later years' outcome windows haven't closed.
- **Population:** 658 at-risk council-years, of which 25 (3.8%) went on to an event within two years. 27 distinct events fall inside the evaluation window.

The rule weights were fixed before any real data was loaded. Results are reported for every k tried, not just the best.

## Results

| Flagged per year (k) | Model | Precision | Lift vs random | Recall | Events caught (of 27) |
|---|---|---|---|---|---|
| 10 | rules_v1 | 0.05 | 1.3x | 0.04 | 1 |
| 10 | reserves_only | 0.05 | 1.3x | 0.04 | 1 |
| 10 | hgb | 0.05 | 1.3x | 0.04 | 1 |
| 20 | rules_v1 | 0.23 | 5.9x | 0.36 | 9 |
| 20 | reserves_only | 0.07 | 2.0x | 0.12 | 5 |
| 20 | hgb | 0.05 | 1.3x | 0.08 | 3 |
| 30 | rules_v1 | 0.17 | 4.4x | 0.40 | 11 |
| 30 | reserves_only | 0.07 | 1.8x | 0.16 | 6 |
| 30 | hgb | 0.07 | 1.8x | 0.16 | 6 |
| 50 | rules_v1 | 0.10 | 2.6x | 0.40 | 11 |
| 50 | reserves_only | 0.09 | 2.4x | 0.36 | 10 |
| 50 | hgb | 0.09 | 2.4x | 0.36 | 10 |

Median lead time for the rule score was 812 days.

## What this says

1. **The transparent score has some signal.** Flagging 20 councils a year, it found 9 of the 27 that later needed support, at about six times the random rate.
2. **It isn't stable.** At top 10 it catches 1. With two evaluation years and 25 positives, one or two councils moving rank changes the headline. Treat it as indicative.
3. **The ML model adds nothing.** It's at or near random at every k, which is expected with only a handful of training positives. It stays in the comparison as a check, not as the recommended score.
4. **Reserves alone are a weak signal.** The weighted score beats them at every k up to 30.

**Flagged in advance (top 20):** Bradford, Enfield, Haringey, Havering, Shropshire, Southampton, Stoke-on-Trent, West Berkshire, Woking.

**Missed:**
- **Commercial borrowing** (Thurrock and others). That needs the borrowing and investment tables, which aren't loaded yet.
- **Equal pay liabilities and governance** (Birmingham). Neither is visible in outturn returns.
- **New councils** (Cumberland, Somerset). They were created in 2023, so there are no earlier rows to flag.

These are public outcomes, so naming them is a factual record. The current watchlist isn't published, because a score with this precision shouldn't be used to label councils that are still trading.

## Gaps that would most improve it

1. **Borrowing and commercial investment** (MHCLG borrowing and investment live tables). This would fill the debt and commercial signals.
2. **Earlier EFS rounds (2020-21 to 2024-25).** Some councils that needed support before 2025 are currently treated as negatives in training.
3. **Core spending power** from the finance settlements, the denominator for debt ratios.

## Reproduce

```bash
council-radar init-db
council-radar extract-councils ro_multi_year data/raw/Revenue_Outturn_time_series_data_v4.csv
council-radar load-councils data/raw/councils.csv
council-radar ingest ro_multi_year data/raw/Revenue_Outturn_time_series_data_v4.csv
council-radar load-events data/reference/distress_events.csv
for k in 10 20 30 50; do council-radar backtest --k $k --observed-until 2026-02-23; done
```
