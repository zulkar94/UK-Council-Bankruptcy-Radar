"""Financial resilience signals per council-year, ranked within tier.

Input frame columns (all money in GBP):
    ons_code, year, tier,
    net_revenue_expenditure, reserves_unallocated, reserves_earmarked,
    dsg_deficit, external_borrowing, commercial_property, interest_cost,
    core_spending_power, social_care_spend

Districts do not run social care and counties do not collect most council tax,
so every percentile is computed within (tier, year). Ranking a district against a
county would make the score meaningless.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

INPUT_COLUMNS: tuple[str, ...] = (
    "ons_code",
    "year",
    "tier",
    "net_revenue_expenditure",
    "reserves_unallocated",
    "reserves_earmarked",
    "dsg_deficit",
    "external_borrowing",
    "commercial_property",
    "interest_cost",
    "core_spending_power",
    "social_care_spend",
)

TREND_YEARS = 3

# signal name -> True if a higher value means more risk
SIGNAL_DIRECTION: dict[str, bool] = {
    "reserves_to_nre": False,
    "reserves_change_3y": False,
    "debt_to_csp": True,
    "commercial_to_csp": True,
    "interest_to_nre": True,
    "dsg_deficit_to_reserves": True,
    "social_care_share": True,
}


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    out = num.astype(float) / den.astype(float).where(den != 0)
    return out.replace([np.inf, -np.inf], np.nan)


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(INPUT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    d = df.sort_values(["ons_code", "year"]).reset_index(drop=True).copy()
    usable = d["reserves_unallocated"] + d["reserves_earmarked"]
    d["reserves_to_nre"] = _safe_div(usable, d["net_revenue_expenditure"])
    prior = d.groupby("ons_code")["reserves_to_nre"].shift(TREND_YEARS)
    year_gap = d["year"] - d.groupby("ons_code")["year"].shift(TREND_YEARS)
    # Only a true 3-year change counts; gaps in the series give NaN, not a wrong delta.
    d["reserves_change_3y"] = (d["reserves_to_nre"] - prior).where(year_gap == TREND_YEARS)
    # Core spending power is the preferred denominator; where it is missing (it is not in
    # the outturn file) fall back to net revenue expenditure so debt signals still work.
    denom = d["core_spending_power"].where(
        d["core_spending_power"].notna(), d["net_revenue_expenditure"]
    )
    d["debt_to_csp"] = _safe_div(d["external_borrowing"], denom)
    d["commercial_to_csp"] = _safe_div(d["commercial_property"], denom)
    d["interest_to_nre"] = _safe_div(d["interest_cost"], d["net_revenue_expenditure"])
    d["dsg_deficit_to_reserves"] = _safe_div(d["dsg_deficit"], usable)
    d["social_care_share"] = _safe_div(d["social_care_spend"], d["net_revenue_expenditure"])

    for sig, higher_is_risk in SIGNAL_DIRECTION.items():
        pct = d.groupby(["tier", "year"])[sig].rank(pct=True, method="average")
        d[f"{sig}_risk_pct"] = pct if higher_is_risk else 1.0 - pct + _tie_fix(d, sig)
    return d


def _tie_fix(d: pd.DataFrame, sig: str) -> pd.Series:
    """Make inverted percentiles land in (0, 1] like the direct ones.

    rank(pct=True) gives values in (0, 1]; 1 - pct gives [0, 1). Adding 1/n shifts
    the inverted rank back so the lowest-risk council scores 1/n, not 0.
    """
    n = d.groupby(["tier", "year"])[sig].transform("count").astype(float)
    return (1.0 / n.where(n > 0)).fillna(0.0)
