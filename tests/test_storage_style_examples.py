from __future__ import annotations

from bot.storage.style_examples import (
    MAX_EXAMPLES_PER_USER,
    add_style_example,
    clear_style_examples,
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


def test_cap_allows_ten_examples():
    assert MAX_EXAMPLES_PER_USER == 10


def test_clear_style_examples_removes_all_for_user(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Первый")
    add_style_example(db_path, TELEGRAM_ID, "Второй")

    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []


def test_clear_style_examples_leaves_other_users_untouched(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Пример пользователя А")
    add_style_example(db_path, OTHER_TELEGRAM_ID, "Пример пользователя Б")

    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    assert get_style_examples(db_path, OTHER_TELEGRAM_ID) == ["Пример пользователя Б"]


def test_clear_style_examples_is_safe_for_unknown_user(db_path):
    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []


from bot.storage.style_examples import KIND_SPOKEN, KIND_WRITTEN


def test_spoken_examples_do_not_appear_among_written(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка кружка", kind=KIND_SPOKEN)

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Письменный пост"]
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == [
        "Расшифровка кружка"
    ]


def test_spoken_examples_never_evict_written_ones(db_path):
    # Регрессия: общий на пользователя лимит вытеснил бы все письменные
    # образцы и сломал сценарий авторского поста, который требует их не менее 5.
    for index in range(MAX_EXAMPLES_PER_USER):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    for index in range(MAX_EXAMPLES_PER_USER + 5):
        add_style_example(db_path, TELEGRAM_ID, f"Кружок {index}", kind=KIND_SPOKEN)

    written = get_style_examples(db_path, TELEGRAM_ID, limit=100)

    assert len(written) == MAX_EXAMPLES_PER_USER


def test_spoken_examples_are_evicted_within_their_own_kind(db_path):
    for index in range(MAX_EXAMPLES_PER_USER + 3):
        add_style_example(db_path, TELEGRAM_ID, f"Кружок {index}", kind=KIND_SPOKEN)

    spoken = get_style_examples(db_path, TELEGRAM_ID, limit=100, kind=KIND_SPOKEN)

    assert len(spoken) == MAX_EXAMPLES_PER_USER


def test_clear_style_examples_can_target_a_single_kind(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка кружка", kind=KIND_SPOKEN)

    clear_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN)

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Письменный пост"]
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == []


def test_clear_style_examples_without_kind_still_clears_everything(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка кружка", kind=KIND_SPOKEN)

    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == []
