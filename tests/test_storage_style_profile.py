from __future__ import annotations

from bot.storage.style_profile import (
    clear_style_profile,
    get_style_profile,
    set_style_profile,
)

TELEGRAM_ID = 111
OTHER_ID = 222


def test_get_returns_none_when_nothing_saved(db_path):
    assert get_style_profile(db_path, TELEGRAM_ID) is None


def test_set_then_get_returns_the_summary(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "• короткие абзацы\n• на «ты»")

    assert get_style_profile(db_path, TELEGRAM_ID) == "• короткие абзацы\n• на «ты»"


def test_set_twice_replaces_the_previous_summary(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "первое резюме")
    set_style_profile(db_path, TELEGRAM_ID, "второе резюме")

    assert get_style_profile(db_path, TELEGRAM_ID) == "второе резюме"


def test_profiles_are_per_user(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "мой стиль")
    set_style_profile(db_path, OTHER_ID, "чужой стиль")

    assert get_style_profile(db_path, TELEGRAM_ID) == "мой стиль"
    assert get_style_profile(db_path, OTHER_ID) == "чужой стиль"


def test_clear_removes_only_that_users_profile(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "мой стиль")
    set_style_profile(db_path, OTHER_ID, "чужой стиль")

    clear_style_profile(db_path, TELEGRAM_ID)

    assert get_style_profile(db_path, TELEGRAM_ID) is None
    assert get_style_profile(db_path, OTHER_ID) == "чужой стиль"


def test_clear_on_a_user_without_a_profile_is_a_no_op(db_path):
    clear_style_profile(db_path, TELEGRAM_ID)

    assert get_style_profile(db_path, TELEGRAM_ID) is None
