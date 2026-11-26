"""ONS code succession: follow merges and splits from reorganisations.

Example: Northamptonshire County Council (E10000021) was replaced on 1 April 2021
by North Northamptonshire (E06000061) and West Northamptonshire (E06000062).
A split carries a weight so values can be apportioned (e.g. by population share).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

WEIGHT_TOLERANCE = 1e-6

_TIER_BY_PREFIX = {
    "E06": "unitary",
    "E07": "district",
    "E08": "metropolitan",
    "E09": "london_borough",
    "E10": "county",
}


def tier_from_code(ons_code: str) -> str:
    """Infer council tier from the ONS entity code prefix (England only)."""
    return _TIER_BY_PREFIX.get(ons_code.strip().upper()[:3], "other")


@dataclass(frozen=True)
class Succession:
    old_code: str
    new_code: str
    effective: date
    weight: float = 1.0


class CodeCycleError(ValueError):
    """Raised when succession rows form a loop."""


class CodeMap:
    def __init__(self, rows: Iterable[Succession]) -> None:
        self._next: dict[str, list[Succession]] = defaultdict(list)
        for r in rows:
            if not 0 < r.weight <= 1:
                raise ValueError(f"weight out of range for {r.old_code}->{r.new_code}")
            self._next[r.old_code].append(r)
        for code, succs in self._next.items():
            total = sum(s.weight for s in succs)
            if abs(total - 1.0) > WEIGHT_TOLERANCE:
                raise ValueError(f"weights for {code} sum to {total:.3f}, expected 1.0")

    def resolve(self, code: str, on: date) -> dict[str, float]:
        """Return the code(s) in force on ``on`` that ``code`` maps to, with weights."""
        out: dict[str, float] = {}
        self._walk(code, on, 1.0, out, frozenset())
        return out

    def _walk(
        self, code: str, on: date, w: float, out: dict[str, float], seen: frozenset[str]
    ) -> None:
        if code in seen:
            raise CodeCycleError(f"cycle at {code}")
        active = [s for s in self._next.get(code, []) if s.effective <= on]
        if not active:
            out[code] = out.get(code, 0.0) + w
            return
        for s in active:
            self._walk(s.new_code, on, w * s.weight, out, seen | {code})
