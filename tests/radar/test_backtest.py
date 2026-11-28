from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from council_radar.backtest import (
    ML_FEATURES,
    BacktestConfig,
    as_of,
    build_frame,
    first_events,
    make_hgb_scorer,
    render_markdown,
    run_backtest,
)
from council_radar.cli import main

from ..conftest import SAMPLE

OBSERVED = date(2025, 3, 31)


def ev(code: str, d: date, verification: str = "primary") -> dict[str, object]:
    return {"ons_code": code, "event_date": d, "verification": verification}


def test_first_events_ignores_unverified() -> None:
    events = pd.DataFrame(
        [
            ev("A", date(2022, 5, 1)),
            ev("A", date(2021, 5, 1)),
            ev("B", date(2020, 1, 1), "unverified"),
        ]
    )
    assert first_events(events) == {"A": date(2021, 5, 1)}
    assert first_events(events.iloc[2:]) == {}


def test_build_frame_labels_and_drops_post_event_rows(
    sample: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    panel, events = sample
    code = "E06000903"  # first event 2019-11
    frame = build_frame(panel, events, horizon=2)
    rows = frame[frame.ons_code == code].set_index("year")
    assert rows.index.max() == 2018  # as_of 2019-12-01 is after the event: dropped
    assert rows.loc[2018, "label"] == 1  # event inside (2018-12-01, 2020-12-01]
    assert rows.loc[2017, "label"] == 1
    assert rows.loc[2016, "label"] == 0  # window ends 2018-12-01, before the event
    healthy = frame[frame.ons_code == "E06000901"]
    assert healthy["label"].sum() == 0
    assert len(healthy) == 10


def test_scorers_never_see_future_labels(sample: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    panel, events = sample
    seen: list[tuple[int, int]] = []

    def spy(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
        test_year = int(test["year"].iloc[0])
        seen.append((int(train["year"].max()), test_year))
        assert (train["label_end"] <= as_of(test_year)).all()
        return test["label"].astype(float) * 100  # oracle: knows the answer for this year

    rep = run_backtest(panel, events, BacktestConfig(k=50, observed_until=OBSERVED), {"o": spy})
    assert seen
    assert all(tr <= te - 2 for tr, te in seen)
    oracle = rep.models["o"]
    assert oracle.recall == 1.0  # k covers everyone, oracle ranks positives first
    assert oracle.true_positives == oracle.positives
    assert rep.eval_years == [2020, 2021, 2022]


def test_skip_reasons(sample: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    panel, events = sample
    rep = run_backtest(panel, events, BacktestConfig(k=5, observed_until=OBSERVED))
    reasons = set(rep.skipped_years.values())
    assert "label window not yet observed" in reasons
    assert "fewer than 3 training years" in reasons
    strict = run_backtest(
        panel, events, BacktestConfig(k=5, min_train_positives=999, observed_until=OBSERVED)
    )
    assert strict.eval_years == []
    assert all(m.lift is None and m.base_rate == 0.0 for m in strict.models.values())
    assert any("not enough training positives for hgb" in r for r in strict.skipped_years.values())
    assert "No year could be evaluated" in render_markdown(strict)


def test_no_positive_years_and_no_events(sample: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    panel, _ = sample
    late = pd.DataFrame([ev("E06000901", date(2030, 1, 1))])
    rep = run_backtest(panel, late, BacktestConfig(observed_until=date(2031, 1, 1)))
    assert "no positives in test year" in set(rep.skipped_years.values())
    none = run_backtest(panel, pd.DataFrame(columns=["ons_code", "event_date", "verification"]))
    assert none.eval_years == []
    assert set(none.skipped_years.values()) == {"label window not yet observed"}


def test_full_backtest_report(sample: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    panel, events = sample
    rep = run_backtest(panel, events, BacktestConfig(k=5, observed_until=OBSERVED))
    assert set(rep.models) == {"rules_v1", "reserves_only", "hgb"}
    for m in rep.models.values():
        assert m.years == rep.eval_years  # every model judged on the same years
        assert 0.0 <= m.precision <= 1.0
        assert 0.0 <= m.recall <= 1.0
        assert len(m.caught) + len(m.missed) == 9
        assert m.median_lead_days is None or m.median_lead_days > 0
        assert 0.0 < m.base_rate < 1.0
        assert m.lift is not None
        assert m.lift == pytest.approx(m.precision / m.base_rate)
    assert rep.watchlist_year == 2025
    # Councils already in distress are never on the watchlist.
    distressed = set(first_events(events))
    for items in rep.watchlist.values():
        assert not {c for c, _ in items} & distressed
    md = render_markdown(rep, {"E06000909": "Somewhere Council"})
    assert "| rules_v1 |" in md
    assert "Base rate:" in md
    assert "Lift vs random" in md
    assert "Watchlist for 2025" in md
    data = json.loads(rep.to_json())
    assert data["config"]["observed_until"] == "2025-03-31"
    assert data["models"]["hgb"]["flags"] == 15


def test_hgb_scorer_handles_unusable_columns(sample: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    panel, events = sample
    frame = build_frame(panel, events, 2)
    train = frame[frame.year <= 2018].copy()
    train["reserves_change_3y"] = float("nan")  # all-NaN column
    train["social_care_share"] = 0.5  # constant column
    scores = make_hgb_scorer(BacktestConfig())(train, frame[frame.year == 2020])
    assert scores is not None
    assert scores.between(0, 100).all()
    assert "reserves_change_3y" in ML_FEATURES


def test_config_validation_and_empty_panel(sample: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        BacktestConfig(horizon=0)
    panel, events = sample
    rep = run_backtest(panel.iloc[:0], events)
    assert rep.eval_years == []
    assert rep.watchlist_year is None


def test_cli_backtest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = ["--db", f"sqlite:///{tmp_path / 'bt.db'}"]
    assert main([*db, "init-db"]) == 0
    assert main([*db, "backtest"]) == 1  # nothing loaded yet
    for step in (
        ["load-councils", str(SAMPLE / "councils.csv")],
        ["ingest", "sample_finance_year", str(SAMPLE / "finance_year.csv")],
        ["load-events", str(SAMPLE / "events.csv")],
    ):
        assert main([*db, *step]) == 0
    md, js = tmp_path / "r" / "bt.md", tmp_path / "r" / "bt.json"
    args = ["backtest", "--k", "5", "--observed-until", "2025-03-31"]
    assert main([*db, *args, "--out", str(md), "--json", str(js)]) == 0
    out = capsys.readouterr().out
    assert "evaluation years: 2020, 2021, 2022" in out
    assert md.read_text().startswith("# Backtest report")
    assert json.loads(js.read_text())["eval_years"] == [2020, 2021, 2022]
    assert main([*db, "backtest"]) == 0  # default observed_until (last event) also runs
