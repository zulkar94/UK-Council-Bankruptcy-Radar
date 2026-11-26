from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from council_radar.domain.codes import CodeCycleError, CodeMap, Succession, tier_from_code
from council_radar.domain.names import match_names, normalise_name
from council_radar.domain.rules import rule_score
from council_radar.domain.signals import INPUT_COLUMNS, compute_signals

NORTHANTS = "E10000021"


def test_split_resolves_with_weights() -> None:
    cm = CodeMap(
        [
            Succession(NORTHANTS, "E06000061", date(2021, 4, 1), 0.45),
            Succession(NORTHANTS, "E06000062", date(2021, 4, 1), 0.55),
        ]
    )
    assert cm.resolve(NORTHANTS, date(2020, 1, 1)) == {NORTHANTS: 1.0}
    assert cm.resolve(NORTHANTS, date(2022, 1, 1)) == {"E06000061": 0.45, "E06000062": 0.55}


def test_chain_and_cycle() -> None:
    cm = CodeMap([Succession("A", "B", date(2019, 4, 1)), Succession("B", "C", date(2020, 4, 1))])
    assert cm.resolve("A", date(2021, 1, 1)) == {"C": 1.0}
    assert cm.resolve("A", date(2019, 6, 1)) == {"B": 1.0}
    loop = CodeMap([Succession("X", "Y", date(2019, 1, 1)), Succession("Y", "X", date(2019, 1, 1))])
    with pytest.raises(CodeCycleError):
        loop.resolve("X", date(2020, 1, 1))


@pytest.mark.parametrize(
    "rows",
    [
        [Succession("A", "B", date(2020, 1, 1), 0.5)],
        [Succession("A", "B", date(2020, 1, 1), 1.5)],
    ],
)
def test_bad_weights_rejected(rows: list[Succession]) -> None:
    with pytest.raises(ValueError, match="weight"):
        CodeMap(rows)


@pytest.mark.parametrize(
    ("code", "tier"),
    [
        ("E06000018", "unitary"),
        ("E07000217", "district"),
        ("E08000025", "metropolitan"),
        ("E09000008", "london_borough"),
        ("E10000021", "county"),
        ("W06000015", "other"),
    ],
)
def test_tier_from_code(code: str, tier: str) -> None:
    assert tier_from_code(code) == tier


def test_name_matching_real_variants() -> None:
    councils = {
        "E06000040": "Windsor and Maidenhead",
        "E08000025": "Birmingham",
        "E06000021": "Stoke-on-Trent",
        "E07000001": "Ashvale",
        "E06000999": "Ashvale",  # deliberate duplicate to force ambiguity
    }
    m = match_names(
        ["Windsor & Maidenhead", "Birmingham City Council", "Stoke-on-Trent", "Ashvale", "Nowhere"],
        councils,
    )
    assert m.matched == {
        "Windsor & Maidenhead": "E06000040",
        "Birmingham City Council": "E08000025",
        "Stoke-on-Trent": "E06000021",
    }
    assert m.ambiguous == {"Ashvale": ["E06000999", "E07000001"]}
    assert m.unmatched == ["Nowhere"]
    assert normalise_name("Royal Borough of Windsor & Maidenhead") == "windsor and maidenhead"


def panel(n_years: int = 5) -> pd.DataFrame:
    rows = []
    for code, tier, reserves, debt in (
        ("E06000901", "unitary", 50.0, 100.0),
        ("E06000902", "unitary", 10.0, 400.0),  # weak
        ("E06000903", "unitary", 30.0, 200.0),
        ("E07000901", "district", 5.0, 50.0),
    ):
        for i, y in enumerate(range(2020, 2020 + n_years)):
            rows.append(
                {
                    "ons_code": code,
                    "year": y,
                    "tier": tier,
                    "net_revenue_expenditure": 100.0,
                    "reserves_unallocated": reserves * 0.3,
                    "reserves_earmarked": reserves * 0.7 - i,
                    "dsg_deficit": 1.0,
                    "external_borrowing": debt,
                    "commercial_property": debt / 4,
                    "interest_cost": debt * 0.03,
                    "core_spending_power": 90.0,
                    "social_care_spend": 0.0 if tier == "district" else 55.0,
                }
            )
    return pd.DataFrame(rows, columns=list(INPUT_COLUMNS))


def test_signals_ratios_and_tier_ranking() -> None:
    s = compute_signals(panel())
    row = s[(s.ons_code == "E06000901") & (s.year == 2020)].iloc[0]
    assert row.reserves_to_nre == pytest.approx(0.5)
    assert row.debt_to_csp == pytest.approx(100 / 90)
    assert np.isnan(row.reserves_change_3y)  # needs 3 prior years
    later = s[(s.ons_code == "E06000901") & (s.year == 2023)].iloc[0]
    assert later.reserves_change_3y == pytest.approx(-0.03)
    weak = s[(s.ons_code == "E06000902") & (s.year == 2024)].iloc[0]
    assert weak.reserves_to_nre_risk_pct == pytest.approx(1.0)  # lowest reserves in tier
    assert weak.debt_to_csp_risk_pct == pytest.approx(1.0)
    strong = s[(s.ons_code == "E06000901") & (s.year == 2024)].iloc[0]
    assert strong.reserves_to_nre_risk_pct == pytest.approx(1 / 3)
    # The lone district is ranked only against itself.
    dist = s[s.ons_code == "E07000901"]
    assert (dist.reserves_to_nre_risk_pct == 1.0).all()


def test_signals_gap_years_and_zero_division() -> None:
    p = panel().query("not (ons_code == 'E06000901' and year == 2021)").copy()
    p.loc[p.ons_code == "E06000903", "core_spending_power"] = 0.0
    s = compute_signals(p)
    # 2024 row for E06000901: shift(3) lands on 2020 (gap year missing) -> must be NaN.
    r = s[(s.ons_code == "E06000901") & (s.year == 2024)].iloc[0]
    assert np.isnan(r.reserves_change_3y)
    assert s.loc[s.ons_code == "E06000903", "debt_to_csp"].isna().all()


def test_signals_missing_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        compute_signals(pd.DataFrame({"ons_code": ["x"]}))


def test_rule_score_orders_and_reports_coverage() -> None:
    sc = rule_score(compute_signals(panel()))
    latest = sc[(sc.year == 2024) & (sc.tier == "unitary")].set_index("ons_code")
    assert latest.score.idxmax() == "E06000902"
    assert latest.score.between(0, 100).all()
    assert (latest.coverage == 1.0).all()
    assert latest.loc["E06000902", "top_drivers"].count(",") == 2
    early = sc[sc.year == 2020]
    assert (early.coverage < 1.0).all()  # 3-year change not yet available


def test_rule_score_validates_weights() -> None:
    s = compute_signals(panel())
    with pytest.raises(ValueError, match="unknown"):
        rule_score(s, {"vibes": 1.0})
    with pytest.raises(ValueError, match="positive"):
        rule_score(s, {"debt_to_csp": 0.0})
