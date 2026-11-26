"""Leakage-safe walk-forward splits over financial years."""

from __future__ import annotations

from collections.abc import Iterator, Sequence


def walk_forward(
    years: Sequence[int],
    *,
    min_train: int = 3,
    gap: int = 1,
) -> Iterator[tuple[list[int], int]]:
    """Yield (train_years, test_year) with an expanding window.

    ``gap`` leaves years out between training and test. Council outturn data is
    published many months after year end, so a gap of 1 mirrors what was
    actually knowable at decision time.
    """
    if min_train < 1:
        raise ValueError("min_train must be >= 1")
    if gap < 0:
        raise ValueError("gap must be >= 0")
    ordered = sorted(set(years))
    for i in range(min_train + gap, len(ordered)):
        train = ordered[: i - gap]
        if len(train) >= min_train:
            yield train, ordered[i]
