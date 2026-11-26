# Changelog

## 0.1.0 (2026-11-26)

- Shared core: settings, SQLAlchemy base with a portable upsert, evaluation harness (precision and recall at k, lead time, walk-forward splits), AI extraction with citation checks and field-level scoring.
- Council Radar ingestion for CSV, XLSX and ODS files, driven by TOML column maps, with validation reports.
- ONS code succession for merges and splits, and name matching for government lists.
- Seven resilience signals ranked within tier, and a transparent baseline rule score.
- Reference labels: 8 Section 114 notices and 104 EFS decisions, each with its source.
- Power BI views, Docker image, CI on SQLite and PostgreSQL.
