"""Распознавание речи на своём сервере, без внешнего сервиса.

Зачем: расшифровка была единственной операцией, ради которой оставался
vsegpt — тексты и картинки уехали на Runware, у которого распознавания речи
нет вовсе. Своя модель убирает и последнего поставщика: голос перестаёт
стоить за минуту и не зависит ни от чужого баланса, ни от блокировок.

Модель загружается на каждый вызов и после него выгружается. Держать её в
памяти постоянно было бы быстрее на пару секунд, но `small` занимает около
700 МБ, а на сервере 2 ГБ на всё вместе с ботом — постоянно занятые 700 МБ
превратили бы любой всплеск нагрузки в убийство процесса по нехватке памяти.
Две секунды на загрузку против такого риска — дешёвый размен.

Замеры на живой записи владельца (15.7 с речи, сервер 2 ядра / 2 ГБ,
05.08.2026): `small` — 3.2 с работы, 698 МБ пика, фраза расшифрована верно;
`base` — 1.2 с и 353 МБ, но "Создай мне пост" превратилось в "Создание пуст".
Поэтому по умолчанию `small`.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import TranscriptionError

logger = logging.getLogger(LOGGER_NAME)

# Отдельная функция, а не вызов внутри `_transcribe_sync`, чтобы тесты могли
# подменить загрузку модели: настоящая скачивает полгигабайта с Hugging Face.
def _load_model(model_name: str, compute_type: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="cpu", compute_type=compute_type)


def _transcribe_sync(
    audio_bytes: bytes, model_name: str, compute_type: str, language_hint: str | None
) -> str:
    model = _load_model(model_name, compute_type)
    segments, _info = model.transcribe(
        io.BytesIO(audio_bytes),
        language=language_hint,
        # beam_size=1 — жадный поиск. На замерах он давал ту же расшифровку,
        # что и поиск по лучу, но заметно быстрее; на двух ядрах это разница
        # между «подождать» и «долго ждать».
        beam_size=1,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


async def transcribe_locally(audio_bytes: bytes, language_hint: str | None = None) -> str:
    """Расшифровка голосового своими силами.

    Работа синхронная и небыстрая, поэтому уезжает в отдельный поток: иначе
    она заблокировала бы весь бот на всё время распознавания, и остальные
    пользователи ждали бы вместе с автором голосового.
    """
    settings = load_settings()
    started = time.monotonic()
    try:
        text = await asyncio.to_thread(
            _transcribe_sync,
            audio_bytes,
            settings.local_whisper_model,
            settings.local_whisper_compute_type,
            language_hint,
        )
    except Exception as exc:
        logger.error(
            "Local transcription failed: model=%s error_class=%s error_message=%s",
            settings.local_whisper_model,
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise TranscriptionError("Не удалось расшифровать голосовое сообщение") from exc

    duration_ms = (time.monotonic() - started) * 1000
    if not text:
        logger.warning(
            "Local transcription returned nothing: model=%s duration_ms=%.1f",
            settings.local_whisper_model,
            duration_ms,
        )
        raise TranscriptionError("Не удалось расшифровать голосовое сообщение")

    logger.info(
        "Local transcription succeeded: model=%s duration_ms=%.1f chars=%d",
        settings.local_whisper_model,
        duration_ms,
        len(text),
    )
    return text
