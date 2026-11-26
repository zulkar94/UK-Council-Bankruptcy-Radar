"""Score extractions against a hand-labelled gold set, field by field."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from finance_ai_core.extraction.schema import ExtractedField


@dataclass(frozen=True)
class FieldScore:
    field: str
    true_pos: int
    false_pos: int
    false_neg: int
    true_neg: int

    @property
    def precision(self) -> float:
        d = self.true_pos + self.false_pos
        return self.true_pos / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.true_pos + self.false_neg
        return self.true_pos / d if d else 0.0


def _match(pred: Any, gold: Any, rel_tol: float) -> bool:
    if isinstance(pred, bool) or isinstance(gold, bool):
        # Strict: True must not match 1, a classic silent pass in Python.
        return isinstance(pred, bool) and isinstance(gold, bool) and pred == gold
    if isinstance(pred, int | float) and isinstance(gold, int | float):
        if gold == 0:
            return pred == 0
        return abs(pred - gold) / abs(gold) <= rel_tol
    if isinstance(pred, str) and isinstance(gold, str):
        return pred.strip().casefold() == gold.strip().casefold()
    return bool(pred == gold)


def score_extractions(
    preds: Sequence[BaseModel],
    golds: Sequence[Mapping[str, Any]],
    *,
    rel_tol: float = 0.01,
) -> dict[str, FieldScore]:
    """Compare predicted models with gold dicts (field -> value or None).

    A wrong non-null value counts as both a false positive and a false negative.
    """
    if len(preds) != len(golds):
        raise ValueError("preds and golds must be the same length")
    counts: dict[str, list[int]] = {}
    for pred, gold in zip(preds, golds, strict=True):
        for name in type(pred).model_fields:
            fld = getattr(pred, name)
            if not isinstance(fld, ExtractedField):
                continue
            c = counts.setdefault(name, [0, 0, 0, 0])
            p, g = fld.value, gold.get(name)
            if p is None and g is None:
                c[3] += 1
            elif p is None:
                c[2] += 1
            elif g is None:
                c[1] += 1
            elif _match(p, g, rel_tol):
                c[0] += 1
            else:
                c[1] += 1
                c[2] += 1
    return {k: FieldScore(k, *v) for k, v in counts.items()}
