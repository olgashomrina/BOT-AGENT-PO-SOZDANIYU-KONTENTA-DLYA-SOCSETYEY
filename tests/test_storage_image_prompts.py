from __future__ import annotations

from bot.storage.image_prompts import MAX_PROMPTS_PER_CHAT, get_image_prompt, save_image_prompt

CHAT_ID = 555


def test_saved_prompt_round_trips(db_path):
    save_image_prompt(db_path, CHAT_ID, 10, "a vivid english prompt")

    assert get_image_prompt(db_path, CHAT_ID, 10) == "a vivid english prompt"


def test_missing_prompt_returns_none(db_path):
    assert get_image_prompt(db_path, CHAT_ID, 999) is None


def test_prompts_are_isolated_between_chats(db_path):
    save_image_prompt(db_path, CHAT_ID, 12, "мой промпт")
    save_image_prompt(db_path, 777, 12, "чужой промпт")

    assert get_image_prompt(db_path, CHAT_ID, 12) == "мой промпт"
    assert get_image_prompt(db_path, 777, 12) == "чужой промпт"


def test_saving_same_message_twice_overwrites(db_path):
    save_image_prompt(db_path, CHAT_ID, 13, "первый")
    save_image_prompt(db_path, CHAT_ID, 13, "второй")

    assert get_image_prompt(db_path, CHAT_ID, 13) == "второй"


def test_oldest_prompts_are_evicted_past_the_cap(db_path):
    for message_id in range(1, MAX_PROMPTS_PER_CHAT + 2):
        save_image_prompt(db_path, CHAT_ID, message_id, f"промпт {message_id}")

    assert get_image_prompt(db_path, CHAT_ID, 1) is None
    assert get_image_prompt(db_path, CHAT_ID, MAX_PROMPTS_PER_CHAT + 1) is not None


def test_eviction_does_not_touch_other_chats(db_path):
    save_image_prompt(db_path, 777, 1, "чужой")
    for message_id in range(1, MAX_PROMPTS_PER_CHAT + 2):
        save_image_prompt(db_path, CHAT_ID, message_id, f"промпт {message_id}")

    assert get_image_prompt(db_path, 777, 1) is not None
