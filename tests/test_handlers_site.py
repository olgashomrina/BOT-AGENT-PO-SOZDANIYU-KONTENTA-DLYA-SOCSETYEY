# tests/test_handlers_site.py
from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.site import cmd_site, on_site_pull, on_site_push
from bot.keyboards.site import PILOT_BLOCK, PILOT_PAGE
from bot.locales.loader import get_string
from bot.services import content_generator
from bot.storage.limits import get_daily_count
from bot.storage.site_content import get_site_content, upsert_site_content
from bot.storage.users import get_pending_media, set_pending_media
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _ai_gateway_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    # bot.config.load_settings() calls load_dotenv(dotenv_path=None,
    # override=False), which does an upward directory search from cwd for a
    # ".env" file. This worktree is nested inside the real project directory,
    # which has its own (gitignored) local-dev .env one level up containing a
    # real MINI_APP_URL value. Without this, monkeypatch.delenv("MINI_APP_URL")
    # in tests below would get silently refilled by that ambient file (delenv
    # makes the var absent, so override=False no longer blocks dotenv from
    # setting it), making test outcomes depend on this machine's local
    # filesystem rather than on bot/handlers/site.py's actual logic. Verified:
    # tests/test_config.py works around the same hazard by always passing an
    # explicit (missing) env_file to load_settings().
    monkeypatch.setattr("bot.config.load_dotenv", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_message(telegram_id: int = TELEGRAM_ID):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    return message


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = ""):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_cmd_site_shows_menu_with_mini_app_button(db_path, monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "https://olgashomrina.github.io/my-lending-test/")
    message = _make_message()

    await cmd_site(message, db_path)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("site_menu_intro", "ru")
    keyboard = kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


@pytest.mark.asyncio
async def test_cmd_site_shows_menu_without_mini_app_button_when_unset(db_path, monkeypatch):
    monkeypatch.delenv("MINI_APP_URL", raising=False)
    message = _make_message()

    await cmd_site(message, db_path)

    args, kwargs = message.answer.call_args
    keyboard = kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 1


@pytest.mark.asyncio
async def test_site_pull_with_content_feeds_finish_and_sets_pending_media(db_path, monkeypatch):
    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, "Текст с сайта", "site-file-id", "/media/services/card_1.jpg")
    mock_generate = AsyncMock(return_value=["Сгенерированный вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    state = _make_state()
    callback = _make_callback(data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    mock_generate.assert_awaited()
    assert mock_generate.await_args_list[0].args[0] == "Текст с сайта"
    assert get_pending_media(db_path, TELEGRAM_ID) == ("site-file-id", "photo")
    assert get_daily_count(db_path, TELEGRAM_ID) == 1
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_site_pull_with_no_content_shows_empty_message(db_path):
    state = _make_state()
    callback = _make_callback(data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("site_pull_empty", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_site_pull_blocked_when_not_whitelisted(db_path):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_site_pull_blocked_when_daily_limit_exceeded(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "0")
    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, "Текст с сайта", None, None)
    state = _make_state()
    callback = _make_callback(data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_daily_limit_exceeded", "ru"))


@pytest.mark.asyncio
async def test_site_push_stores_text_and_downloads_photo(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_MEDIA_DIR", str(tmp_path / "media"))
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await state.update_data(language="ru")
    callback = _make_callback(data="site:push:telegram:1")
    callback.message.text = "Готовый текст карточки"
    bot = AsyncMock()

    await on_site_push(callback, state, db_path, bot)

    bot.download.assert_awaited_once()
    content = get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK)
    assert content.text == "Готовый текст карточки"
    assert content.photo_file_id == "photo-file-id"
    assert content.photo_static_path == f"/media/{PILOT_PAGE}/{PILOT_BLOCK}.jpg"
    callback.message.answer.assert_awaited_once_with(get_string("site_push_success", "ru"))


@pytest.mark.asyncio
async def test_site_push_without_pending_media_keeps_existing_photo(db_path):
    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, "Старый текст", "old-file-id", "/media/services/card_1.jpg")
    state = _make_state()
    await state.update_data(language="ru")
    callback = _make_callback(data="site:push:telegram:1")
    callback.message.text = "Новый текст без фото"
    bot = AsyncMock()

    await on_site_push(callback, state, db_path, bot)

    bot.download.assert_not_awaited()
    content = get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK)
    assert content.text == "Новый текст без фото"
    assert content.photo_file_id == "old-file-id"
    assert content.photo_static_path == "/media/services/card_1.jpg"


@pytest.mark.asyncio
async def test_site_push_photo_download_failure_shows_friendly_error(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_MEDIA_DIR", str(tmp_path / "media"))
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await state.update_data(language="ru")
    callback = _make_callback(data="site:push:telegram:1")
    callback.message.text = "Текст"
    bot = AsyncMock()
    bot.download = AsyncMock(side_effect=OSError("disk full"))

    await on_site_push(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("site_push_photo_failed", "ru"))
    assert get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK) is None


@pytest.mark.asyncio
async def test_site_push_blocked_when_not_whitelisted(db_path):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data="site:push:telegram:1")
    callback.message.text = "Текст"
    bot = AsyncMock()

    await on_site_push(callback, state, db_path, bot)

    bot.download.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    assert get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK) is None
