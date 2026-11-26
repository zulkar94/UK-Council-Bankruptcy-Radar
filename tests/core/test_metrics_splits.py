from __future__ import annotations

from datetime import date

import pytest

from finance_ai_core.eval import lead_times, precision_at_k, recall_at_k, walk_forward

SCORES = {"a": 0.9, "b": 0.8, "c": 0.8, "d": 0.1}


def test_precision_recall_at_k() -> None:
    assert precision_at_k(SCORES, {"a", "c"}, 2) == 0.5  # tie b/c broken by id -> a, b
    assert recall_at_k(SCORES, {"a", "c"}, 3) == 1.0
    assert recall_at_k(SCORES, {"zz"}, 2) == 0.0  # positive never scored
    assert precision_at_k({}, {"a"}, 3) == 0.0


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        precision_at_k(SCORES, set(), 0)


def test_lead_times_ignores_late_flags() -> None:
    events = {"a": date(2023, 9, 5), "b": date(2023, 6, 7), "c": date(2022, 12, 19)}
    flags = {
        "a": [date(2021, 9, 5), date(2023, 10, 1)],  # second flag is after the event
        "b": [date(2023, 6, 1)],  # inside 30-day minimum window
    }
    rep = lead_times(flags, events, min_lead_days=30)
    assert rep.caught == {"a": 730}
    assert rep.missed == ["b", "c"]
    assert rep.hit_rate == pytest.approx(1 / 3)
    assert rep.mean_days == 730
    assert rep.median_days == 730


def test_lead_times_empty() -> None:
    rep = lead_times({}, {})
    assert rep.hit_rate == 0.0
    assert rep.mean_days is None
    assert rep.median_days is None


def test_walk_forward_gap_prevents_leakage() -> None:
    splits = list(walk_forward([2018, 2019, 2020, 2021, 2022, 2022], min_train=2, gap=1))
    assert splits == [([2018, 2019], 2021), ([2018, 2019, 2020], 2022)]
    for train, test in splits:
        assert max(train) < test - 1


@pytest.mark.parametrize(("kw", "msg"), [({"min_train": 0}, "min_train"), ({"gap": -1}, "gap")])
def test_walk_forward_validates(kw: dict[str, int], msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        list(walk_forward([2020, 2021], **kw))
