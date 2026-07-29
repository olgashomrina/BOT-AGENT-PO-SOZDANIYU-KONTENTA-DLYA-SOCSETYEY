from __future__ import annotations

from bot.storage.refine_context import (
    MAX_CONTEXTS_PER_CHAT,
    get_refine_context,
    save_refine_context,
)

CHAT_ID = 555


def test_saved_context_round_trips(db_path):
    save_refine_context(db_path, CHAT_ID, 10, "Исходник", "ru", True, "telegram")

    context = get_refine_context(db_path, CHAT_ID, 10)

    assert context == {
        "source_text": "Исходник",
        "content_language": "ru",
        "with_hashtags": True,
        "platform": "telegram",
    }


def test_missing_context_returns_none(db_path):
    assert get_refine_context(db_path, CHAT_ID, 999) is None


def test_with_hashtags_round_trips_as_bool_not_int(db_path):
    save_refine_context(db_path, CHAT_ID, 11, "Исходник", "ru", False, "vk")

    context = get_refine_context(db_path, CHAT_ID, 11)

    assert context["with_hashtags"] is False


def test_contexts_are_isolated_between_chats(db_path):
    save_refine_context(db_path, CHAT_ID, 12, "Мой", "ru", True, "telegram")
    save_refine_context(db_path, 777, 12, "Чужой", "en", False, "vk")

    assert get_refine_context(db_path, CHAT_ID, 12)["source_text"] == "Мой"
    assert get_refine_context(db_path, 777, 12)["source_text"] == "Чужой"


def test_saving_same_message_twice_overwrites(db_path):
    save_refine_context(db_path, CHAT_ID, 13, "Первый", "ru", True, "telegram")
    save_refine_context(db_path, CHAT_ID, 13, "Второй", "en", False, "vk")

    context = get_refine_context(db_path, CHAT_ID, 13)

    assert context["source_text"] == "Второй"
    assert context["content_language"] == "en"


def test_oldest_contexts_are_evicted_past_the_cap(db_path):
    for message_id in range(1, MAX_CONTEXTS_PER_CHAT + 2):
        save_refine_context(db_path, CHAT_ID, message_id, f"Пост {message_id}", "ru", False, "telegram")

    # The very first message's context is gone, the newest survives.
    assert get_refine_context(db_path, CHAT_ID, 1) is None
    assert get_refine_context(db_path, CHAT_ID, MAX_CONTEXTS_PER_CHAT + 1) is not None


def test_eviction_does_not_touch_other_chats(db_path):
    save_refine_context(db_path, 777, 1, "Чужой", "ru", False, "telegram")
    for message_id in range(1, MAX_CONTEXTS_PER_CHAT + 2):
        save_refine_context(db_path, CHAT_ID, message_id, f"Пост {message_id}", "ru", False, "telegram")

    assert get_refine_context(db_path, 777, 1) is not None
