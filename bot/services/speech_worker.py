"""Фоновый опрос рендеров и доставка готовых кружков.

Асинхронная задача, стартующая вместе с ботом. На каждом тике берёт все
задания в статусе `rendering` — в том числе оставшиеся от прошлого запуска.
Это и есть страховка от рестарта: рендер уже оплачен, и потерять его нельзя.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import load_settings
from bot.locales.loader import DEFAULT_LANGUAGE, get_string
from bot.logging_config import LOGGER_NAME
from bot.services.speech_pipeline import collect_ready
from bot.services.video_note import to_video_note
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    get_job,
    get_jobs_by_status,
    update_job,
)
from bot.storage.users import get_interface_language

logger = logging.getLogger(LOGGER_NAME)

JOB_ID = "speech_render_poll"


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


def _language(db_path: str, telegram_id: int) -> str:
    return get_interface_language(db_path, telegram_id) or DEFAULT_LANGUAGE


def _rendered_video_path(job_id: int) -> pathlib.Path:
    """Путь к готовому ролику, оставленному оркестратором на диске.

    Формат `speech-{job_id}.mp4` — контракт с `speech_pipeline._video_path`
    (см. её докстринг): оркестратор этот файл не удаляет, потому что не знает
    о доставке. Удаление после успешной отправки — обязанность воркера;
    без неё временная папка растёт на один файл с каждым рендером.
    """
    return pathlib.Path(load_settings().tmp_media_dir) / f"speech-{job_id}.mp4"


async def _deliver(bot: Bot, db_path: str, job_id: int, video_bytes: bytes) -> None:
    raw_path = _tmp_path(".mp4")
    note_path = _tmp_path(".mp4")
    job = get_job(db_path, job_id)
    language = _language(db_path, job.telegram_id)
    try:
        pathlib.Path(raw_path).write_bytes(video_bytes)
        await to_video_note(raw_path, note_path)
        message = await bot.send_video_note(
            job.telegram_id, FSInputFile(note_path)
        )
        # file_id кэшируется: публикация в канал дальше бесплатна и мгновенна.
        # Статус пишем в ready и здесь: для только что оплаченного рендера
        # это переустановка того же значения, а для задания, подобранного
        # аварийным сбором по ready (см. process_rendering_jobs), это
        # единственное место, где статус вообще выставляется, — collect_ready
        # для такого задания просто отдаёт байты с диска, не трогая базу.
        update_job(
            db_path,
            job_id,
            status=STATUS_READY,
            result_file_id=message.video_note.file_id,
        )
        await bot.send_message(job.telegram_id, get_string("speech_ready", language))
        # Только теперь ролик доставлен и result_file_id записан: следующий
        # тик уже не станет искать его на диске для повторной отправки, и
        # файл оркестратора можно стереть. Удалить его раньше (например, в
        # finally ниже) значило бы потерять оплаченное видео, если отправка
        # только что упала, — RECOVERY-ветка collect_ready читает именно этот
        # файл.
        _rendered_video_path(job_id).unlink(missing_ok=True)
    finally:
        for path in (raw_path, note_path, job.audio_path):
            if path:
                pathlib.Path(path).unlink(missing_ok=True)


def _jobs_to_poll(db_path: str) -> list:
    """Задания, за судьбу которых воркер ещё отвечает.

    `rendering` — обычный случай, рендер идёт. `ready` без `result_file_id` —
    страховка от рестарта между записью статуса и отправкой: деньги уже
    списаны (Task 13, RECOVERY-ветка `collect_ready`), а кружок пользователь
    ещё не увидел. Задание `ready` со `result_file_id` уже доставлено —
    трогать его снова значило бы слать один и тот же кружок каждый тик.
    """
    ready_undelivered = [
        job
        for job in get_jobs_by_status(db_path, STATUS_READY)
        if job.result_file_id is None
    ]
    return get_jobs_by_status(db_path, STATUS_RENDERING) + ready_undelivered


async def process_rendering_jobs(bot: Bot, db_path: str) -> None:
    for job in _jobs_to_poll(db_path):
        try:
            video_bytes = await collect_ready(db_path, job)
        except Exception:
            # Один сломавшийся рендер не должен оставить соседние задания
            # висеть в rendering до следующего тика — и тем более навсегда.
            logger.warning(
                "Speech job polling failed",
                extra={"user_id": job.telegram_id, "operation": "speech_worker"},
                exc_info=True,
            )
            continue

        refreshed = get_job(db_path, job.id)
        if refreshed is not None and refreshed.status == STATUS_FAILED:
            await bot.send_message(
                job.telegram_id,
                get_string("speech_failed", _language(db_path, job.telegram_id)),
            )
            continue

        if video_bytes is None:
            continue

        try:
            await _deliver(bot, db_path, job.id, video_bytes)
        except Exception:
            logger.error(
                "Speech job delivery failed",
                extra={"user_id": job.telegram_id, "operation": "speech_worker"},
                exc_info=True,
            )
            update_job(
                db_path, job.id, status=STATUS_FAILED, error="доставка не удалась"
            )
            # Задание терминально: ни rendering-, ни ready-выборка больше его
            # не увидит, а значит и ролик оркестратора никто не прочитает —
            # держать его на диске дальше некому и незачем.
            _rendered_video_path(job.id).unlink(missing_ok=True)
            await bot.send_message(
                job.telegram_id,
                get_string("speech_failed", _language(db_path, job.telegram_id)),
            )


def build_speech_scheduler(
    bot: Bot, db_path: str, interval_seconds: int
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        process_rendering_jobs,
        trigger=IntervalTrigger(seconds=interval_seconds),
        args=[bot, db_path],
        id=JOB_ID,
        # Рендер идёт минутами: пропущенный тик наверстывается следующим,
        # и накапливать очередь одинаковых запусков незачем.
        coalesce=True,
        max_instances=1,
        misfire_grace_time=interval_seconds * 3,
    )
    return scheduler
