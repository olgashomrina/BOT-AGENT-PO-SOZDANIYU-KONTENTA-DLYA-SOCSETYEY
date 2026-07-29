from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.authorpost import on_authorpost_item, on_authorpost_start
from bot.keyboards.authorpost import CALLBACK_ITEM_PREFIX, CALLBACK_START
from bot.locales.loader import get_string
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111

DIGEST_ITEMS = [
    "Новость про ИИ",
    "Вторая новость",
    "Научная статья",
    "Новая методика X.",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_callback(data: str, telegram_id: int = TELEGRAM_ID):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


def _make_message(text: str | None = None, telegram_id: int = TELEGRAM_ID):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.text = text
    return message


@pytest.mark.asyncio
async def test_start_shows_one_button_per_digest_item(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_item", "ru")
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert len(buttons) == len(DIGEST_ITEMS)


@pytest.mark.asyncio
async def test_start_reports_expired_digest_when_fsm_has_no_items(db_path):
    state = _make_state()
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


@pytest.mark.asyncio
async def test_start_reports_expired_digest_when_items_are_empty(db_path):
    state = _make_state()
    await state.update_data(digest_items=[])
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


@pytest.mark.asyncio
async def test_start_refuses_user_outside_whitelist(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(CALLBACK_START, telegram_id=999)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_not_whitelisted", "ru")


@pytest.mark.asyncio
async def test_item_choice_stores_source_text_and_offers_next_step(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:2")

    await on_authorpost_item(callback, state, db_path)

    data = await state.get_data()
    assert data["source_text"] == "Научная статья"
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_item_chosen", "ru", item="Научная статья")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_item_choice_out_of_range_reports_expired_digest(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:99")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    data = await state.get_data()
    assert "source_text" not in data


@pytest.mark.asyncio
async def test_item_choice_negative_index_reports_expired_digest(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:-1")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    data = await state.get_data()
    assert "source_text" not in data


@pytest.mark.asyncio
async def test_item_choice_malformed_index_reports_expired_digest(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:abc")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    data = await state.get_data()
    assert "source_text" not in data


@pytest.mark.asyncio
async def test_item_choice_without_digest_items_reports_expired(db_path):
    state = _make_state()
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:0")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


from bot.handlers.authorpost import (
    REQUIRED_EXAMPLES,
    AuthorPostStates,
    on_authorpost_new_samples,
    on_authorpost_next,
    on_authorpost_sample,
    on_authorpost_samples_done,
    on_authorpost_use_saved,
)
from bot.handlers.settov import MAX_EXAMPLE_LENGTH
from bot.storage.style_examples import add_style_example, get_style_examples


@pytest.mark.asyncio
async def test_next_step_prompts_for_samples_when_storage_empty(db_path):
    state = _make_state()
    callback = _make_callback("authorpost:next")

    await on_authorpost_next(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_samples_prompt", "ru", required=REQUIRED_EXAMPLES)
    assert await state.get_state() == AuthorPostStates.collecting_examples.state


@pytest.mark.asyncio
async def test_next_step_offers_saved_examples_when_enough_stored(db_path):
    for index in range(REQUIRED_EXAMPLES):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    state = _make_state()
    callback = _make_callback("authorpost:next")

    await on_authorpost_next(callback, state, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string(
        "authorpost_saved_examples_intro", "ru", count=REQUIRED_EXAMPLES
    )
    assert "reply_markup" in kwargs
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_next_step_prompts_for_samples_when_stored_below_threshold(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Единственный пост")
    state = _make_state()
    callback = _make_callback("authorpost:next")

    await on_authorpost_next(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_samples_prompt", "ru", required=REQUIRED_EXAMPLES)


@pytest.mark.asyncio
async def test_use_saved_goes_straight_to_platform_choice(db_path):
    callback = _make_callback("authorpost:use_saved")

    await on_authorpost_use_saved(callback, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_platform", "ru")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_new_samples_wipes_storage_and_starts_collecting(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Старый пост")
    state = _make_state()
    callback = _make_callback("authorpost:new_samples")

    await on_authorpost_new_samples(callback, state, db_path)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    assert await state.get_state() == AuthorPostStates.collecting_examples.state


@pytest.mark.asyncio
async def test_sample_below_threshold_shows_progress_without_done_button(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="Мой пост")

    await on_authorpost_sample(message, state, db_path)

    args, kwargs = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_progress", "ru", count=1, required=REQUIRED_EXAMPLES
    )
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_sample_at_threshold_offers_done_button(db_path):
    for index in range(REQUIRED_EXAMPLES - 1):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="Пятый пост")

    await on_authorpost_sample(message, state, db_path)

    args, kwargs = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_enough", "ru", count=REQUIRED_EXAMPLES, required=REQUIRED_EXAMPLES
    )
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_sample_counter_includes_previously_stored_examples(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Ранее сохранённый")
    add_style_example(db_path, TELEGRAM_ID, "И ещё один")
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="Третий")

    await on_authorpost_sample(message, state, db_path)

    args, _ = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_progress", "ru", count=3, required=REQUIRED_EXAMPLES
    )


@pytest.mark.asyncio
async def test_non_text_sample_is_rejected_without_counting(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text=None)

    await on_authorpost_sample(message, state, db_path)

    args, _ = message.answer.call_args
    assert args[0] == get_string("authorpost_sample_non_text", "ru")
    assert get_style_examples(db_path, TELEGRAM_ID) == []


@pytest.mark.asyncio
async def test_overlong_sample_is_rejected_without_counting(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    message = _make_message(text="я" * (MAX_EXAMPLE_LENGTH + 1))

    await on_authorpost_sample(message, state, db_path)

    args, _ = message.answer.call_args
    assert args[0] == get_string("authorpost_sample_too_long", "ru")
    assert get_style_examples(db_path, TELEGRAM_ID) == []


@pytest.mark.asyncio
async def test_samples_done_clears_state_and_asks_for_platform(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    callback = _make_callback("authorpost:samples_done")

    await on_authorpost_samples_done(callback, state, db_path)

    assert await state.get_state() is None
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_platform", "ru")
    assert "reply_markup" in kwargs


from bot.handlers.authorpost import on_authorpost_platform
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.limits import get_daily_count


async def _seed_ready_session(state: FSMContext, db_path: str) -> None:
    for index in range(REQUIRED_EXAMPLES):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    await state.update_data(
        digest_items=DIGEST_ITEMS,
        source_text="Научная статья",
        content_language="ru",
        language="ru",
    )
    await state.set_state(None)


@pytest.mark.asyncio
async def test_platform_telegram_generates_with_style_and_hashtags(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Вариант 1", "Вариант 2", "Вариант 3"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    mock_generate.assert_awaited_once()
    kwargs = mock_generate.await_args.kwargs
    assert mock_generate.await_args.args[1] == "telegram"
    assert kwargs["with_hashtags"] is True
    assert len(kwargs["style_examples"]) == REQUIRED_EXAMPLES


@pytest.mark.asyncio
async def test_platform_both_generates_for_two_platforms(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:both")

    await on_authorpost_platform(callback, state, db_path)

    platforms = [call.args[1] for call in mock_generate.await_args_list]
    assert platforms == ["telegram", "vk"]


@pytest.mark.asyncio
async def test_platform_choice_sets_hashtag_flag_in_fsm(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Вариант"])
    )
    callback = _make_callback("authorpost:platform:vk")

    await on_authorpost_platform(callback, state, db_path)

    data = await state.get_data()
    assert data["with_hashtags"] is True


@pytest.mark.asyncio
async def test_platform_choice_without_source_reports_expired(db_path, monkeypatch):
    state = _make_state()
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    mock_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_choice_refuses_user_outside_whitelist(db_path, monkeypatch):
    state = _make_state(telegram_id=999)
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:telegram", telegram_id=999)

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_not_whitelisted", "ru")
    mock_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_choice_reports_ai_error_without_spending_quota(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator,
        "generate_variants",
        AsyncMock(side_effect=AIGatewayTimeoutError("timed out")),
    )
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_ai_timeout", "ru")
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_platform_choice_spends_quota_on_success(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Вариант"])
    )
    callback = _make_callback("authorpost:platform:telegram")

    await on_authorpost_platform(callback, state, db_path)

    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_platform_both_charges_quota_once_per_platform(db_path, monkeypatch):
    state = _make_state()
    await _seed_ready_session(state, db_path)
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Вариант"])
    )
    callback = _make_callback("authorpost:platform:both")

    await on_authorpost_platform(callback, state, db_path)

    assert get_daily_count(db_path, TELEGRAM_ID) == 2


@pytest.mark.asyncio
async def test_platform_choice_forged_callback_data_reports_expired(db_path, monkeypatch):
    # callback.data is client-supplied, same as in on_authorpost_item: a
    # modified client can send a suffix that isn't one of this bot's own
    # keyboard's "telegram"/"vk"/"both" values. A raw dict lookup would raise
    # KeyError before _safe_answer runs, leaving the button's spinner hanging.
    state = _make_state()
    await _seed_ready_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)
    callback = _make_callback("authorpost:platform:unknown")

    await on_authorpost_platform(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    mock_generate.assert_not_awaited()
    callback.answer.assert_awaited_once()
