from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, call

import pytest

from bot.handlers.start import cmd_help, cmd_start
from bot.locales.loader import get_string
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
)


def _make_message(telegram_id: int, language_code: str | None, text: str | None = "/start"):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    message.text = text
    return message


def _greeting_calls(language: str):
    return [
        call(get_string("start_greeting", language), reply_markup=ANY),
        call(get_string("menu_intro", language), reply_markup=ANY),
    ]


def _onboarding_calls(language: str):
    return [
        call(get_string("onboarding_capabilities", language)),
        call(get_string("onboarding_settov", language)),
        call(get_string("onboarding_quick_start", language)),
    ]


@pytest.mark.asyncio
async def test_new_user_gets_language_from_supported_language_code(db_path):
    message = _make_message(111, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 111) == "vi"
    message.answer.assert_has_calls([*_greeting_calls("vi"), *_onboarding_calls("vi")])


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_for_unsupported_language_code(db_path):
    message = _make_message(222, "fr")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 222) == "ru"
    message.answer.assert_has_calls([*_greeting_calls("ru"), *_onboarding_calls("ru")])


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_when_language_code_missing(db_path):
    message = _make_message(333, None)

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 333) == "ru"


@pytest.mark.asyncio
async def test_new_user_sees_greeting_menu_and_all_three_onboarding_messages(db_path):
    message = _make_message(777, "ru")

    await cmd_start(message, db_path)

    assert message.answer.await_count == 5
    message.answer.assert_has_calls([*_greeting_calls("ru"), *_onboarding_calls("ru")])


@pytest.mark.asyncio
async def test_new_user_start_persists_onboarding_shown_flag(db_path):
    message = _make_message(888, "ru")

    await cmd_start(message, db_path)

    assert get_onboarding_shown(db_path, 888) is True


@pytest.mark.asyncio
async def test_second_start_from_same_new_user_does_not_repeat_onboarding(db_path):
    message = _make_message(999, "ru")

    await cmd_start(message, db_path)
    message.answer.reset_mock()
    await cmd_start(message, db_path)

    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("ru"))


@pytest.mark.asyncio
async def test_returning_user_start_shows_greeting_and_menu_only(db_path):
    set_interface_language(db_path, 444, "en")
    set_onboarding_shown(db_path, 444, True)
    message = _make_message(444, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 444) == "en"
    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("en"))


@pytest.mark.asyncio
async def test_persistent_start_button_text_triggers_same_flow_as_command(db_path):
    set_interface_language(db_path, 1010, "ru")
    set_onboarding_shown(db_path, 1010, True)
    message = _make_message(1010, "ru", text=get_string("start_button_label", "ru"))

    await cmd_start(message, db_path)

    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("ru"))


@pytest.mark.asyncio
async def test_help_shows_onboarding_for_new_user(db_path):
    message = _make_message(555, "ru")

    await cmd_help(message, db_path)

    assert message.answer.await_count == 3
    message.answer.assert_has_calls(_onboarding_calls("ru"))


@pytest.mark.asyncio
async def test_help_shows_onboarding_again_for_user_who_already_saw_it(db_path):
    set_interface_language(db_path, 666, "zh")
    set_onboarding_shown(db_path, 666, True)
    message = _make_message(666, "en")

    await cmd_help(message, db_path)

    assert message.answer.await_count == 3
    message.answer.assert_has_calls(_onboarding_calls("zh"))


from bot.handlers.start import on_menu_capabilities, on_menu_create_post, on_menu_text_hint
from bot.keyboards.start import CALLBACK_CAPABILITIES, CALLBACK_CREATE_POST, CALLBACK_TEXT_HINT
from bot.storage.whitelist import add_user


def _make_callback(telegram_id: int, data: str, language_code: str = "ru"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_menu_capabilities_sends_onboarding_capabilities_text(db_path):
    add_user(db_path, 2001)
    callback = _make_callback(2001, CALLBACK_CAPABILITIES)

    await on_menu_capabilities(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("onboarding_capabilities", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_capabilities_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2002, CALLBACK_CAPABILITIES)

    await on_menu_capabilities(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_menu_create_post_shows_submenu_keyboard(db_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    add_user(db_path, 2003)
    callback = _make_callback(2003, CALLBACK_CREATE_POST)

    await on_menu_create_post(callback, db_path)

    callback.message.answer.assert_awaited_once()
    _, kwargs = callback.message.answer.call_args
    assert "reply_markup" in kwargs
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_create_post_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2004, CALLBACK_CREATE_POST)

    await on_menu_create_post(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_menu_text_hint_sends_hint_text(db_path):
    add_user(db_path, 2005)
    callback = _make_callback(2005, CALLBACK_TEXT_HINT)

    await on_menu_text_hint(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("menu_text_generation_hint", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_text_hint_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2006, CALLBACK_TEXT_HINT)

    await on_menu_text_hint(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.start import PhotoGenStates, on_menu_photo_gen, on_photo_gen_description
from bot.keyboards.start import CALLBACK_PHOTO_GEN
from bot.services import ai_gateway, content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.users import get_pending_media


def _make_state(telegram_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_description_message(telegram_id: int, text: str, language_code: str = "ru"):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    message.text = text
    message.chat = SimpleNamespace(id=telegram_id)
    return message


def _fake_sent_photo_message(file_id: str = "telegram-cdn-file-id"):
    return SimpleNamespace(photo=[SimpleNamespace(file_id=file_id)])


@pytest.mark.asyncio
async def test_menu_photo_gen_prompts_for_description_and_sets_state(db_path):
    add_user(db_path, 3001)
    state = _make_state(3001)
    callback = _make_callback(3001, CALLBACK_PHOTO_GEN)

    await on_menu_photo_gen(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("photo_gen_prompt", "ru"))
    assert await state.get_state() == PhotoGenStates.waiting_for_description.state
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_photo_gen_blocked_when_not_whitelisted(db_path):
    state = _make_state(3002)
    callback = _make_callback(3002, CALLBACK_PHOTO_GEN)

    await on_menu_photo_gen(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_photo_gen_description_generates_and_attaches_image(db_path, monkeypatch):
    add_user(db_path, 3003)
    state = _make_state(3003)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value="https://vendor.example/generated.png")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    message = _make_description_message(3003, "закат над морем, тёплые тона")
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_photo_gen_description(message, state, db_path, bot)

    mock_prompt.assert_awaited_once_with("закат над морем, тёплые тона")
    mock_generate_image.assert_awaited_once_with("a vivid english prompt")
    bot.send_photo.assert_awaited_once()
    args, kwargs = bot.send_photo.call_args
    assert args[0] == 3003
    assert kwargs["photo"] == "https://vendor.example/generated.png"
    assert get_pending_media(db_path, 3003) == ("telegram-cdn-file-id", "photo")
    assert await state.get_state() is None
    message.answer.assert_awaited_once_with(get_string("photo_gen_ready", "ru"))


@pytest.mark.asyncio
async def test_photo_gen_description_empty_text_reprompts_without_calling_ai(db_path, monkeypatch):
    state = _make_state(3004)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock()
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)

    message = _make_description_message(3004, None)
    bot = AsyncMock()

    await on_photo_gen_description(message, state, db_path, bot)

    mock_prompt.assert_not_awaited()
    message.answer.assert_awaited_once_with(get_string("photo_gen_prompt", "ru"))
    assert await state.get_state() == PhotoGenStates.waiting_for_description.state


@pytest.mark.asyncio
async def test_photo_gen_description_ai_error_replies_friendly_message(db_path, monkeypatch):
    state = _make_state(3005)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)

    message = _make_description_message(3005, "закат")
    bot = AsyncMock()

    await on_photo_gen_description(message, state, db_path, bot)

    message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    assert get_pending_media(db_path, 3005) is None
    assert await state.get_state() == PhotoGenStates.waiting_for_description.state
