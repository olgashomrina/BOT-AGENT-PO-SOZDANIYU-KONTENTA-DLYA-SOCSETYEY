from __future__ import annotations

from bot.storage.users import (
    clear_pending_media,
    get_channel_id,
    get_content_language,
    get_interface_language,
    get_onboarding_shown,
    get_pending_media,
    set_channel_id,
    set_content_language,
    set_interface_language,
    set_onboarding_shown,
    set_pending_media,
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


def test_unknown_user_has_no_pending_media(db_path):
    assert get_pending_media(db_path, 111) is None


def test_set_pending_media_is_readable(db_path):
    set_pending_media(db_path, 111, "file-abc", "photo")

    assert get_pending_media(db_path, 111) == ("file-abc", "photo")


def test_pending_media_supports_video_type(db_path):
    set_pending_media(db_path, 111, "file-xyz", "video")

    assert get_pending_media(db_path, 111) == ("file-xyz", "video")


def test_pending_media_can_be_replaced(db_path):
    set_pending_media(db_path, 111, "file-old", "photo")
    set_pending_media(db_path, 111, "file-new", "video")

    assert get_pending_media(db_path, 111) == ("file-new", "video")


def test_pending_media_is_scoped_per_user(db_path):
    set_pending_media(db_path, 111, "file-abc", "photo")

    assert get_pending_media(db_path, 222) is None


def test_clear_pending_media_removes_it(db_path):
    set_pending_media(db_path, 111, "file-abc", "photo")

    clear_pending_media(db_path, 111)

    assert get_pending_media(db_path, 111) is None


def test_clear_pending_media_on_unknown_user_does_not_crash(db_path):
    clear_pending_media(db_path, 999)

    assert get_pending_media(db_path, 999) is None


def test_unknown_user_has_onboarding_not_shown(db_path):
    assert get_onboarding_shown(db_path, 111) is False


def test_set_onboarding_shown_is_readable(db_path):
    set_onboarding_shown(db_path, 111, True)

    assert get_onboarding_shown(db_path, 111) is True


def test_onboarding_shown_can_be_reset(db_path):
    set_onboarding_shown(db_path, 111, True)
    set_onboarding_shown(db_path, 111, False)

    assert get_onboarding_shown(db_path, 111) is False


def test_onboarding_shown_is_scoped_per_user(db_path):
    set_onboarding_shown(db_path, 111, True)

    assert get_onboarding_shown(db_path, 222) is False
