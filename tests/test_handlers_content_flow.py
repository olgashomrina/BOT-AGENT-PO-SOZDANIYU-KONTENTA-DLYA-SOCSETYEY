from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.content import detect_input_type, route_content
from bot.locales.loader import get_string


def _make_message(
    telegram_id: int = 111,
    text: str | None = None,
    voice=None,
    audio=None,
    entities=None,
    caption=None,
    caption_entities=None,
):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.text = text
    message.voice = voice
    message.audio = audio
    message.entities = entities
    message.caption = caption
    message.caption_entities = caption_entities
    return message


def test_detects_link_from_plain_url_in_text():
    message = _make_message(text="Посмотри вот это: https://example.com/article")

    assert detect_input_type(message) == "link"


def test_detects_link_from_url_entity():
    entity = SimpleNamespace(type="url")
    message = _make_message(text="example.com/article", entities=[entity])

    assert detect_input_type(message) == "link"


def test_detects_voice():
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    assert detect_input_type(message) == "voice"


def test_detects_audio():
    message = _make_message(audio=SimpleNamespace(file_id="abc"))

    assert detect_input_type(message) == "voice"


def test_detects_plain_text():
    message = _make_message(text="Просто текст без ссылок и голоса")

    assert detect_input_type(message) == "text"


@pytest.mark.asyncio
async def test_route_content_link(db_path):
    message = _make_message(text="https://example.com/article")

    await route_content(message, db_path)

    message.answer.assert_awaited_once_with(get_string("content_stub_link", "ru"))


@pytest.mark.asyncio
async def test_route_content_voice(db_path):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    await route_content(message, db_path)

    message.answer.assert_awaited_once_with(get_string("content_stub_voice", "ru"))


@pytest.mark.asyncio
async def test_route_content_text(db_path):
    message = _make_message(text="Просто текст")

    await route_content(message, db_path)

    message.answer.assert_awaited_once_with(get_string("content_stub_text", "ru"))
