from __future__ import annotations

from bot.storage.whitelist import add_user, is_whitelisted, remove_user


def test_unknown_user_is_not_whitelisted(db_path):
    assert is_whitelisted(db_path, 111) is False


def test_add_user_makes_them_whitelisted(db_path):
    add_user(db_path, 111)

    assert is_whitelisted(db_path, 111) is True


def test_add_user_twice_does_not_error(db_path):
    add_user(db_path, 111)
    add_user(db_path, 111)

    assert is_whitelisted(db_path, 111) is True


def test_remove_user_revokes_access(db_path):
    add_user(db_path, 111)

    remove_user(db_path, 111)

    assert is_whitelisted(db_path, 111) is False


def test_remove_user_not_in_whitelist_does_not_error(db_path):
    remove_user(db_path, 999)

    assert is_whitelisted(db_path, 999) is False


def test_whitelist_is_scoped_per_user(db_path):
    add_user(db_path, 111)

    assert is_whitelisted(db_path, 222) is False
