from __future__ import annotations

from bot.storage.users import (
    get_channel_id,
    get_content_language,
    get_interface_language,
    set_channel_id,
    set_content_language,
    set_interface_language,
)


def test_unknown_user_has_no_interface_language(db_path):
    assert get_interface_language(db_path, 111) is None


def test_unknown_user_has_no_content_language(db_path):
    assert get_content_language(db_path, 111) is None


def test_set_interface_language_is_readable(db_path):
    set_interface_language(db_path, 111, "ru")

    assert get_interface_language(db_path, 111) == "ru"


def test_content_language_defaults_to_interface_language(db_path):
    set_interface_language(db_path, 111, "ru")

    assert get_content_language(db_path, 111) == "ru"


def test_content_language_can_be_set_independently(db_path):
    set_interface_language(db_path, 111, "ru")
    set_content_language(db_path, 111, "en")

    assert get_content_language(db_path, 111) == "en"
    assert get_interface_language(db_path, 111) == "ru"


def test_changing_interface_language_does_not_change_explicit_content_language(db_path):
    set_interface_language(db_path, 111, "ru")
    set_content_language(db_path, 111, "en")

    set_interface_language(db_path, 111, "vi")

    assert get_interface_language(db_path, 111) == "vi"
    assert get_content_language(db_path, 111) == "en"


def test_languages_are_scoped_per_user(db_path):
    set_interface_language(db_path, 111, "ru")

    assert get_interface_language(db_path, 222) is None


def test_unknown_user_has_no_channel_id(db_path):
    assert get_channel_id(db_path, 111) is None


def test_set_channel_id_is_readable(db_path):
    set_channel_id(db_path, 111, -1001234567890)

    assert get_channel_id(db_path, 111) == -1001234567890


def test_channel_id_is_scoped_per_user(db_path):
    set_channel_id(db_path, 111, -1001234567890)

    assert get_channel_id(db_path, 222) is None


def test_channel_id_can_be_replaced(db_path):
    set_channel_id(db_path, 111, -1001111111111)
    set_channel_id(db_path, 111, -1002222222222)

    assert get_channel_id(db_path, 111) == -1002222222222
