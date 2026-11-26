"""Transparent baseline risk score. The ML model must beat this to earn its place.

Weights are stated assumptions, set before looking at outcomes, not fitted. Fitting
them on seven Section 114 events would be overfitting with extra steps.
"""

from __future__ import annotations

import pandas as pd

from council_radar.domain.signals import SIGNAL_DIRECTION

DEFAULT_WEIGHTS: dict[str, float] = {
    "reserves_to_nre": 0.25,
    "reserves_change_3y": 0.15,
    "debt_to_csp": 0.15,
    "commercial_to_csp": 0.15,
    "interest_to_nre": 0.10,
    "dsg_deficit_to_reserves": 0.10,
    "social_care_share": 0.10,
}

TOP_DRIVERS = 3


def rule_score(signals: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Return ons_code, year, tier, score (0-100), coverage, top_drivers.

    Missing signals are skipped and the remaining weights renormalised. ``coverage``
    is the share of total weight actually available, so thin data is visible.
    """
    w = weights or DEFAULT_WEIGHTS
    unknown = set(w) - set(SIGNAL_DIRECTION)
    if unknown:
        raise ValueError(f"unknown signals in weights: {sorted(unknown)}")
    total_w = sum(w.values())
    if total_w <= 0:
        raise ValueError("weights must sum to a positive value")

    cols = {s: f"{s}_risk_pct" for s in w}
    pcts = signals[list(cols.values())].rename(columns={v: k for k, v in cols.items()})
    wser = pd.Series(w, dtype=float)
    avail = pcts.notna().mul(wser, axis=1)
    contrib = pcts.fillna(0.0).mul(wser, axis=1)
    avail_sum = avail.sum(axis=1)
    score = (contrib.sum(axis=1) / avail_sum.where(avail_sum > 0)) * 100

    def drivers(row: pd.Series) -> str:
        ranked = row.dropna().sort_values(ascending=False)
        return ",".join(ranked.index[:TOP_DRIVERS])

    out = signals[["ons_code", "year", "tier"]].copy()
    out["score"] = score.round(2)
    out["coverage"] = (avail_sum / total_w).round(3)
    out["top_drivers"] = contrib.where(pcts.notna()).apply(drivers, axis=1)
    return out
