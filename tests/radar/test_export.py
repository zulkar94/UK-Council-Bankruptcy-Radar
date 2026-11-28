from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from council_radar.backtest import BacktestConfig
from council_radar.cli import main
from council_radar.export import build_tables, fy_label, write_tables

from ..conftest import SAMPLE

CFG = BacktestConfig(k=5, observed_until=date(2025, 3, 31))


@pytest.fixture(scope="module")
def tables(sample: tuple[pd.DataFrame, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    panel, events = sample
    councils = pd.read_csv(SAMPLE / "councils.csv", dtype=str, keep_default_na=False)
    councils["tier"] = ["unitary"] * len(councils)
    return build_tables(councils, panel, events, CFG)


def test_star_schema_keys_are_unique(tables: dict[str, pd.DataFrame]) -> None:
    keys = {
        "dim_council": ["ons_code"],
        "dim_year": ["year"],
        "fact_signals": ["ons_code", "year"],
        "fact_score": ["ons_code", "year", "model"],
        "fact_backtest_summary": ["model"],
        "fact_backtest_year": ["model", "year"],
        "fact_backtest_outcome": ["model", "year", "ons_code"],
    }
    for name, cols in keys.items():
        assert not tables[name].duplicated(cols).any(), name
    # Every fact row joins to a council and a year.
    codes = set(tables["dim_council"]["ons_code"])
    years = set(tables["dim_year"]["year"])
    for name in ("fact_signals", "fact_score", "fact_backtest_outcome"):
        assert set(tables[name]["ons_code"]) <= codes, name
        assert set(tables[name]["year"]) <= years, name


def test_outcomes_reconcile_with_summary(tables: dict[str, pd.DataFrame]) -> None:
    out = tables["fact_backtest_outcome"]
    summary = tables["fact_backtest_summary"].set_index("model")
    for model, d in out.groupby("model"):
        tp = int(((d.flagged == 1) & (d.had_event == 1)).sum())
        assert tp / d.flagged.sum() == pytest.approx(summary.loc[model, "precision"], abs=1e-4)
        assert tp / d.had_event.sum() == pytest.approx(summary.loc[model, "recall"], abs=1e-4)
        assert d.had_event.mean() == pytest.approx(summary.loc[model, "base_rate"], abs=1e-4)


def test_scores_ranked_per_year(tables: dict[str, pd.DataFrame]) -> None:
    sc = tables["fact_score"]
    assert set(sc["model"]) == {"rules_v1", "reserves_only"}
    one = sc[(sc.model == "rules_v1") & (sc.year == 2020)].sort_values("rank_overall")
    assert one["rank_overall"].iloc[0] == 1
    assert one["score"].is_monotonic_decreasing
    assert tables["dim_council"]["tier_label"].eq("Unitary").all()
    assert tables["dim_year"].set_index("year").loc[2024, "fy_label"] == "2023-24"


def test_fy_label() -> None:
    assert fy_label(2000) == "1999-00"
    assert fy_label(2026) == "2025-26"


def test_write_tables_no_exponents(tables: dict[str, pd.DataFrame], tmp_path: Path) -> None:
    paths = write_tables(tables, tmp_path / "pbi")
    assert {p.stem for p in paths} == set(tables)
    text = (tmp_path / "pbi" / "fact_event.csv").read_text()
    assert "e+0" not in text


def test_cli_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = ["--db", f"sqlite:///{tmp_path / 'x.db'}"]
    out = tmp_path / "pbi"
    assert main([*db, "init-db"]) == 0
    assert main([*db, "export-powerbi", "--out", str(out)]) == 1  # nothing loaded
    for step in (
        ["load-councils", str(SAMPLE / "councils.csv")],
        ["ingest", "sample_finance_year", str(SAMPLE / "finance_year.csv")],
        ["load-events", str(SAMPLE / "events.csv")],
    ):
        assert main([*db, *step]) == 0
    args = ["export-powerbi", "--k", "5", "--observed-until", "2025-03-31", "--out", str(out)]
    assert main([*db, *args]) == 0
    assert "fact_backtest_outcome.csv" in capsys.readouterr().out
    assert len(list(out.glob("*.csv"))) == 8
