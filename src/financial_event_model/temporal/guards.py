"""Reusable leakage checks for future split and label builders."""

from datetime import datetime
from typing import Iterable


def assert_disjoint_content_hashes(
    train_hashes: set[str],
    test_hashes: set[str],
) -> None:
    overlap = train_hashes & test_hashes
    if overlap:
        raise ValueError(f"duplicate content crosses split boundary: {sorted(overlap)}")


def assert_non_overlapping_outcome_windows(
    train_windows: Iterable[tuple[datetime, datetime]],
    test_windows: Iterable[tuple[datetime, datetime]],
) -> None:
    train = tuple(train_windows)
    test = tuple(test_windows)
    for start, end in (*train, *test):
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("outcome window endpoints must be timezone-aware")
        if end <= start:
            raise ValueError("outcome window end must be after start")
    if any(
        train_start < test_end and test_start < train_end
        for train_start, train_end in train
        for test_start, test_end in test
    ):
        raise ValueError("outcome window overlaps across fold boundary")
