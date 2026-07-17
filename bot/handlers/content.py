from __future__ import annotations

import re
from typing import Literal

from aiogram import Router
from aiogram.types import Message

from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.storage.users import get_interface_language

router = Router(name="content")

_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")

InputType = Literal["link", "voice", "text"]

_STUB_KEYS: dict[InputType, str] = {
    "link": "content_stub_link",
    "voice": "content_stub_voice",
    "text": "content_stub_text",
}


def detect_input_type(message: Message) -> InputType:
    if message.voice is not None or message.audio is not None:
        return "voice"

    text = message.text or message.caption
    if text and _URL_PATTERN.search(text):
        return "link"

    entities = (message.entities or []) + (message.caption_entities or [])
    if any(entity.type in ("url", "text_link") for entity in entities):
        return "link"

    return "text"


@router.message()
async def route_content(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    input_type = detect_input_type(message)
    await message.answer(get_string(_STUB_KEYS[input_type], language))
