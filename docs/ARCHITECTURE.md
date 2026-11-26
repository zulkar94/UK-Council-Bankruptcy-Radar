# Architecture

```
            data/raw/*.csv|xlsx|ods
                     │
        column map (TOML) ──► ingest.loader ──► ValidationReport
                     │                               │ stops on bad codes or years
                     ▼                               ▼
              canonical DataFrame ──────► db.repo ──► PostgreSQL / SQLite
                                                  │
     dim_council · map_council_code · fact_finance_year · fact_event · fact_risk_score
                                                  │
                     domain.signals ◄─────────────┘
                           │  ratios, 3-year trend, percentile within (tier, year)
                     domain.rules ──► fact_risk_score ──► sql/powerbi_views.sql ──► Power BI
                           │
         finance_ai_core.eval (precision@k, lead time, walk-forward)   [backtest, next]
         finance_ai_core.extraction + domain.s25                       [AI layer, next]
```

## Packages

**`finance_ai_core`**: shared with the planned Audit Arena project.
- `config`: settings from `FAI_*` environment variables.
- `db`: declarative base, engine factory, and `upsert` for SQLite and PostgreSQL. `upsert` updates only the columns it is given, so two sources can fill different columns of the same row.
- `eval`: pure metrics. `lead_times` ignores flags raised after the event or inside a minimum window, so a model gets no credit for spotting a failure that is already in the news.
- `extraction`: an `LLMClient` protocol (any provider fits), Pydantic schemas in which every field carries a citation, a quote check against the source text, and field-level scoring against a gold set.

**`council_radar`**
- `domain`: pure logic, with no IO, database or CLI imports.
  - `codes`: ONS succession, with weighted splits and cycle detection.
  - `names`: normalised name matching that reports ambiguous and unmatched names.
  - `signals`, `rules`, `s25`.
- `ingest`: TOML specs and the file loader.
- `db`: ORM models and the repository.
- `cli`: `council-radar` commands.

## Schema notes

- `fact_finance_year` is one wide row per council per year. Each source fills its own columns. This is simpler for Power BI than one table per source and costs nothing at roughly 400 councils × 10 years.
- `fact_event.verification` is `primary`, `secondary` or `unverified`. Views and `events_frame` drop `unverified` by default.
- Money is stored in GBP. Loaders apply `units_multiplier` (MHCLG tables are in £ thousands).

## Not built yet

- ML model and backtest runner using `walk_forward` and `lead_times`.
- Provider adapter for `LLMClient`, plus a PDF to text step for Section 25 statements.
- Weighted re-attribution of predecessor values to successor councils using `CodeMap.resolve`. The map is loaded and validated but not yet applied in scoring.
