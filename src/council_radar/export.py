"""Export a star schema of CSVs for Power BI (or any BI tool).

Tables (keys in brackets):
    dim_council [ons_code]            name, tier, region
    dim_year [year]                   financial year label, decision (as-of) date
    fact_signals [ons_code, year]     inputs in GBP, ratios, within-tier risk percentiles
    fact_score [ons_code, year, model]  score, rank overall and within tier
    fact_event [ons_code, event_type, financial_year]
    fact_backtest_summary [model]     precision, recall, base rate, lift, lead time
    fact_backtest_year [model, year]  the same, per evaluation year
    fact_backtest_outcome [model, year, ons_code]  flagged or not, and what happened

CSV is used on purpose: it loads in Power BI Desktop with no driver, and the files
diff cleanly in git.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from council_radar.backtest import BacktestConfig, as_of, build_frame, run_backtest
from council_radar.domain.rules import rule_score
from council_radar.domain.signals import INPUT_COLUMNS, SIGNAL_DIRECTION, compute_signals

TIER_LABELS = {
    "district": "Shire district",
    "county": "County",
    "unitary": "Unitary",
    "metropolitan": "Metropolitan district",
    "london_borough": "London borough",
    "other": "Other",
}
SCORE_MODELS = ("rules_v1", "reserves_only")


def fy_label(year: int) -> str:
    return f"{year - 1}-{str(year)[2:]}"


def _ranked(df: pd.DataFrame, model: str) -> pd.DataFrame:
    out = df.copy()
    out["model"] = model
    out["rank_overall"] = out.groupby("year")["score"].rank(ascending=False, method="min")
    out["rank_in_tier"] = out.groupby(["year", "tier"])["score"].rank(ascending=False, method="min")
    return out


def build_tables(
    councils: pd.DataFrame,
    panel: pd.DataFrame,
    events: pd.DataFrame,
    cfg: BacktestConfig | None = None,
) -> dict[str, pd.DataFrame]:
    cfg = cfg or BacktestConfig()
    signals = compute_signals(panel)

    dim_council = councils[["ons_code", "name", "tier", "region"]].copy()
    dim_council["tier_label"] = dim_council["tier"].map(TIER_LABELS).fillna("Other")

    years = sorted(signals["year"].unique().tolist())
    dim_year = pd.DataFrame(
        {
            "year": years,
            "fy_label": [fy_label(y) for y in years],
            "as_of": [as_of(y) for y in years],
        }
    )

    sig_cols = [f"{s}_risk_pct" for s in SIGNAL_DIRECTION]
    fact_signals = signals[
        ["ons_code", "year", *INPUT_COLUMNS[3:], *SIGNAL_DIRECTION, *sig_cols]
    ].copy()

    rules = rule_score(signals)
    rules_tbl = _ranked(
        rules[["ons_code", "year", "tier", "score", "coverage", "top_drivers"]], "rules_v1"
    )
    reserves = signals[["ons_code", "year", "tier"]].copy()
    reserves["score"] = signals["reserves_to_nre_risk_pct"] * 100
    reserves["coverage"] = signals["reserves_to_nre_risk_pct"].notna().astype(float)
    reserves["top_drivers"] = "reserves_to_nre"
    fact_score = pd.concat([rules_tbl, _ranked(reserves, "reserves_only")], ignore_index=True).drop(
        columns="tier"
    )

    fact_event = events.copy()

    report = run_backtest(panel, events, cfg)
    summary_rows, year_rows, outcome_rows = [], [], []
    frame = build_frame(panel, events, cfg.horizon)
    for name, m in report.models.items():
        summary_rows.append(
            {
                "model": name,
                "k": cfg.k,
                "horizon_years": cfg.horizon,
                "eval_years": ",".join(map(str, m.years)),
                "precision": round(m.precision, 4),
                "recall": round(m.recall, 4),
                "base_rate": round(m.base_rate, 4),
                "lift": round(m.lift, 3) if m.lift is not None else None,
                "events_caught": len(m.caught),
                "events_missed": len(m.missed),
                "median_lead_days": m.median_lead_days,
            }
        )
        year_rows += [{"model": name, **row} for row in m.per_year]
        for y, top in m.flagged.items():
            t = frame[frame["year"] == y]
            flagged = set(top)
            outcome_rows += [
                {
                    "model": name,
                    "year": y,
                    "ons_code": c,
                    "flagged": int(c in flagged),
                    "had_event": int(lbl),
                }
                for c, lbl in zip(t["ons_code"], t["label"], strict=True)
            ]

    return {
        "dim_council": dim_council,
        "dim_year": dim_year,
        "fact_signals": fact_signals,
        "fact_score": fact_score,
        "fact_event": fact_event,
        "fact_backtest_summary": pd.DataFrame(summary_rows),
        "fact_backtest_year": pd.DataFrame(year_rows),
        "fact_backtest_outcome": pd.DataFrame(
            outcome_rows, columns=["model", "year", "ons_code", "flagged", "had_event"]
        ),
    }


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, df in tables.items():
        path = out_dir / f"{name}.csv"
        # Plain decimals, no exponent notation: safer for Power Query type detection.
        df.round(6).to_csv(path, index=False)
        written.append(path)
    return written
