# Changelog

## 0.3.0 (2026-11-27)

- Real-data backtest on the MHCLG revenue outturn file: results in `docs/REAL_RESULTS.md`.
- Column map completed from the metadata workbook: net revenue expenditure, unallocated and earmarked reserves, DSG deficit (sign flipped so deficits are positive), interest payable.
- Loader: keep only council codes, per-field scale factors, wider total-row pattern.
- Event loading: optional `ons_code` column pins ambiguous names (Somerset, Medway); RO name suffixes (UA, BC, MBC, CC, DC, LB) ignored when matching.
- Backtest reports base rate and lift against random picking.
- Every EFS round from 2020-21 to 2024-25 added (61 rows plus Norfolk), with a `date_basis` column; earliest plausible dates used where gov.uk gives none.
- Debt and commercial ratios fall back to net revenue expenditure when core spending power is missing.

## 0.2.0 (2026-11-26)

- Walk-forward backtest (`council-radar backtest`): rules_v1, reserves-only and HistGradientBoosting compared on the same years, with precision and recall at k, lead time, a watchlist, and markdown and JSON reports.
- Leakage controls: 1 December decision date, rows after the first event dropped, training limited to closed outcome windows, `--observed-until` for event list completeness.
- Richer synthetic panel: 45 councils over 10 years with healthy, distressed, recovering and shock profiles.
- scikit-learn added as a dependency.
- Real MHCLG outturn layout: built-in `ro_multi_year` map, YYYYMM years, total rows skipped instead of rejected, `Not set` treated as missing, fields summed from several columns.
- `council-radar extract-councils` builds the council list from the outturn file.

## 0.1.0 (2026-11-26)

- Shared core: settings, SQLAlchemy base with a portable upsert, evaluation harness (precision and recall at k, lead time, walk-forward splits), AI extraction with citation checks and field-level scoring.
- Council Radar ingestion for CSV, XLSX and ODS files, driven by TOML column maps, with validation reports.
- ONS code succession for merges and splits, and name matching for government lists.
- Seven resilience signals ranked within tier, and a transparent baseline rule score.
- Reference labels: 8 Section 114 notices and 104 EFS decisions, each with its source.
- Power BI views, Docker image, CI on SQLite and PostgreSQL.
