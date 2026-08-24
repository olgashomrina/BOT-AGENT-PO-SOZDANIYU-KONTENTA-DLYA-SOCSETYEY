"""Ведение задания речи от текста до готового видео.

Про aiogram здесь нет ни строчки: картинка и звук приходят байтами, готовое
видео уходит байтами. Всё телеграмное живёт в воркере и хендлерах — благодаря
этому весь денежный путь тестируется без сети и без бота.

Задание живёт в SQLite, а не в состоянии диалога. Причина денежная: рестарт
бота посреди оплаченного рендера — это выброшенные деньги.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME
from bot.services.avatar_gateway import poll_render, start_render
from bot.services.cost_tracker import video_cost
from bot.services.ffmpeg_tools import probe_duration
from bot.storage.costs import record_cost
from bot.storage.render_usage import add_usage, seconds_left
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    STATUS_VOICED,
    SpeechJob,
    update_job,
)

logger = logging.getLogger(LOGGER_NAME)

REASON_TOO_LONG = "too_long"
REASON_LIMIT = "limit"

OPERATION_RENDER = "avatar_render"


class RenderRefused(Exception):
    """Отказ до обращения к провайдеру, то есть с нулевым расходом.

    `detail` — число, которое пользователю надо назвать: предел формата
    в секундах либо остаток месячного лимита.
    """

    def __init__(self, reason: str, detail: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


async def attach_audio(db_path: str, job_id: int, audio_bytes: bytes) -> float:
    """Положить озвучку к заданию и замерить её длительность.

    Порядок именно такой: сначала звук и его фактическая длительность, потом
    всё остальное. Длительность синтеза по числу символов заранее точно не
    предсказывается, а от неё зависят и допустимость, и цена.
    """
    settings = load_settings()
    audio_path = _tmp_path(".mp3")
    pathlib.Path(audio_path).write_bytes(audio_bytes)

    duration = await probe_duration(audio_path)
    if duration > settings.avatar_max_seconds:
        pathlib.Path(audio_path).unlink(missing_ok=True)
        raise RenderRefused(REASON_TOO_LONG, settings.avatar_max_seconds)

    update_job(
        db_path,
        job_id,
        status=STATUS_VOICED,
        audio_path=audio_path,
        audio_duration_sec=duration,
    )
    return duration


async def request_render(
    db_path: str, job_id: int, image_bytes: bytes, look_id: int
) -> None:
    """Запустить платный рендер, проверив лимит до обращения к провайдеру."""
    settings = load_settings()
    from bot.storage.speech_jobs import get_job

    job = get_job(db_path, job_id)
    if job is None or job.audio_path is None or job.audio_duration_sec is None:
        raise RenderRefused(REASON_TOO_LONG, settings.avatar_max_seconds)

    needed = int(round(job.audio_duration_sec))
    left = seconds_left(
        db_path, job.telegram_id, settings.avatar_monthly_seconds_limit
    )
    if needed > left:
        # Единственное место, где отказ обязан случиться раньше вызова:
        # после него секунды уже оплачены, отказывать поздно.
        raise RenderRefused(REASON_LIMIT, left)

    audio_bytes = pathlib.Path(job.audio_path).read_bytes()
    task_uuid = await start_render(image_bytes, audio_bytes)

    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id=task_uuid,
        look_id=look_id,
        error=None,
    )


async def collect_ready(db_path: str, job: SpeechJob) -> bytes | None:
    """Опросить провайдера. Байты — когда готово, None — пока нет или отказ.

    Списание идёт здесь и ровно один раз: статус уходит из `rendering` тем же
    вызовом, а воркер выбирает задания только по этому статусу. Задание не в
    `rendering` — уже обработано (или ещё не запущено) — опрос повторно не
    идёт, иначе повторный опрос того же провайдерского taskUUID списал бы
    деньги второй раз.
    """
    if job.status != STATUS_RENDERING or job.provider_task_id is None:
        return None

    status = await poll_render(job.provider_task_id)

    if status.failed:
        logger.warning(
            "Avatar render failed",
            extra={"user_id": job.telegram_id, "operation": "speech_pipeline"},
        )
        update_job(db_path, job.id, status=STATUS_FAILED, error=status.error)
        return None

    if not status.done or status.video_bytes is None:
        return None

    settings = load_settings()
    seconds = int(round(job.audio_duration_sec or 0))
    cost_rub = (
        status.cost_usd * settings.usd_rub_rate
        if status.cost_usd is not None
        # Провайдер не вернул фактическую цену — считаем по замерам. Ноль
        # писать нельзя: отчёт показал бы бесплатный рендер.
        else video_cost(settings.avatar_model, seconds)
    )

    add_usage(db_path, job.telegram_id, seconds, cost_rub)
    record_cost(
        db_path,
        job.telegram_id,
        OPERATION_RENDER,
        settings.avatar_model,
        cost_rub,
    )
    update_job(db_path, job.id, status=STATUS_READY, cost_rub=cost_rub)
    return status.video_bytes
