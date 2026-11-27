from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, func, select

from council_radar.cli import main
from council_radar.db import repo
from council_radar.db.models import Council, Event, FinanceYear, RiskScore
from finance_ai_core.db import make_engine, session_scope

from ..conftest import COUNCILS, EVENTS, FINANCE_ROWS, REFERENCE, SAMPLE


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(SAMPLE / name, dtype=str, keep_default_na=False)


def test_financial_year_of() -> None:
    assert repo.financial_year_of(date(2023, 9, 5)) == 2024
    assert repo.financial_year_of(date(2024, 2, 1)) == 2024


def test_load_councils_infers_tier_and_rejects_bad(engine: Engine) -> None:
    with session_scope(engine) as s:
        assert repo.load_councils(s, _csv("councils.csv")) == COUNCILS
        assert repo.load_councils(s, pd.DataFrame({"ons_code": ["E10000999"], "name": ["X"]})) == 1
    with session_scope(engine) as s:
        assert s.get(Council, "E10000999").tier == "county"
        assert s.get(Council, "E09000901").tier == "london_borough"
    with pytest.raises(ValueError, match="unknown tiers"), session_scope(engine) as s:
        repo.load_councils(s, pd.DataFrame({"ons_code": ["E1"], "name": ["X"], "tier": ["moon"]}))


def test_codemap_validates_before_write(engine: Engine) -> None:
    bad = pd.DataFrame(
        {"old_code": ["A"], "new_code": ["B"], "effective": ["2021-04-01"], "weight": ["0.4"]}
    )
    with pytest.raises(ValueError, match="sum"), session_scope(engine) as s:
        repo.load_codemap(s, bad)
    with session_scope(engine) as s:
        assert repo.load_codemap(s, _csv("code_succession.csv")) == 2


def test_finance_upsert_is_idempotent_and_partial(engine: Engine) -> None:
    with session_scope(engine) as s:
        repo.load_councils(s, _csv("councils.csv"))
        df = pd.DataFrame(
            {
                "ons_code": ["E06000901", "E06000999"],
                "year": [2024, 2024],
                "net_revenue_expenditure": [1.0, 2.0],
            }
        )
        res = repo.load_finance(s, df, "a")
        assert res.written == 1
        assert res.unknown_codes == ["E06000999"]
        # A second source adds a different column without wiping the first.
        repo.load_finance(
            s, pd.DataFrame({"ons_code": ["E06000901"], "year": [2024], "dsg_deficit": [9.0]}), "b"
        )
        repo.load_finance(s, df.iloc[:1], "a")
    with session_scope(engine) as s:
        row = s.scalars(select(FinanceYear)).one()
        assert (row.net_revenue_expenditure, row.dsg_deficit) == (1.0, 9.0)


def test_events_keep_earliest_date_latest_amount(engine: Engine) -> None:
    with session_scope(engine) as s:
        repo.load_councils(
            s,
            pd.DataFrame({"ons_code": ["E06000034", "E06000039"], "name": ["Thurrock", "Slough"]}),
        )
        m = repo.load_events(
            s, pd.read_csv(REFERENCE / "distress_events.csv", dtype=str, keep_default_na=False)
        )
        assert set(m.matched.values()) == {"E06000034", "E06000039"}
        assert "Croydon" in m.unmatched
    with session_scope(engine) as s:
        thurrock_2026 = s.scalars(
            select(Event).filter_by(ons_code="E06000034", event_type="efs", financial_year=2026)
        ).one()
        assert thurrock_2026.event_date == date(2025, 2, 20)  # first decision
        assert thurrock_2026.amount_gbp == pytest.approx(62.11e6)  # latest amount
        s114 = s.scalars(select(Event).filter_by(ons_code="E06000039", event_type="s114")).one()
        assert s114.financial_year == 2022
        ev = repo.events_frame(s)
        assert set(ev.verification) <= {"primary", "secondary"}
        assert len(repo.events_frame(s, include_unverified=True)) == len(ev)


def test_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = ["--db", f"sqlite:///{tmp_path / 'cli.db'}"]
    out_csv = tmp_path / "scores.csv"
    steps = [
        ["init-db"],
        ["load-councils", str(SAMPLE / "councils.csv")],
        ["load-codemap", str(SAMPLE / "code_succession.csv")],
        ["ingest", "sample_finance_year", str(SAMPLE / "finance_year.csv")],
        ["load-events", str(SAMPLE / "events.csv")],
        ["load-events", str(SAMPLE / "events.csv")],  # idempotent re-run
        ["score", "--out", str(out_csv), "--top", "4"],
        ["inspect", str(SAMPLE / "finance_year.csv")],
    ]
    for step in steps:
        assert main([*db, *step]) == 0, step
    out = capsys.readouterr().out
    assert f"matched: {EVENTS} ambiguous: 0 unmatched: 0" in out
    assert "Net revenue expenditure (£000)" in out
    scores = pd.read_csv(out_csv)
    assert len(scores) == FINANCE_ROWS
    latest = scores[scores.year == 2025].set_index("ons_code").score
    # Councils that drifted early are still stressed in 2025 and should sit above the median.
    assert (latest[["E06000903", "E09000902", "E08000904", "E07000906"]] > latest.median()).all()
    eng = make_engine(db[1])
    with session_scope(eng) as s:
        assert s.scalar(select(func.count()).select_from(Event)) == EVENTS
        assert s.scalar(select(func.count()).select_from(RiskScore)) == FINANCE_ROWS
    eng.dispose()


def test_cli_ingest_rejects_bad_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = ["--db", f"sqlite:///{tmp_path / 'bad.db'}"]
    main([*db, "init-db"])
    main([*db, "load-councils", str(SAMPLE / "councils.csv")])
    bad = tmp_path / "bad.csv"
    src = pd.read_csv(SAMPLE / "finance_year.csv", dtype=str)
    src.loc[0, "ONS code"] = "NOTACODE"
    src.loc[1, "ONS code"] = "E06000999"  # valid format, not in dim_council
    src.to_csv(bad, index=False)
    assert main([*db, "ingest", "sample_finance_year", str(bad)]) == 2
    spec = Path(__file__).resolve().parents[2] / (
        "src/council_radar/ingest/column_maps/sample_finance_year.toml"
    )
    assert main([*db, "ingest", str(spec), str(bad), "--force"]) == 0
    out = capsys.readouterr().out
    assert "rejected codes: ['NOTACODE']" in out
    assert "not in dim_council (skipped): ['E06000999']" in out


def test_cli_score_without_data(tmp_path: Path) -> None:
    db = ["--db", f"sqlite:///{tmp_path / 'empty.db'}"]
    main([*db, "init-db"])
    assert main([*db, "score"]) == 1


def test_cli_reports_unmatched_and_ambiguous(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = ["--db", f"sqlite:///{tmp_path / 'm.db'}"]
    councils = tmp_path / "c.csv"
    pd.DataFrame({"ons_code": ["E06000901", "E07000901"], "name": ["Twin", "Twin Borough"]}).to_csv(
        councils, index=False
    )
    events = tmp_path / "e.csv"
    pd.DataFrame(
        {
            "council_name": ["Twin", "Ghost"],
            "event_type": ["s114", "s114"],
            "event_date": ["2023-01-01", "2023-01-01"],
            "financial_year": ["", ""],
            "amount_gbp_m": ["", ""],
            "verification": ["primary", "primary"],
            "source_url": ["", ""],
        }
    ).to_csv(events, index=False)
    for step in (["init-db"], ["load-councils", str(councils)], ["load-events", str(events)]):
        assert main([*db, *step]) == 0
    out = capsys.readouterr().out
    assert "unmatched: Ghost" in out
    assert "ambiguous: Twin -> ['E06000901', 'E07000901']" in out


def test_cli_real_layout_pipeline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "ro_layout_sample.csv"
    db = ["--db", f"sqlite:///{tmp_path / 'ro.db'}"]
    councils = tmp_path / "councils.csv"
    assert main([*db, "init-db"]) == 0
    assert main(["extract-councils", "ro_multi_year", str(fixture), "--out", str(councils)]) == 0
    assert main([*db, "load-councils", str(councils)]) == 0
    assert main([*db, "ingest", "ro_multi_year", str(fixture)]) == 0
    out = capsys.readouterr().out
    assert "councils written: 3" in out
    assert "rows written: 4" in out


def test_events_pinned_by_code(engine: Engine) -> None:
    with session_scope(engine) as s:
        repo.load_councils(
            s,
            pd.DataFrame(
                {
                    "ons_code": ["E06000066", "E10000027", "E06000035"],
                    "name": ["Somerset", "Somerset CC", "Medway Towns UA"],
                }
            ),
        )
        m = repo.load_events(
            s, pd.read_csv(REFERENCE / "distress_events.csv", dtype=str, keep_default_na=False)
        )
        assert m.matched["Somerset"] == "E06000066"
        assert m.matched["Medway"] == "E06000035"
        assert "Somerset" not in m.ambiguous
