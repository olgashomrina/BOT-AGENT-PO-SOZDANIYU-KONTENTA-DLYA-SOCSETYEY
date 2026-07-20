from __future__ import annotations

from bot.storage.style_examples import (
    MAX_EXAMPLES_PER_USER,
    add_style_example,
    get_style_examples,
)

TELEGRAM_ID = 111
OTHER_TELEGRAM_ID = 222


def test_get_style_examples_empty_for_unknown_user(db_path):
    assert get_style_examples(db_path, TELEGRAM_ID) == []


def test_add_and_get_style_example_round_trip(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Мой первый пост.")

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Мой первый пост."]


def test_get_style_examples_returns_most_recent_first(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Первый")
    add_style_example(db_path, TELEGRAM_ID, "Второй")
    add_style_example(db_path, TELEGRAM_ID, "Третий")

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Третий", "Второй", "Первый"]


def test_add_style_example_evicts_oldest_beyond_cap(db_path):
    for index in range(MAX_EXAMPLES_PER_USER + 2):
        add_style_example(db_path, TELEGRAM_ID, f"Пример {index}")

    examples = get_style_examples(db_path, TELEGRAM_ID, limit=100)

    assert len(examples) == MAX_EXAMPLES_PER_USER
    assert examples == [
        f"Пример {index}"
        for index in range(MAX_EXAMPLES_PER_USER + 1, 1, -1)
    ]


def test_get_style_examples_respects_limit_argument(db_path):
    for index in range(MAX_EXAMPLES_PER_USER):
        add_style_example(db_path, TELEGRAM_ID, f"Пример {index}")

    assert len(get_style_examples(db_path, TELEGRAM_ID, limit=2)) == 2


def test_style_examples_are_isolated_per_user(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Пример пользователя А")
    add_style_example(db_path, OTHER_TELEGRAM_ID, "Пример пользователя Б")

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Пример пользователя А"]
    assert get_style_examples(db_path, OTHER_TELEGRAM_ID) == ["Пример пользователя Б"]
