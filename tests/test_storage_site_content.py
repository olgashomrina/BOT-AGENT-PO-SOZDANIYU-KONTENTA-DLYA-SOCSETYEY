from __future__ import annotations

from bot.storage.site_content import get_site_content, upsert_site_content


def test_unknown_block_returns_none(db_path):
    assert get_site_content(db_path, "services", "card_1") is None


def test_upsert_then_get_returns_stored_content(db_path):
    upsert_site_content(
        db_path, "services", "card_1", "Текст карточки", "file-id-1", "/media/services/card_1.jpg"
    )

    content = get_site_content(db_path, "services", "card_1")

    assert content.text == "Текст карточки"
    assert content.photo_file_id == "file-id-1"
    assert content.photo_static_path == "/media/services/card_1.jpg"
    assert content.updated_at


def test_upsert_twice_overwrites_previous_value(db_path):
    upsert_site_content(db_path, "services", "card_1", "Старый текст", "old-file-id", "/media/services/card_1.jpg")
    upsert_site_content(db_path, "services", "card_1", "Новый текст", "new-file-id", "/media/services/card_1.jpg")

    content = get_site_content(db_path, "services", "card_1")

    assert content.text == "Новый текст"
    assert content.photo_file_id == "new-file-id"


def test_upsert_with_no_photo_stores_none(db_path):
    upsert_site_content(db_path, "services", "card_1", "Только текст", None, None)

    content = get_site_content(db_path, "services", "card_1")

    assert content.photo_file_id is None
    assert content.photo_static_path is None


def test_different_block_ids_do_not_collide(db_path):
    upsert_site_content(db_path, "services", "card_1", "Карточка 1", None, None)
    upsert_site_content(db_path, "services", "card_2", "Карточка 2", None, None)

    assert get_site_content(db_path, "services", "card_1").text == "Карточка 1"
    assert get_site_content(db_path, "services", "card_2").text == "Карточка 2"
