from __future__ import annotations

import trafilatura
from aiogram import Bot
from aiogram.types import Message

from bot.services import ai_gateway


class LinkExtractionError(Exception):
    """Raised when an article's text can't be extracted from a URL.

    Deliberately not part of the AI Gateway exception hierarchy — this is a
    trafilatura/HTTP-fetch concern, not an AI call (see Plan.md 5.1).
    """


def extract_from_link(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as exc:
        raise LinkExtractionError(f"Не удалось загрузить страницу: {url}") from exc

    if not downloaded:
        raise LinkExtractionError(f"Не удалось загрузить страницу: {url}")

    text = trafilatura.extract(downloaded)
    if not text or not text.strip():
        raise LinkExtractionError(f"Не удалось извлечь текст со страницы: {url}")

    return text


async def handle_voice(bot: Bot, message: Message, language_hint: str | None = None) -> str:
    file = message.voice or message.audio
    buffer = await bot.download(file)
    audio_bytes = buffer.read()
    return await ai_gateway.transcribe(audio_bytes, language_hint=language_hint)
