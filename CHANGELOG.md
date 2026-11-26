# Changelog

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
