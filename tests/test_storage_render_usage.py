from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.storage.render_usage import add_usage, get_month_seconds, seconds_left

TELEGRAM_ID = 801
AUGUST = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
SEPTEMBER = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def test_untouched_user_has_the_whole_limit(db_path):
    assert get_month_seconds(db_path, TELEGRAM_ID, now=AUGUST) == 0
    assert seconds_left(db_path, TELEGRAM_ID, 300, now=AUGUST) == 300


def test_usage_accumulates_within_the_month(db_path):
    add_usage(db_path, TELEGRAM_ID, 30, 135.0, now=AUGUST)
    add_usage(db_path, TELEGRAM_ID, 30, 135.0, now=AUGUST)

    assert get_month_seconds(db_path, TELEGRAM_ID, now=AUGUST) == 60
    assert seconds_left(db_path, TELEGRAM_ID, 300, now=AUGUST) == 240


def test_a_new_month_starts_from_zero(db_path):
    add_usage(db_path, TELEGRAM_ID, 300, 1350.0, now=AUGUST)

    assert get_month_seconds(db_path, TELEGRAM_ID, now=SEPTEMBER) == 0
    assert seconds_left(db_path, TELEGRAM_ID, 300, now=SEPTEMBER) == 300


def test_usage_is_per_user(db_path):
    add_usage(db_path, 802, 300, 1350.0, now=AUGUST)

    assert get_month_seconds(db_path, TELEGRAM_ID, now=AUGUST) == 0


def test_seconds_left_never_goes_negative(db_path):
    # Провайдер может отрендерить чуть длиннее заказанного; отрицательный
    # остаток превратил бы отказ по лимиту в странное «осталось -4 секунды».
    add_usage(db_path, TELEGRAM_ID, 310, 1400.0, now=AUGUST)

    assert seconds_left(db_path, TELEGRAM_ID, 300, now=AUGUST) == 0
