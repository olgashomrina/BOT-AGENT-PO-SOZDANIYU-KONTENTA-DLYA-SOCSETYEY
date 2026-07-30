from __future__ import annotations

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import BufferedInputFile

from bot.handlers.refine import (
    on_image_upgrade,
    on_image_upgrade_done,
    on_refine_image,
    on_refine_more,
    on_refine_publish,
    on_refine_shorten,
)
from bot.keyboards.refine import (
    CALLBACK_IMAGE_UPGRADE,
    CALLBACK_IMAGE_UPGRADE_DONE,
    build_image_upgrade_keyboard,
    build_image_upgraded_keyboard,
)
from bot.locales.loader import get_string
from bot.services import ai_gateway, content_generator, output_formatter
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.image_prompts import claim_image_prompt, save_image_prompt
from bot.storage.limits import get_daily_count, get_daily_image_count, increment_image_usage
from bot.storage.refine_context import get_refine_context, save_refine_context
from bot.storage.users import get_pending_media, set_channel_id, set_pending_media
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111
CHAT_ID = 333

# _generate_and_send now looks up its source text via a context row keyed on
# the message the button sits under, rather than trusting FSM data — every
# test below that seeds a "finished session" through _make_callback's default
# message id needs a matching row, or it would hit the "missing context"
# branch instead of ever calling generate_variants.
_SEEDED_MESSAGE_ID = 1

# The freshly sent variant carries its own buttons, so _generate_and_send
# records a context row for it too — every AsyncMock standing in for
# Message.answer here must therefore return something with a genuine int
# message_id (sqlite rejects binding a MagicMock). Same pattern as
# tests/test_handlers_content_flow.py and tests/test_handlers_site.py.
_sent_message_ids = itertools.count(1000)


def _make_sent_message():
    return SimpleNamespace(message_id=next(_sent_message_ids))


@pytest.fixture(autouse=True)
def _ai_gateway_env(monkeypatch):
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


async def _seed_finished_session(
    state: FSMContext,
    db_path: str,
    source_text: str = "Исходный текст статьи.",
    content_language: str = "ru",
    language: str = "ru",
    with_hashtags: bool = False,
    platform: str = "telegram",
    telegram_id: int = TELEGRAM_ID,
) -> None:
    await state.update_data(source_text=source_text, content_language=content_language, language=language)
    await state.set_state(None)
    # _generate_and_send reads the refine context, not FSM data, for
    # source_text/content_language/with_hashtags (see bot/handlers/refine.py)
    # — this row is what makes _make_callback's default message id resolve.
    save_refine_context(
        db_path, telegram_id, _SEEDED_MESSAGE_ID, source_text, content_language, with_hashtags, platform
    )


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = "", language_code: str = "ru"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    callback.data = data
    callback.message = AsyncMock()
    callback.message.chat = SimpleNamespace(id=telegram_id)
    callback.message.message_id = _SEEDED_MESSAGE_ID
    callback.message.answer = AsyncMock(side_effect=lambda *args, **kwargs: _make_sent_message())
    return callback


@pytest.mark.asyncio
async def test_refine_more_generates_and_sends_new_variant(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_generate = AsyncMock(return_value=["Новый вариант поста"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.",
        "telegram",
        "ru",
        count=1,
        extra_instruction=None,
        style_examples=[],
        with_hashtags=False,
    )
    callback.message.answer.assert_awaited_once()
    args, kwargs = callback.message.answer.call_args
    assert args[0] == output_formatter.format_variant("Новый вариант поста")
    assert kwargs["parse_mode"] == output_formatter.PARSE_MODE
    assert "reply_markup" in kwargs
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_shorten_passes_shorten_instruction(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_generate = AsyncMock(return_value=["Короткий вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:shorten:vk:1")
    await on_refine_shorten(callback, state, db_path)

    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.",
        "vk",
        "ru",
        count=1,
        extra_instruction=content_generator.SHORTEN_INSTRUCTION,
        style_examples=[],
        with_hashtags=False,
    )
    callback.message.answer.assert_awaited_once()
    args, _ = callback.message.answer.call_args
    assert args[0] == output_formatter.format_variant("Короткий вариант")
    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_blocked_when_daily_limit_exceeded_does_not_call_generate(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "0")
    state = _make_state()
    await _seed_finished_session(state, db_path, language="en")

    mock_generate = AsyncMock(return_value=["Не должно быть отправлено"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1", language_code="en")
    await on_refine_more(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_daily_limit_exceeded", "en"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_refine_blocked_when_at_limit_uses_stored_interface_language(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "0")
    state = _make_state()
    await _seed_finished_session(state, db_path, language="vi")

    mock_generate = AsyncMock(return_value=["x"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:shorten:telegram:1", language_code="en")
    await on_refine_shorten(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_daily_limit_exceeded", "vi"))


@pytest.mark.asyncio
async def test_refine_with_missing_fsm_data_does_not_crash(db_path, monkeypatch):
    state = _make_state()

    mock_generate = AsyncMock(return_value=["x"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("error_refine_missing_context", "ru")
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_refine_ai_gateway_error_replies_friendly_message_and_does_not_increment(
    db_path, monkeypatch
):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_generate = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.parametrize(
    "handler, data",
    [
        (on_refine_more, "refine:more:telegram:1"),
        (on_refine_shorten, "refine:shorten:telegram:1"),
    ],
)
@pytest.mark.asyncio
async def test_refine_blocked_when_not_whitelisted_does_not_call_generate(
    db_path, monkeypatch, handler, data
):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_finished_session(state, db_path)

    mock_generate = AsyncMock(return_value=["Не должно быть отправлено"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data=data)
    await handler(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, NOT_WHITELISTED_ID) == 0


CHANNEL_ID = -1001234567890


@pytest.mark.asyncio
async def test_publish_success_sends_formatted_variant_to_channel(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_awaited_once_with(
        CHANNEL_ID,
        output_formatter.format_variant("Готовый вариант поста"),
        parse_mode=output_formatter.PARSE_MODE,
    )
    callback.message.answer.assert_awaited_once_with(get_string("publish_success", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_without_configured_channel_prompts_setup_and_does_not_send(db_path):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("publish_no_channel_configured", "ru")
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_telegram_failure_replies_friendly_error(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()
    bot.send_message = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=CHANNEL_ID, text="x"), message="bot was kicked"
        )
    )

    await on_refine_publish(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("publish_failed", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_blocked_when_not_whitelisted_does_not_send(db_path):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_finished_session(state, db_path)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_with_pending_photo_sends_photo_not_message(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_not_awaited()
    bot.send_photo.assert_awaited_once_with(
        CHANNEL_ID,
        photo="photo-file-id",
        caption=output_formatter.format_variant("Готовый вариант поста"),
        parse_mode=output_formatter.PARSE_MODE,
    )
    callback.message.answer.assert_awaited_once_with(get_string("publish_success", "ru"))
    callback.answer.assert_awaited_once()
    assert get_pending_media(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_publish_with_pending_video_sends_video_not_message(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    set_pending_media(db_path, TELEGRAM_ID, "video-file-id", "video")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_not_awaited()
    bot.send_video.assert_awaited_once_with(
        CHANNEL_ID,
        video="video-file-id",
        caption=output_formatter.format_variant("Готовый вариант поста"),
        parse_mode=output_formatter.PARSE_MODE,
    )
    callback.message.answer.assert_awaited_once_with(get_string("publish_success", "ru"))
    assert get_pending_media(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_publish_without_pending_media_still_sends_message(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_photo.assert_not_awaited()
    bot.send_video.assert_not_awaited()
    bot.send_message.assert_awaited_once_with(
        CHANNEL_ID,
        output_formatter.format_variant("Готовый вариант поста"),
        parse_mode=output_formatter.PARSE_MODE,
    )


@pytest.mark.asyncio
async def test_publish_with_pending_photo_truncates_oversized_caption(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    oversized_text = "А" * 1500
    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = oversized_text
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    caption = kwargs["caption"]
    assert len(caption) == 1024
    assert caption.endswith("…")
    assert caption == output_formatter.format_variant(oversized_text)[:1023] + "…"


@pytest.mark.asyncio
async def test_publish_failure_with_pending_media_keeps_it_for_retry(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()
    bot.send_photo = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=CHANNEL_ID, text="x"), message="bot was kicked"
        )
    )

    await on_refine_publish(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("publish_failed", "ru"))
    assert get_pending_media(db_path, TELEGRAM_ID) == ("photo-file-id", "photo")


def _fake_sent_photo_message(file_id: str = "telegram-cdn-file-id", message_id: int = 5000):
    return SimpleNamespace(photo=[SimpleNamespace(file_id=file_id)], message_id=message_id)


@pytest.mark.asyncio
async def test_refine_image_success_stores_telegram_file_id(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_refine_image(callback, state, db_path, bot)

    mock_prompt.assert_awaited_once_with("Готовый вариант поста")
    mock_generate_image.assert_awaited_once_with("a vivid english prompt")
    bot.send_photo.assert_awaited_once()
    args, kwargs = bot.send_photo.call_args
    assert args[0] == TELEGRAM_ID
    assert isinstance(kwargs["photo"], BufferedInputFile)
    assert kwargs["photo"].data == b"fake-png-bytes"

    assert get_pending_media(db_path, TELEGRAM_ID) == ("telegram-cdn-file-id", "photo")
    callback.message.answer.assert_awaited_once_with(get_string("image_attached_confirmation", "ru"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_image_counts_towards_the_daily_image_budget(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    monkeypatch.setattr(
        content_generator, "generate_image_prompt", AsyncMock(return_value="a prompt")
    )
    monkeypatch.setattr(ai_gateway, "generate_image", AsyncMock(return_value=b"fake-png-bytes"))

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_refine_image(callback, state, db_path, bot)

    assert get_daily_image_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_image_refuses_once_daily_image_limit_is_reached(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_IMAGE_LIMIT", "2")
    state = _make_state()
    await _seed_finished_session(state, db_path)

    for _ in range(2):
        increment_image_usage(db_path, TELEGRAM_ID)

    mock_prompt = AsyncMock(return_value="a prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_image(callback, state, db_path, bot)

    mock_prompt.assert_not_awaited()
    mock_generate_image.assert_not_awaited()
    bot.send_photo.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("error_daily_image_limit", "ru", limit=2)
    )


@pytest.mark.asyncio
async def test_image_upgrade_refuses_once_daily_image_limit_is_reached(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_IMAGE_LIMIT", "1")
    state = _make_state()
    await _seed_finished_session(state, db_path)
    increment_image_usage(db_path, TELEGRAM_ID)

    save_image_prompt(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID, "a prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("error_daily_image_limit", "ru", limit=1)
    )
    # The stored prompt must survive a refusal — the user can upgrade this
    # very photo tomorrow, once the budget resets.
    assert claim_image_prompt(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID) == "a prompt"


@pytest.mark.asyncio
async def test_image_upgrade_counts_towards_the_daily_image_budget(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)
    save_image_prompt(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID, "a prompt")

    monkeypatch.setattr(ai_gateway, "generate_image", AsyncMock(return_value=b"fake-png-bytes"))

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("upgraded-file-id"))

    await on_image_upgrade(callback, state, db_path, bot)

    assert get_daily_image_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_image_success_attaches_upgrade_button_and_stores_prompt(db_path, monkeypatch):
    from bot.keyboards.refine import build_image_upgrade_keyboard

    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_refine_image(callback, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    expected_keyboard = build_image_upgrade_keyboard("ru")
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        expected_keyboard.inline_keyboard[0][0].callback_data
    )
    assert claim_image_prompt(db_path, TELEGRAM_ID, 5000) == "a vivid english prompt"


@pytest.mark.asyncio
async def test_refine_image_stale_callback_answer_does_not_raise(db_path, monkeypatch):
    # Reproduces a production bug: a slow/retried AI Gateway call can push
    # elapsed time past Telegram's callback-query validity window, so the
    # final callback.answer() raises "query is too old" — this must not
    # escape as an unhandled exception (which would trigger the generic
    # error_unexpected message even though the image was already delivered).
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.answer = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=TELEGRAM_ID, text="x"),
            message="query is too old and response timeout expired or query ID is invalid",
        )
    )
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_refine_image(callback, state, db_path, bot)

    bot.send_photo.assert_awaited_once()
    callback.message.answer.assert_awaited_once_with(get_string("image_attached_confirmation", "ru"))
    assert get_pending_media(db_path, TELEGRAM_ID) == ("telegram-cdn-file-id", "photo")


@pytest.mark.asyncio
async def test_refine_image_prompt_failure_replies_friendly_error_and_does_not_call_send_photo(
    db_path, monkeypatch
):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    mock_generate_image = AsyncMock()
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()

    await on_refine_image(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    bot.send_photo.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    callback.answer.assert_awaited_once()
    assert get_pending_media(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_refine_image_generation_failure_replies_friendly_error(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()

    await on_refine_image(callback, state, db_path, bot)

    bot.send_photo.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    callback.answer.assert_awaited_once()
    assert get_pending_media(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_refine_image_delivery_failure_replies_friendly_error_and_does_not_attach_or_charge(
    db_path, monkeypatch
):
    state = _make_state()
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()
    bot.send_photo = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=TELEGRAM_ID, text="x"), message="failed to fetch image"
        )
    )

    await on_refine_image(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("image_delivery_failed", "ru"))
    callback.answer.assert_awaited_once()
    assert get_pending_media(db_path, TELEGRAM_ID) is None
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_refine_image_blocked_when_not_whitelisted_does_not_call_ai(db_path, monkeypatch):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_finished_session(state, db_path)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data="refine:image:telegram:1")
    callback.message.text = "Готовый вариант поста"
    callback.message.chat = SimpleNamespace(id=NOT_WHITELISTED_ID)
    bot = AsyncMock()

    await on_refine_image(callback, state, db_path, bot)

    mock_prompt.assert_not_awaited()
    mock_generate_image.assert_not_awaited()
    bot.send_photo.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    callback.answer.assert_awaited_once()


from bot.storage.style_examples import add_style_example


@pytest.mark.asyncio
async def test_refine_more_forwards_stored_style_examples(db_path, monkeypatch):
    add_style_example(db_path, TELEGRAM_ID, "Мой старый пост.")
    state = _make_state()
    await _seed_finished_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    await on_refine_more(_make_callback(data="refine:more:telegram:1"), state, db_path)

    assert mock_generate.await_args.kwargs["style_examples"] == ["Мой старый пост."]


@pytest.mark.asyncio
async def test_refine_more_forwards_hashtag_flag_from_context(db_path, monkeypatch):
    # with_hashtags now comes from the refine-context row, not FSM data (see
    # bot/handlers/refine.py::_generate_and_send), so it is seeded here the
    # same way _generate_and_send will read it back.
    state = _make_state()
    await _seed_finished_session(state, db_path, with_hashtags=True)
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    await on_refine_more(_make_callback(data="refine:more:telegram:1"), state, db_path)

    assert mock_generate.await_args.kwargs["with_hashtags"] is True


@pytest.mark.asyncio
async def test_refine_more_defaults_hashtag_flag_to_false(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state, db_path)
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    await on_refine_more(_make_callback(data="refine:more:telegram:1"), state, db_path)

    assert mock_generate.await_args.kwargs["with_hashtags"] is False


async def _seed_upgrade_session(
    state: FSMContext,
    db_path: str,
    prompt: str = "a vivid english prompt",
    chat_id: int = TELEGRAM_ID,
    message_id: int = _SEEDED_MESSAGE_ID,
) -> None:
    await state.update_data(language="ru")
    await state.set_state(None)
    save_image_prompt(db_path, chat_id, message_id, prompt)


@pytest.mark.asyncio
async def test_image_upgrade_success_uses_premium_model_and_sends_new_photo(db_path, monkeypatch):
    state = _make_state()
    await _seed_upgrade_session(state, db_path)

    mock_generate_image = AsyncMock(return_value=b"fake-premium-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)
    monkeypatch.setenv("AI_GATEWAY_PREMIUM_IMAGE_MODEL", "test-premium-model")

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("premium-file-id"))

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_awaited_once_with("a vivid english prompt", model="test-premium-model")
    bot.send_photo.assert_awaited_once()
    args, kwargs = bot.send_photo.call_args
    assert args[0] == TELEGRAM_ID
    assert kwargs["photo"].data == b"fake-premium-png-bytes"
    assert kwargs["caption"] == get_string("image_upgraded_caption", "ru")

    assert get_pending_media(db_path, TELEGRAM_ID) == ("premium-file-id", "photo")
    assert get_daily_count(db_path, TELEGRAM_ID) == 1

    callback.message.edit_reply_markup.assert_awaited_once()
    _, edit_kwargs = callback.message.edit_reply_markup.call_args
    expected_keyboard = build_image_upgraded_keyboard("ru")
    assert edit_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        expected_keyboard.inline_keyboard[0][0].callback_data
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_upgrade_ai_error_replies_friendly_message_and_keeps_button(db_path, monkeypatch):
    state = _make_state()
    await _seed_upgrade_session(state, db_path)

    mock_generate_image = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    bot.send_photo.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    assert callback.message.edit_reply_markup.await_count == 2
    restore_call_kwargs = callback.message.edit_reply_markup.call_args_list[-1].kwargs
    upgrade_keyboard = build_image_upgrade_keyboard("ru")
    assert restore_call_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        upgrade_keyboard.inline_keyboard[0][0].callback_data
    )
    assert get_pending_media(db_path, TELEGRAM_ID) is None
    assert get_daily_count(db_path, TELEGRAM_ID) == 0
    # The claim consumed the prompt before the AI call failed — the restore
    # path must put it back, or a retry after this error would always hit
    # "missing context" instead of actually retrying.
    assert claim_image_prompt(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID) == "a vivid english prompt"


@pytest.mark.asyncio
async def test_image_upgrade_missing_prompt_replies_friendly_error_and_does_not_call_ai(db_path, monkeypatch):
    state = _make_state()
    await state.update_data(language="ru")
    await state.set_state(None)

    mock_generate_image = AsyncMock()
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_refine_missing_context", "ru"))
    callback.message.edit_reply_markup.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_upgrade_second_concurrent_tap_gets_missing_context_not_a_second_charge(
    db_path, monkeypatch
):
    state = _make_state()
    await state.update_data(language="ru")
    await state.set_state(None)
    save_image_prompt(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID, "a vivid english prompt")

    mock_generate_image = AsyncMock(return_value=b"fake-premium-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("premium-file-id"))

    # Simulate the row already being claimed by a "first" concurrent tap
    # that ran to completion before this one even started reading it.
    from bot.storage.image_prompts import claim_image_prompt as _claim_directly

    _claim_directly(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID)

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_refine_missing_context", "ru"))


@pytest.mark.asyncio
async def test_image_upgrade_blocked_when_not_whitelisted_does_not_call_ai(db_path, monkeypatch):
    NOT_WHITELISTED_ID = 998
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_upgrade_session(state, db_path)

    mock_generate_image = AsyncMock()
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=NOT_WHITELISTED_ID)
    bot = AsyncMock()

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_image_upgrade_delivery_failure_replies_friendly_error_and_does_not_attach_or_charge(
    db_path, monkeypatch
):
    state = _make_state()
    await _seed_upgrade_session(state, db_path)

    mock_generate_image = AsyncMock(return_value=b"fake-premium-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()
    bot.send_photo = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=TELEGRAM_ID, text="x"), message="failed to fetch image"
        )
    )

    await on_image_upgrade(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("image_delivery_failed", "ru"))
    assert callback.message.edit_reply_markup.await_count == 2
    restore_call_kwargs = callback.message.edit_reply_markup.call_args_list[-1].kwargs
    upgrade_keyboard = build_image_upgrade_keyboard("ru")
    assert restore_call_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        upgrade_keyboard.inline_keyboard[0][0].callback_data
    )
    assert get_pending_media(db_path, TELEGRAM_ID) is None
    assert get_daily_count(db_path, TELEGRAM_ID) == 0
    # Same reasoning as the AI-error test above: the claimed prompt must be
    # restored after a delivery failure too, or a retry can never succeed.
    assert claim_image_prompt(db_path, TELEGRAM_ID, _SEEDED_MESSAGE_ID) == "a vivid english prompt"


@pytest.mark.asyncio
async def test_image_upgrade_uses_the_prompt_for_the_specific_photo_tapped(db_path, monkeypatch):
    state = _make_state()
    await state.update_data(language="ru")
    await state.set_state(None)
    save_image_prompt(db_path, TELEGRAM_ID, 4001, "prompt for the OLDER photo")
    save_image_prompt(db_path, TELEGRAM_ID, 4002, "prompt for the NEWER photo")

    mock_generate_image = AsyncMock(return_value=b"fake-premium-png-bytes")
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE)
    callback.message.chat = SimpleNamespace(id=TELEGRAM_ID)
    callback.message.message_id = 4001
    callback.message.edit_reply_markup = AsyncMock()
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("premium-file-id"))

    await on_image_upgrade(callback, state, db_path, bot)

    mock_generate_image.assert_awaited_once()
    args, _ = mock_generate_image.call_args
    assert args[0] == "prompt for the OLDER photo"


@pytest.mark.asyncio
async def test_image_upgrade_done_button_just_acknowledges():
    callback = _make_callback(data=CALLBACK_IMAGE_UPGRADE_DONE)

    await on_image_upgrade_done(callback)

    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_refine_more_uses_the_context_of_its_own_message(db_path, monkeypatch):
    state = _make_state()
    # Two posts generated in sequence: the second overwrites any shared value.
    save_refine_context(db_path, CHAT_ID, 10, "Первый исходник", "ru", True, "telegram")
    save_refine_context(db_path, CHAT_ID, 20, "Второй исходник", "en", False, "vk")

    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    # The button under the FIRST post is tapped.
    callback = _make_callback(data="refine:more:telegram:1")
    callback.message.message_id = 10
    callback.message.chat = SimpleNamespace(id=CHAT_ID)

    await on_refine_more(callback, state, db_path)

    assert mock_generate.await_args.args[0] == "Первый исходник"
    assert mock_generate.await_args.kwargs["with_hashtags"] is True


@pytest.mark.asyncio
async def test_refine_without_stored_context_reports_missing_context(db_path, monkeypatch):
    state = _make_state()
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    callback.message.message_id = 999
    callback.message.chat = SimpleNamespace(id=CHAT_ID)

    await on_refine_more(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("error_refine_missing_context", "ru")
    )


@pytest.mark.asyncio
async def test_refine_records_context_for_the_message_it_sends(db_path, monkeypatch):
    state = _make_state()
    save_refine_context(db_path, CHAT_ID, 10, "Первый исходник", "ru", True, "telegram")
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Новый вариант"])
    )

    callback = _make_callback(data="refine:more:telegram:1")
    callback.message.message_id = 10
    callback.message.chat = SimpleNamespace(id=CHAT_ID)
    callback.message.answer = AsyncMock(return_value=SimpleNamespace(message_id=30))

    await on_refine_more(callback, state, db_path)

    # The freshly sent variant carries its own buttons, so it needs its own
    # context row — otherwise refining a refinement would report "missing".
    assert get_refine_context(db_path, CHAT_ID, 30)["source_text"] == "Первый исходник"
