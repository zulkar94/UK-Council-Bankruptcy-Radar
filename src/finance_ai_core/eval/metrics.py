"""Ranking and early-warning metrics. Pure functions, no framework imports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from statistics import mean, median


def _top_k(scores: Mapping[str, float], k: int) -> list[str]:
    if k <= 0:
        raise ValueError("k must be positive")
    # Sort by score desc, then id asc so ties are deterministic.
    return [eid for eid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def precision_at_k(scores: Mapping[str, float], positives: set[str], k: int) -> float:
    """Share of the top-k ranked entities that are positives."""
    top = _top_k(scores, k)
    if not top:
        return 0.0
    return sum(1 for eid in top if eid in positives) / len(top)


def recall_at_k(scores: Mapping[str, float], positives: set[str], k: int) -> float:
    """Share of positives (that were scored) found in the top-k."""
    scored_pos = positives & set(scores)
    if not scored_pos:
        return 0.0
    top = set(_top_k(scores, k))
    return len(top & scored_pos) / len(scored_pos)


@dataclass(frozen=True)
class LeadTimeReport:
    """How far ahead of each event the first flag was raised."""

    caught: dict[str, int] = field(default_factory=dict)  # entity -> lead days
    missed: list[str] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        total = len(self.caught) + len(self.missed)
        return len(self.caught) / total if total else 0.0

    @property
    def mean_days(self) -> float | None:
        return mean(self.caught.values()) if self.caught else None

    @property
    def median_days(self) -> float | None:
        return median(self.caught.values()) if self.caught else None


def lead_times(
    flags: Mapping[str, list[date]],
    events: Mapping[str, date],
    *,
    min_lead_days: int = 0,
) -> LeadTimeReport:
    """For each event, find the earliest flag at least ``min_lead_days`` before it.

    Flags raised after the event (or inside the minimum lead window) do not count,
    which stops a model getting credit for spotting a failure already in the news.
    """
    caught: dict[str, int] = {}
    missed: list[str] = []
    for entity, event_day in sorted(events.items()):
        valid = [
            (event_day - f).days
            for f in flags.get(entity, [])
            if (event_day - f).days >= min_lead_days
        ]
        if valid:
            caught[entity] = max(valid)
        else:
            missed.append(entity)
    return LeadTimeReport(caught=caught, missed=missed)
