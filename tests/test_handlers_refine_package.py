from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.refine import on_refine_package
from bot.locales.loader import get_string
from bot.services import platform_package
from bot.storage.limits import get_daily_count
from bot.storage.users import set_channel_id
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


def _make_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _make_callback(variant_text: str = "Текст поста.\n\n#тег"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    callback.data = "refine:package:telegram:0"
    callback.message = AsyncMock()
    callback.message.text = variant_text
    return callback


def _sent_texts(callback) -> list[str]:
    return [call.args[0] for call in callback.message.answer.await_args_list]


async def _run(callback, db_path: str, state: FSMContext | None = None) -> None:
    state = state or _make_state()
    await state.update_data(language="ru")
    await on_refine_package(callback, state, db_path)


async def test_sends_an_intro_plus_one_message_per_external_platform(db_path):
    callback = _make_callback()

    await _run(callback, db_path)

    texts = _sent_texts(callback)
    assert len(texts) == 1 + len(platform_package.PROFILES)
    assert texts[0] == get_string("package_intro", "ru")
    for profile in platform_package.PROFILES.values():
        assert any(profile.display_name in text for text in texts[1:]), profile.display_name


async def test_each_platform_message_carries_the_post_text_and_its_media_spec(db_path):
    callback = _make_callback("Разбор новой статьи.\n\n#контент")

    await _run(callback, db_path)

    for text in _sent_texts(callback)[1:]:
        assert "Разбор новой статьи." in text
        assert "9:16" in text


async def test_youtube_message_includes_a_title_field(db_path):
    callback = _make_callback("Почему кружки дают охват. Дальше объяснение.")

    await _run(callback, db_path)

    youtube_message = next(
        text for text in _sent_texts(callback) if "<b>YouTube Shorts</b>" in text
    )
    assert get_string("package_title_label", "ru") in youtube_message
    assert "Почему кружки дают охват" in youtube_message


async def test_html_special_characters_in_the_post_are_escaped(db_path):
    # The copy block is sent with parse_mode=HTML; an unescaped "<" in the
    # post text would make Telegram reject the whole message.
    callback = _make_callback("Скидки <b>до 50%</b> & подарки")

    await _run(callback, db_path)

    instagram_message = next(
        text for text in _sent_texts(callback) if "<b>Instagram Reels</b>" in text
    )
    assert "&lt;b&gt;" in instagram_message
    assert "&amp;" in instagram_message
    assert "<b>до 50%</b>" not in instagram_message


async def test_the_bot_never_publishes_anywhere_itself(db_path):
    # The whole point of the pack: it hands the user files and text, and does
    # not touch any channel or external platform on their behalf.
    set_channel_id(db_path, TELEGRAM_ID, -1001234567890)
    callback = _make_callback()

    await _run(callback, db_path)

    callback.bot.send_message.assert_not_awaited()
    callback.bot.send_photo.assert_not_awaited()
    callback.bot.send_video.assert_not_awaited()


async def test_building_a_pack_costs_no_quota(db_path):
    # No AI call happens here — it is a local text transformation, so it must
    # not consume the user's daily allowance the way "Ещё вариант" does.
    callback = _make_callback()

    await _run(callback, db_path)

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


async def test_non_whitelisted_user_gets_nothing_but_the_refusal(db_path):
    callback = _make_callback()
    callback.from_user = SimpleNamespace(id=999, language_code="ru")

    await _run(callback, db_path)

    texts = _sent_texts(callback)
    assert texts == [get_string("error_not_whitelisted", "ru")]


async def test_empty_variant_text_does_not_crash(db_path):
    callback = _make_callback("")
    callback.message.text = None

    await _run(callback, db_path)

    assert callback.message.answer.await_count >= 1
