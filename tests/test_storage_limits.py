from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.limits import (
    get_daily_count,
    get_monthly_count,
    increment_usage,
    is_within_limit,
)

DAY_1 = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
DAY_1_LATER = datetime(2026, 7, 17, 23, 59, tzinfo=timezone.utc)
DAY_2 = datetime(2026, 7, 18, 0, 5, tzinfo=timezone.utc)
NEXT_MONTH = datetime(2026, 8, 1, 0, 5, tzinfo=timezone.utc)


def test_new_user_has_zero_counts(db_path):
    assert get_daily_count(db_path, 111, now=DAY_1) == 0
    assert get_monthly_count(db_path, 111, now=DAY_1) == 0


def test_increment_usage_increases_daily_and_monthly_counts(db_path):
    increment_usage(db_path, 111, now=DAY_1)

    assert get_daily_count(db_path, 111, now=DAY_1) == 1
    assert get_monthly_count(db_path, 111, now=DAY_1) == 1


def test_increment_usage_accumulates_within_same_day(db_path):
    increment_usage(db_path, 111, now=DAY_1)
    increment_usage(db_path, 111, now=DAY_1_LATER)

    assert get_daily_count(db_path, 111, now=DAY_1) == 2
    assert get_monthly_count(db_path, 111, now=DAY_1) == 2


def test_daily_count_resets_on_new_day(db_path):
    increment_usage(db_path, 111, now=DAY_1)
    increment_usage(db_path, 111, now=DAY_2)

    assert get_daily_count(db_path, 111, now=DAY_2) == 1


def test_monthly_count_accumulates_across_days_in_same_month(db_path):
    increment_usage(db_path, 111, now=DAY_1)
    increment_usage(db_path, 111, now=DAY_2)

    assert get_monthly_count(db_path, 111, now=DAY_2) == 2


def test_monthly_count_resets_on_new_month(db_path):
    increment_usage(db_path, 111, now=DAY_1)
    increment_usage(db_path, 111, now=NEXT_MONTH)

    assert get_monthly_count(db_path, 111, now=NEXT_MONTH) == 1


def test_is_within_limit_true_when_under_both_limits(db_path):
    increment_usage(db_path, 111, now=DAY_1)

    assert is_within_limit(db_path, 111, daily_limit=5, monthly_limit=50, now=DAY_1) is True


def test_is_within_limit_false_when_daily_limit_reached(db_path):
    for _ in range(3):
        increment_usage(db_path, 111, now=DAY_1)

    assert is_within_limit(db_path, 111, daily_limit=3, monthly_limit=50, now=DAY_1) is False


def test_is_within_limit_false_when_monthly_limit_reached(db_path):
    increment_usage(db_path, 111, now=DAY_1)
    increment_usage(db_path, 111, now=DAY_2)

    assert is_within_limit(db_path, 111, daily_limit=50, monthly_limit=2, now=DAY_2) is False


def test_is_within_limit_true_again_after_daily_rollover(db_path):
    for _ in range(3):
        increment_usage(db_path, 111, now=DAY_1)

    assert is_within_limit(db_path, 111, daily_limit=3, monthly_limit=50, now=DAY_2) is True


def test_usage_is_scoped_per_user(db_path):
    increment_usage(db_path, 111, now=DAY_1)

    assert get_daily_count(db_path, 222, now=DAY_1) == 0
