from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.storage.costs import (
    get_monthly_cost_by_operation,
    get_monthly_cost_by_user,
    get_monthly_total,
    record_cost,
)

DAY_1 = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
DAY_2 = datetime(2026, 7, 18, 0, 5, tzinfo=timezone.utc)
NEXT_MONTH = datetime(2026, 8, 1, 0, 5, tzinfo=timezone.utc)


def test_empty_ledger_totals_zero(db_path):
    assert get_monthly_total(db_path, now=DAY_1) == 0
    assert get_monthly_cost_by_user(db_path, now=DAY_1) == []


def test_recorded_costs_sum_into_the_monthly_total(db_path):
    record_cost(db_path, 111, "generate_image", "img-flux/flux-2-klein-4b", 3.90, now=DAY_1)
    record_cost(db_path, 111, "transcribe", "stt-openai/gpt-4o-mini-transcribe", 0.96, now=DAY_2)

    assert get_monthly_total(db_path, now=DAY_2) == pytest.approx(4.86)


def test_monthly_total_excludes_other_months(db_path):
    record_cost(db_path, 111, "generate_image", "m", 3.90, now=DAY_1)
    record_cost(db_path, 111, "generate_image", "m", 10.00, now=NEXT_MONTH)

    assert get_monthly_total(db_path, now=NEXT_MONTH) == pytest.approx(10.00)


def test_cost_by_user_is_sorted_biggest_spender_first(db_path):
    record_cost(db_path, 111, "generate_image", "m", 3.90, now=DAY_1)
    record_cost(db_path, 222, "generate_image", "m", 10.00, now=DAY_1)
    record_cost(db_path, 222, "transcribe", "m", 1.00, now=DAY_1)

    assert get_monthly_cost_by_user(db_path, now=DAY_1) == [
        (222, pytest.approx(11.00)),
        (111, pytest.approx(3.90)),
    ]


def test_cost_by_operation_shows_where_the_money_goes(db_path):
    record_cost(db_path, 111, "generate_image", "m", 3.90, now=DAY_1)
    record_cost(db_path, 111, "generate_image", "m", 3.90, now=DAY_1)
    record_cost(db_path, 111, "transcribe", "m", 0.96, now=DAY_1)

    assert get_monthly_cost_by_operation(db_path, now=DAY_1) == [
        ("generate_image", pytest.approx(7.80)),
        ("transcribe", pytest.approx(0.96)),
    ]


def test_several_costs_for_one_user_accumulate_rather_than_overwrite(db_path):
    for _ in range(3):
        record_cost(db_path, 111, "generate_image", "m", 3.90, now=DAY_1)

    assert get_monthly_cost_by_user(db_path, now=DAY_1) == [(111, pytest.approx(11.70))]
