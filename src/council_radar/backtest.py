"""Walk-forward backtest: does a score flag councils before they hit distress?

Timing rules (the whole point is to avoid leakage):
- Outturn data for financial year Y (ending 31 March Y) is assumed usable from
  1 December Y, the decision date ("as-of") for that row.
- A row is positive if the council's FIRST verified distress event falls in
  (as_of, as_of + horizon years]. Rows on or after a council's first event are
  dropped: spotting a crisis that is already public is not a prediction.
- A model scoring year T trains only on rows whose label window closed by T's
  as-of date, i.e. feature years <= T - horizon.
- A test year is evaluated only if its whole label window is observed.

Every scorer is compared on the same test years and the same councils.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from council_radar.domain.rules import rule_score
from council_radar.domain.signals import SIGNAL_DIRECTION, compute_signals
from finance_ai_core.eval import lead_times, precision_at_k, recall_at_k

AS_OF_MONTH, AS_OF_DAY = 12, 1
RAW_FEATURES = list(SIGNAL_DIRECTION)
PCT_FEATURES = [f"{s}_risk_pct" for s in SIGNAL_DIRECTION]
ML_FEATURES = RAW_FEATURES + PCT_FEATURES


@dataclass(frozen=True)
class BacktestConfig:
    horizon: int = 2
    k: int = 10
    min_train_years: int = 3
    min_train_positives: int = 3
    seed: int = 42
    observed_until: date | None = None  # default: last event date in the data

    def __post_init__(self) -> None:
        if self.horizon < 1 or self.k < 1 or self.min_train_years < 1:
            raise ValueError("horizon, k and min_train_years must be >= 1")


def as_of(year: int) -> date:
    return date(year, AS_OF_MONTH, AS_OF_DAY)


def _add_years(d: date, years: int) -> date:
    return d.replace(year=d.year + years)


def first_events(events: pd.DataFrame) -> dict[str, date]:
    """Earliest verified event date per council (unverified rows are ignored)."""
    ev = events[events["verification"] != "unverified"]
    if ev.empty:
        return {}
    first = ev.groupby("ons_code")["event_date"].min()
    return {str(k): pd.Timestamp(v).date() for k, v in first.items()}


def build_frame(panel: pd.DataFrame, events: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Signals plus as_of, label and label_end per council-year, at-risk rows only."""
    sig = compute_signals(panel)
    firsts = first_events(events)
    sig["as_of"] = sig["year"].map(as_of)
    sig["label_end"] = sig["as_of"].map(lambda d: _add_years(d, horizon))
    sig["first_event"] = sig["ons_code"].map(lambda c: firsts.get(str(c)))
    # Compare row by row: the column mixes dates and None, which pandas won't compare.
    already = [
        fe is not None and fe <= ao for fe, ao in zip(sig["first_event"], sig["as_of"], strict=True)
    ]
    sig = sig.loc[~pd.Series(already, index=sig.index, dtype=bool)].copy()
    sig["label"] = [
        int(fe is not None and fe <= end)
        for fe, end in zip(sig["first_event"], sig["label_end"], strict=True)
    ]
    return sig.reset_index(drop=True)


Scorer = Callable[[pd.DataFrame, pd.DataFrame], pd.Series | None]


def score_rules(_train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    return rule_score(test)["score"]


def score_reserves_only(_train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    """Naive baseline: low usable reserves relative to spending, nothing else."""
    return test["reserves_to_nre_risk_pct"] * 100


def make_hgb_scorer(cfg: BacktestConfig) -> Scorer:
    def score_hgb(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series | None:
        if int(train["label"].sum()) < cfg.min_train_positives:
            return None
        model = HistGradientBoostingClassifier(
            max_depth=3,
            learning_rate=0.1,
            max_iter=200,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=cfg.seed,
        )
        # Early folds can have a feature that is all NaN (e.g. the 3-year trend) or
        # constant; HistGradientBoosting cannot bin those, and they carry no signal.
        cols = [c for c in ML_FEATURES if train[c].nunique(dropna=True) > 1]
        model.fit(train[cols].to_numpy(float), train["label"].to_numpy())
        proba = model.predict_proba(test[cols].to_numpy(float))[:, 1]
        return pd.Series(proba * 100, index=test.index)

    return score_hgb


@dataclass
class ModelResult:
    name: str
    years: list[int] = field(default_factory=list)
    positives: int = 0
    at_risk: int = 0
    true_positives: int = 0
    flags: int = 0
    per_year: list[dict[str, float | int]] = field(default_factory=list)
    caught: dict[str, int] = field(default_factory=dict)
    missed: list[str] = field(default_factory=list)
    flagged: dict[int, list[str]] = field(default_factory=dict)  # year -> top-k codes

    @property
    def precision(self) -> float:
        return self.true_positives / self.flags if self.flags else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.positives if self.positives else 0.0

    @property
    def base_rate(self) -> float:
        """Share of at-risk councils that had an event: what random picking would score."""
        return self.positives / self.at_risk if self.at_risk else 0.0

    @property
    def lift(self) -> float | None:
        return self.precision / self.base_rate if self.base_rate else None

    @property
    def median_lead_days(self) -> float | None:
        return float(np.median(list(self.caught.values()))) if self.caught else None


@dataclass
class BacktestReport:
    config: BacktestConfig
    eval_years: list[int]
    skipped_years: dict[int, str]
    models: dict[str, ModelResult]
    watchlist_year: int | None
    watchlist: dict[str, list[tuple[str, float]]]

    def to_json(self) -> str:
        cfg = asdict(self.config)
        cfg["observed_until"] = str(cfg["observed_until"]) if cfg["observed_until"] else None
        return json.dumps(
            {
                "config": cfg,
                "eval_years": self.eval_years,
                "skipped_years": {str(k): v for k, v in self.skipped_years.items()},
                "models": {
                    n: {
                        "precision_at_k": round(m.precision, 3),
                        "recall_at_k": round(m.recall, 3),
                        "positives": m.positives,
                        "at_risk": m.at_risk,
                        "base_rate": round(m.base_rate, 4),
                        "lift": round(m.lift, 2) if m.lift is not None else None,
                        "true_positives": m.true_positives,
                        "flags": m.flags,
                        "events_caught": len(m.caught),
                        "events_missed": len(m.missed),
                        "median_lead_days": m.median_lead_days,
                        "per_year": m.per_year,
                        "caught": m.caught,
                        "missed": m.missed,
                    }
                    for n, m in self.models.items()
                },
                "watchlist_year": self.watchlist_year,
                "watchlist": self.watchlist,
            },
            indent=2,
        )


def run_backtest(
    panel: pd.DataFrame,
    events: pd.DataFrame,
    cfg: BacktestConfig | None = None,
    scorers: Mapping[str, Scorer] | None = None,
) -> BacktestReport:
    cfg = cfg or BacktestConfig()
    frame = build_frame(panel, events, cfg.horizon)
    scorers = scorers or {
        "rules_v1": score_rules,
        "reserves_only": score_reserves_only,
        "hgb": make_hgb_scorer(cfg),
    }
    firsts = first_events(events)
    observed = cfg.observed_until or (max(firsts.values()) if firsts else None)
    years = sorted(frame["year"].unique().tolist())

    skipped: dict[int, str] = {}
    scored: dict[int, dict[str, pd.Series]] = {}
    for y in years:
        test = frame[frame["year"] == y]
        train = frame[frame["year"] <= y - cfg.horizon]
        if observed is None or _add_years(as_of(y), cfg.horizon) > observed:
            skipped[y] = "label window not yet observed"
            continue
        if train["year"].nunique() < cfg.min_train_years:
            skipped[y] = f"fewer than {cfg.min_train_years} training years"
            continue
        if int(test["label"].sum()) == 0:
            skipped[y] = "no positives in test year"
            continue
        out = {name: fn(train, test) for name, fn in scorers.items()}
        missing = [n for n, s in out.items() if s is None]
        if missing:
            skipped[y] = f"not enough training positives for {', '.join(missing)}"
            continue
        scored[y] = {n: s for n, s in out.items() if s is not None}

    results = {n: ModelResult(name=n) for n in scorers}
    flag_dates: dict[str, dict[str, list[date]]] = {n: {} for n in scorers}
    for y, by_model in scored.items():
        test = frame[frame["year"] == y]
        positives = set(test.loc[test["label"] == 1, "ons_code"])
        for name, s in by_model.items():
            scores = dict(zip(test["ons_code"], s.fillna(-1.0), strict=True))
            k = min(cfg.k, len(scores))
            top = sorted(scores, key=lambda c: (-scores[c], c))[:k]
            tp = len(set(top) & positives)
            r = results[name]
            r.years.append(y)
            r.positives += len(positives)
            r.at_risk += len(scores)
            r.true_positives += tp
            r.flags += k
            r.flagged[y] = top
            r.per_year.append(
                {
                    "year": y,
                    "at_risk": len(scores),
                    "flags": k,
                    "true_positives": tp,
                    "positives": len(positives),
                    "precision_at_k": round(precision_at_k(scores, positives, k), 3),
                    "recall_at_k": round(recall_at_k(scores, positives, k), 3),
                }
            )
            for c in top:
                flag_dates[name].setdefault(c, []).append(as_of(y))

    eval_years = sorted(scored)
    if eval_years:
        window_start = as_of(eval_years[0])
        window_end = _add_years(as_of(eval_years[-1]), cfg.horizon)
        target = {c: d for c, d in firsts.items() if window_start < d <= window_end}
        for name, r in results.items():
            lt = lead_times(flag_dates[name], target, min_lead_days=1)
            r.caught, r.missed = lt.caught, lt.missed

    watch_year, watchlist = _watchlist(frame, scorers, cfg)
    return BacktestReport(cfg, eval_years, skipped, results, watch_year, watchlist)


def _watchlist(
    frame: pd.DataFrame, scorers: Mapping[str, Scorer], cfg: BacktestConfig
) -> tuple[int | None, dict[str, list[tuple[str, float]]]]:
    """Top-k at-risk councils in the latest year, by each model (outcome not yet known)."""
    if frame.empty:
        return None, {}
    y = int(frame["year"].max())
    test = frame[frame["year"] == y]
    train = frame[frame["label_end"] <= as_of(y)]
    out: dict[str, list[tuple[str, float]]] = {}
    for name, fn in scorers.items():
        s = fn(train, test)
        if s is None:
            continue
        ranked = sorted(
            zip(test["ons_code"], s.fillna(-1.0), strict=True), key=lambda t: (-t[1], t[0])
        )
        out[name] = [(c, round(float(v), 1)) for c, v in ranked[: cfg.k]]
    return y, out


def render_markdown(rep: BacktestReport, names: Mapping[str, str] | None = None) -> str:
    names = names or {}
    cfg = rep.config
    lines = [
        "# Backtest report",
        "",
        f"Horizon {cfg.horizon} years, top-{cfg.k} flagged per year, "
        f"evaluation years: {', '.join(map(str, rep.eval_years)) or 'none'}.",
        "",
    ]
    if not rep.eval_years:
        lines += ["No year could be evaluated. Reasons:", ""]
    if rep.models and rep.eval_years:
        lines += [
            "| Model | Precision@k | Lift vs random | Recall@k | Events caught "
            "| Median lead (days) |",
            "|---|---|---|---|---|---|",
        ]
        for m in rep.models.values():
            lead = f"{m.median_lead_days:.0f}" if m.median_lead_days is not None else "-"
            lift = f"{m.lift:.1f}x" if m.lift is not None else "-"
            caught = f"{len(m.caught)} of {len(m.caught) + len(m.missed)}"
            lines.append(
                f"| {m.name} | {m.precision:.2f} | {lift} | {m.recall:.2f} | {caught} | {lead} |"
            )
        first = next(iter(rep.models.values()))
        lines += [
            "",
            f"Base rate: {first.base_rate:.1%} of at-risk council-years had an event within the "
            "horizon, so random picking scores that precision and a lift of 1.0x.",
            "",
        ]
    if rep.skipped_years:
        lines += ["Skipped years:", ""]
        lines += [f"- {y}: {why}" for y, why in sorted(rep.skipped_years.items())]
        lines.append("")
    if rep.watchlist_year is not None and rep.watchlist:
        lines += [f"## Watchlist for {rep.watchlist_year} (outcome not yet known)", ""]
        for model, items in rep.watchlist.items():
            shown = ", ".join(f"{names.get(c, c)} ({v})" for c, v in items)
            lines.append(f"- **{model}**: {shown}")
        lines.append("")
    lines += [
        "Precision@k is the share of flagged councils that went on to an event within the",
        "horizon. Recall@k is the share of those events that were flagged. Lead time counts",
        "from the decision date of the earliest flag to the event.",
    ]
    return "\n".join(lines) + "\n"
