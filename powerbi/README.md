# Power BI report

The report reads the CSVs written by `council-radar export-powerbi`. `sample_data/` holds an export of the synthetic panel, so you can build the report without downloading anything. Every council and figure in it is invented.

For real councils, run the export against your own database and point the report at that folder instead:

```bash
council-radar export-powerbi --k 20 --observed-until 2026-02-23 --out exports/powerbi
```

`exports/` is git-ignored. Keep it that way: the real scores rank named councils, and the score isn't precise enough to publish as a watchlist (see [docs/REAL_RESULTS.md](../docs/REAL_RESULTS.md)).

## 1. Load the tables

Get Data > Text/CSV, one file at a time, or Get Data > Folder on `sample_data/` and expand each file. In Power Query:
- `year`, `financial_year` and `rank_*` columns: whole number
- money, ratio and score columns: decimal number
- `as_of` and `event_date`: date
- `ons_code`, `model`, `tier`: text

| Table | Grain | Key |
|---|---|---|
| dim_council | council | ons_code |
| dim_year | financial year (ending) | year |
| fact_signals | council × year | ons_code, year |
| fact_score | council × year × model | ons_code, year, model |
| fact_event | distress event | ons_code, event_type, financial_year |
| fact_backtest_summary | model | model |
| fact_backtest_year | model × evaluation year | model, year |
| fact_backtest_outcome | model × evaluation year × at-risk council | model, year, ons_code |

## 2. Relationships

Create `dim_model` and `'Top N'` from [measures.dax](measures.dax) first. Then add these relationships, all one-to-many with single-direction filtering:

- `dim_council[ons_code]` to `fact_signals`, `fact_score`, `fact_event` and `fact_backtest_outcome`
- `dim_year[year]` to `fact_signals[year]`, `fact_score[year]`, `fact_backtest_year[year]` and `fact_backtest_outcome[year]`
- `dim_year[year]` to `fact_event[financial_year]`
- `dim_model[model]` to `fact_score`, `fact_backtest_summary`, `fact_backtest_year` and `fact_backtest_outcome`

Mark `dim_year` as the year dimension for sorting (sort `fy_label` by `year`).

## 3. Measures

Paste the blocks in [measures.dax](measures.dax). They cover:
- **Portfolio:** average score, change on last year, rank, top-N flag.
- **Finances:** reserves, DSG deficit, interest, social care.
- **Events:** EFS support in £m, councils with a Section 114 notice.
- **Backtest:** precision, recall, base rate, lift, false positives, missed events.

## 4. Suggested pages

1. **Overview.** Cards: Councils, Councils With EFS, Councils With s114, EFS Support £m. A bar chart of Avg Risk Score by tier. A year slicer.
2. **Watchlist.** A table of council, tier, score, Score Rank, top_drivers and Signal Coverage, filtered to In Top N = 1. Add a Top N slicer, a model slicer and a short note on precision. This page is for internal use only.
3. **Council drill-through.** Drill through on `ons_code`. Show a line chart of Usable Reserves % of NRE, Interest % of NRE and DSG Deficit £m by year, the score by year for each model, and the council's events.
4. **Backtest.** A matrix of model × year showing Precision, Recall, Base Rate and Lift vs Random. A confusion grid (flagged × had_event) using True Positives, False Positives and Missed Events. A text box with the caveats from REAL_RESULTS.md.
5. **Data quality.** Signal Coverage by tier and year, and the share of blank values per signal column.

## 5. Check the numbers

Before trusting a visual, check these on the backtest page with only the model slicer set (synthetic sample, k = 5):

| model | Precision | Recall | Base Rate |
|---|---|---|---|
| rules_v1 | 0.5333 | 0.5714 | 0.125 |
| reserves_only | 0.4667 | 0.5 | 0.125 |
| hgb | 0.4 | 0.4286 | 0.125 |

They should equal `fact_backtest_summary`. If they don't, a relationship or a column type is wrong.
