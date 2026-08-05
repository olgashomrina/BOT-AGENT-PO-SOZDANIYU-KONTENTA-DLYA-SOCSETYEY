from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, call

import pytest

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.start import cmd_help, cmd_start
from bot.locales.loader import get_string
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
)


@pytest.fixture(autouse=True)
def _required_env(monkeypatch):
    # Several handlers here reach load_settings() — the digest and photo-gen
    # message handlers do it through the quota guard (bot/handlers/guards.py).
    # Without these the suite only passes on a machine that happens to have a
    # real .env next to it, and fails in CI, which has none.
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")



def _make_message(telegram_id: int, language_code: str | None, text: str | None = "/start"):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    message.text = text
    return message


def _make_state(telegram_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


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
    state = _make_state(111)

    await cmd_start(message, state, db_path)

    assert get_interface_language(db_path, 111) == "vi"
    message.answer.assert_has_calls([*_greeting_calls("vi"), *_onboarding_calls("vi")])


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_for_unsupported_language_code(db_path):
    message = _make_message(222, "fr")
    state = _make_state(222)

    await cmd_start(message, state, db_path)

    assert get_interface_language(db_path, 222) == "ru"
    message.answer.assert_has_calls([*_greeting_calls("ru"), *_onboarding_calls("ru")])


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_when_language_code_missing(db_path):
    message = _make_message(333, None)
    state = _make_state(333)

    await cmd_start(message, state, db_path)

    assert get_interface_language(db_path, 333) == "ru"


@pytest.mark.asyncio
async def test_new_user_sees_greeting_menu_and_all_three_onboarding_messages(db_path):
    message = _make_message(777, "ru")
    state = _make_state(777)

    await cmd_start(message, state, db_path)

    assert message.answer.await_count == 5
    message.answer.assert_has_calls([*_greeting_calls("ru"), *_onboarding_calls("ru")])


@pytest.mark.asyncio
async def test_new_user_start_persists_onboarding_shown_flag(db_path):
    message = _make_message(888, "ru")
    state = _make_state(888)

    await cmd_start(message, state, db_path)

    assert get_onboarding_shown(db_path, 888) is True


@pytest.mark.asyncio
async def test_second_start_from_same_new_user_does_not_repeat_onboarding(db_path):
    message = _make_message(999, "ru")
    state = _make_state(999)

    await cmd_start(message, state, db_path)
    message.answer.reset_mock()
    await cmd_start(message, state, db_path)

    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("ru"))


@pytest.mark.asyncio
async def test_returning_user_start_shows_greeting_and_menu_only(db_path):
    set_interface_language(db_path, 444, "en")
    set_onboarding_shown(db_path, 444, True)
    message = _make_message(444, "vi")
    state = _make_state(444)

    await cmd_start(message, state, db_path)

    assert get_interface_language(db_path, 444) == "en"
    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("en"))


@pytest.mark.asyncio
async def test_persistent_start_button_text_triggers_same_flow_as_command(db_path):
    set_interface_language(db_path, 1010, "ru")
    set_onboarding_shown(db_path, 1010, True)
    message = _make_message(1010, "ru", text=get_string("start_button_label", "ru"))
    state = _make_state(1010)

    await cmd_start(message, state, db_path)

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


from bot.handlers.start import (
    on_menu_capabilities,
    on_menu_create_post,
    on_menu_news_digest,
    on_menu_text_hint,
)
from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_NEWS_DIGEST,
    CALLBACK_TEXT_HINT,
)
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


from bot.handlers.start import DigestStates, on_digest_topic_input, on_menu_digest_set_topic
from bot.keyboards.start import CALLBACK_DIGEST_SET_TOPIC
from bot.services import digest as digest_service
from bot.storage.users import get_digest_topic, set_digest_topic


@pytest.mark.asyncio
async def test_menu_news_digest_prompts_for_topic_when_none_saved(db_path):
    add_user(db_path, 2007)
    callback = _make_callback(2007, CALLBACK_NEWS_DIGEST)
    state = _make_state(2007)

    await on_menu_news_digest(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(
        get_string("digest_prompt_no_topic", "ru"), reply_markup=ANY
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_news_digest_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2008, CALLBACK_NEWS_DIGEST)
    state = _make_state(2008)

    await on_menu_news_digest(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_menu_news_digest_builds_digest_immediately_when_topic_saved(db_path, monkeypatch):
    # check_limit_or_reply (bot/handlers/guards.py) calls load_settings()
    # internally, same as test_menu_create_post_shows_submenu_keyboard above —
    # required env vars must be set or ConfigError raises before the handler
    # body even runs.
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    add_user(db_path, 2009)
    set_digest_topic(db_path, 2009, "психология")
    callback = _make_callback(2009, CALLBACK_NEWS_DIGEST)
    state = _make_state(2009)

    fake_result = digest_service.DigestResult(topic="психология", news=[], papers=[], methods_summary=None)
    mock_build = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(digest_service, "build_digest", mock_build)

    await on_menu_news_digest(callback, state, db_path)

    mock_build.assert_awaited_once_with("психология")
    assert callback.message.answer.await_count == 2
    first_call_text = callback.message.answer.await_args_list[0].args[0]
    assert first_call_text == digest_service.format_digest_message(fake_result, "ru")
    second_call_args, second_call_kwargs = callback.message.answer.await_args_list[1]
    assert second_call_args[0] == get_string("digest_change_topic_prompt", "ru")
    assert "reply_markup" in second_call_kwargs
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_digest_set_topic_sends_force_reply_and_sets_state(db_path):
    from aiogram.types import ForceReply

    add_user(db_path, 2010)
    state = _make_state(2010)
    callback = _make_callback(2010, CALLBACK_DIGEST_SET_TOPIC)

    await on_menu_digest_set_topic(callback, state, db_path)

    callback.message.answer.assert_awaited_once()
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("digest_topic_input_prompt", "ru")
    assert isinstance(kwargs["reply_markup"], ForceReply)
    assert await state.get_state() == DigestStates.waiting_for_topic.state
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_digest_set_topic_blocked_when_not_whitelisted(db_path):
    state = _make_state(2011)
    callback = _make_callback(2011, CALLBACK_DIGEST_SET_TOPIC)

    await on_menu_digest_set_topic(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_digest_topic_input_saves_topic_and_sends_digest(db_path, monkeypatch):
    state = _make_state(2012)
    await state.update_data(language="ru")
    await state.set_state(DigestStates.waiting_for_topic)

    fake_result = digest_service.DigestResult(topic="дизайн интерьеров", news=[], papers=[], methods_summary=None)
    mock_build = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(digest_service, "build_digest", mock_build)

    message = _make_description_message(2012, "дизайн интерьеров")

    await on_digest_topic_input(message, state, db_path)

    assert get_digest_topic(db_path, 2012) == "дизайн интерьеров"
    mock_build.assert_awaited_once_with("дизайн интерьеров")
    assert await state.get_state() is None
    assert message.answer.await_count == 3
    first_call_text = message.answer.await_args_list[0].args[0]
    assert first_call_text == get_string("digest_topic_saved", "ru", topic="дизайн интерьеров")
    second_call_text = message.answer.await_args_list[1].args[0]
    assert second_call_text == digest_service.format_digest_message(fake_result, "ru")
    third_call_args, third_call_kwargs = message.answer.await_args_list[2]
    assert third_call_args[0] == get_string("digest_change_topic_prompt", "ru")
    assert "reply_markup" in third_call_kwargs


@pytest.mark.asyncio
async def test_digest_topic_input_reprompts_on_empty_text(db_path, monkeypatch):
    from aiogram.types import ForceReply

    state = _make_state(2013)
    await state.update_data(language="ru")
    await state.set_state(DigestStates.waiting_for_topic)
    mock_build = AsyncMock()
    monkeypatch.setattr(digest_service, "build_digest", mock_build)

    message = _make_description_message(2013, None)

    await on_digest_topic_input(message, state, db_path)

    mock_build.assert_not_awaited()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("digest_topic_input_prompt", "ru")
    assert isinstance(kwargs["reply_markup"], ForceReply)
    assert await state.get_state() == DigestStates.waiting_for_topic.state


@pytest.mark.asyncio
async def test_start_clears_fsm_state_stuck_in_digest_topic_input(db_path):
    state = _make_state(2014)
    await state.update_data(language="ru")
    await state.set_state(DigestStates.waiting_for_topic)
    message = _make_message(2014, "ru")

    await cmd_start(message, state, db_path)

    assert await state.get_state() is None


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


from aiogram.types import BufferedInputFile

from bot.handlers.start import PhotoGenStates, on_menu_photo_gen, on_photo_gen_description
from bot.keyboards.start import CALLBACK_PHOTO_GEN
from bot.services import ai_gateway, content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.image_prompts import claim_image_prompt
from bot.storage.limits import get_daily_image_count, increment_image_usage
from bot.storage.users import get_pending_media


def _make_description_message(telegram_id: int, text: str, language_code: str = "ru"):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    message.text = text
    message.chat = SimpleNamespace(id=telegram_id)
    return message


def _fake_sent_photo_message(file_id: str = "telegram-cdn-file-id", message_id: int = 5000):
    return SimpleNamespace(photo=[SimpleNamespace(file_id=file_id)], message_id=message_id)


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
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
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
    assert isinstance(kwargs["photo"], BufferedInputFile)
    assert kwargs["photo"].data == b"fake-png-bytes"
    assert get_pending_media(db_path, 3003) == ("telegram-cdn-file-id", "photo")
    assert await state.get_state() is None
    message.answer.assert_awaited_once_with(get_string("photo_gen_ready", "ru"))


@pytest.mark.asyncio
async def test_photo_gen_description_counts_towards_daily_image_budget(db_path, monkeypatch):
    add_user(db_path, 3009)
    state = _make_state(3009)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    monkeypatch.setattr(content_generator, "generate_image_prompt", AsyncMock(return_value="p"))
    monkeypatch.setattr(ai_gateway, "generate_image", AsyncMock(return_value=b"fake-png-bytes"))

    message = _make_description_message(3009, "закат над морем")
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message())

    await on_photo_gen_description(message, state, db_path, bot)

    assert get_daily_image_count(db_path, 3009) == 1


@pytest.mark.asyncio
async def test_photo_gen_description_refused_once_daily_image_limit_reached(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_IMAGE_LIMIT", "2")
    add_user(db_path, 3010)
    state = _make_state(3010)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    for _ in range(2):
        increment_image_usage(db_path, 3010)

    mock_prompt = AsyncMock(return_value="p")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    message = _make_description_message(3010, "закат над морем")
    bot = AsyncMock()

    await on_photo_gen_description(message, state, db_path, bot)

    mock_prompt.assert_not_awaited()
    mock_generate_image.assert_not_awaited()
    bot.send_photo.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        get_string("error_daily_image_limit", "ru", limit=2)
    )


@pytest.mark.asyncio
async def test_photo_gen_description_attaches_upgrade_button_and_stores_prompt(db_path, monkeypatch):
    from bot.keyboards.refine import build_image_upgrade_keyboard

    add_user(db_path, 3005)
    state = _make_state(3005)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value=b"fake-png-bytes")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    message = _make_description_message(3005, "горы на рассвете")
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_photo_gen_description(message, state, db_path, bot)

    _, kwargs = bot.send_photo.call_args
    expected_keyboard = build_image_upgrade_keyboard("ru")
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
        expected_keyboard.inline_keyboard[0][0].callback_data
    )
    assert claim_image_prompt(db_path, 3005, 5000) == "a vivid english prompt"


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


@pytest.mark.asyncio
async def test_start_clears_fsm_state_stuck_in_photo_gen(db_path):
    state = _make_state(3006)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)
    message = _make_message(3006, "ru")

    await cmd_start(message, state, db_path)

    assert await state.get_state() is None


from bot.services import digest as digest_service
from bot.storage.users import set_digest_topic
from bot.storage.whitelist import add_user


# on_menu_news_digest goes through check_limit_or_reply (bot/handlers/guards.py), which calls
# load_settings() — without these the whole test errors on missing env.
@pytest.fixture
def _settings_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _sample_digest_result():
    return digest_service.DigestResult(
        topic="ИИ",
        news=[digest_service.DigestItem(title="Новость 1", url="https://n1")],
        papers=[digest_service.DigestItem(title="Статья 1", url="https://p1")],
        methods_summary="Новая методика X.",
    )


def _make_digest_callback(telegram_id: int):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_menu_news_digest_stores_items_in_fsm(db_path, monkeypatch, _settings_env):
    telegram_id = 555
    add_user(db_path, telegram_id)
    set_digest_topic(db_path, telegram_id, "ИИ")
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)

    await on_menu_news_digest(_make_digest_callback(telegram_id), state, db_path)

    data = await state.get_data()
    assert data["digest_items"] == ["Новость 1", "Статья 1", "Новая методика X."]


@pytest.mark.asyncio
async def test_digest_topic_input_stores_items_in_fsm(db_path, monkeypatch):
    telegram_id = 556
    add_user(db_path, telegram_id)
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)
    message = _make_message(telegram_id, "ru", text="ИИ")

    await on_digest_topic_input(message, state, db_path)

    data = await state.get_data()
    assert data["digest_items"] == ["Новость 1", "Статья 1", "Новая методика X."]


@pytest.mark.asyncio
async def test_menu_news_digest_starts_generation_at_one(db_path, monkeypatch, _settings_env):
    telegram_id = 557
    add_user(db_path, telegram_id)
    set_digest_topic(db_path, telegram_id, "ИИ")
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)

    await on_menu_news_digest(_make_digest_callback(telegram_id), state, db_path)

    data = await state.get_data()
    assert data["digest_generation"] == 1


@pytest.mark.asyncio
async def test_menu_news_digest_increments_generation_on_second_delivery(
    db_path, monkeypatch, _settings_env
):
    # This is the path the reported bug walks: collect a digest (generation
    # 1), collect another (generation 2) — the numbered buttons under the
    # first message must stop resolving against whichever digest is current.
    telegram_id = 558
    add_user(db_path, telegram_id)
    set_digest_topic(db_path, telegram_id, "ИИ")
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)

    await on_menu_news_digest(_make_digest_callback(telegram_id), state, db_path)
    await on_menu_news_digest(_make_digest_callback(telegram_id), state, db_path)

    data = await state.get_data()
    assert data["digest_generation"] == 2


@pytest.mark.asyncio
async def test_digest_topic_input_starts_generation_at_one(db_path, monkeypatch):
    telegram_id = 559
    add_user(db_path, telegram_id)
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)
    message = _make_message(telegram_id, "ru", text="ИИ")

    await on_digest_topic_input(message, state, db_path)

    data = await state.get_data()
    assert data["digest_generation"] == 1


@pytest.mark.asyncio
async def test_digest_topic_input_increments_generation_on_second_delivery(db_path, monkeypatch):
    # Both delivery paths must bump the generation: this is the topic-change
    # path (ForceReply -> on_digest_topic_input), the other place a digest
    # can be delivered besides the menu button covered above.
    telegram_id = 560
    add_user(db_path, telegram_id)
    monkeypatch.setattr(
        digest_service, "build_digest", AsyncMock(return_value=_sample_digest_result())
    )
    state = _make_state(telegram_id)
    first_message = _make_message(telegram_id, "ru", text="ИИ")
    second_message = _make_message(telegram_id, "ru", text="Кулинария")
    await state.set_state(DigestStates.waiting_for_topic)

    await on_digest_topic_input(first_message, state, db_path)
    await state.set_state(DigestStates.waiting_for_topic)
    await on_digest_topic_input(second_message, state, db_path)

    data = await state.get_data()
    assert data["digest_generation"] == 2


@pytest.mark.asyncio
async def test_news_digest_clears_a_leftover_collecting_state(db_path, monkeypatch):
    # Reached from the style-ready keyboard (bot/keyboards/style.py), where a
    # sample-collection state is still set: leaving it would turn the user's
    # next plain message into another style sample.
    from bot.handlers.authorpost import AuthorPostStates

    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    telegram_id = 2014
    add_user(db_path, telegram_id)
    set_digest_topic(db_path, telegram_id, "ИИ")
    monkeypatch.setattr(
        digest_service,
        "build_digest",
        AsyncMock(
            return_value=digest_service.DigestResult(
                topic="ИИ", news=[], papers=[], methods_summary=None
            )
        ),
    )
    state = _make_state(telegram_id)
    await state.set_state(AuthorPostStates.collecting_examples)
    callback = _make_callback(telegram_id, CALLBACK_NEWS_DIGEST)

    await on_menu_news_digest(callback, state, db_path)

    assert await state.get_state() is None


from bot.handlers.start import on_menu_post_length, on_set_post_length
from bot.keyboards.start import CALLBACK_POST_LENGTH_SET_PREFIX
from bot.storage.users import get_post_length, set_post_length
from bot.storage.whitelist import add_user


def _make_length_callback(telegram_id: int, data: str, language_code: str = "ru"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_post_length_screen_shows_the_current_choice(db_path):
    add_user(db_path, 111)
    set_post_length(db_path, 111, "expanded")
    callback = _make_length_callback(111, "menu:post_length")

    await on_menu_post_length(callback, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("post_length_prompt", "ru")
    keyboard = kwargs["reply_markup"]
    marked = [row[0].text for row in keyboard.inline_keyboard if row[0].text.startswith("✓")]
    assert marked == [f"✓ {get_string('post_length_expanded', 'ru')}"]


@pytest.mark.asyncio
async def test_choosing_a_preset_saves_it(db_path):
    add_user(db_path, 111)
    callback = _make_length_callback(111, f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short")

    await on_set_post_length(callback, db_path)

    assert get_post_length(db_path, 111) == "short"


@pytest.mark.asyncio
async def test_choosing_a_preset_confirms_and_returns_to_the_create_post_screen(db_path):
    add_user(db_path, 111)
    callback = _make_length_callback(111, f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short")

    await on_set_post_length(callback, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string(
        "post_length_saved", "ru", value=get_string("post_length_short", "ru")
    )
    callbacks = [
        button.callback_data
        for row in kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert CALLBACK_TEXT_HINT in callbacks
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_unknown_preset_key_does_not_change_the_setting(db_path):
    # Значение callback_data приходит от клиента, а клиент можно подменить.
    add_user(db_path, 111)
    set_post_length(db_path, 111, "medium")
    callback = _make_length_callback(111, f"{CALLBACK_POST_LENGTH_SET_PREFIX}:bogus")

    await on_set_post_length(callback, db_path)

    assert get_post_length(db_path, 111) == "medium"
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_length_screen_blocked_for_a_user_not_in_the_whitelist(db_path, monkeypatch):
    monkeypatch.setenv("WHITELIST_ENABLED", "true")
    callback = _make_length_callback(999, "menu:post_length")

    await on_menu_post_length(callback, db_path)

    keyboards = [
        kwargs.get("reply_markup") for _, kwargs in callback.message.answer.call_args_list
    ]
    assert all(keyboard is None for keyboard in keyboards)
