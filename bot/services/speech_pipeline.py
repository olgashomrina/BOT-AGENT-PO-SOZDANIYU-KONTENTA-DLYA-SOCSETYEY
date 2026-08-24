"""Ведение задания речи от текста до готового видео.

Про aiogram здесь нет ни строчки: картинка и звук приходят байтами, готовое
видео уходит байтами. Всё телеграмное живёт в воркере и хендлерах — благодаря
этому весь денежный путь тестируется без сети и без бота.

Задание живёт в SQLite, а не в состоянии диалога. Причина денежная: рестарт
бота посреди оплаченного рендера — это выброшенные деньги. По той же причине
готовый ролик сначала ложится на диск по имени, восстановимому из одного
`job.id`, и только потом списываются деньги: упавший между списанием и
отправкой бот иначе оставил бы пользователя с оплаченным и потерянным видео.

Секунды месячного лимита бронируются в момент запуска рендера, а не в момент
получения результата. Рендер идёт минутами; пока он идёт, его секунды обязаны
быть видны проверке лимита, иначе несколько запросов подряд каждый увидит
полный остаток и оплачены будут все.
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
REASON_NO_AUDIO = "no_audio"

OPERATION_RENDER = "avatar_render"


class RenderRefused(Exception):
    """Отказ до обращения к провайдеру, то есть с нулевым расходом.

    `detail` — число, которое пользователю надо назвать: предел формата
    в секундах либо остаток месячного лимита. Для отказа без числа (озвучки
    нет вовсе) там ноль.
    """

    def __init__(self, reason: str, detail: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _media_dir() -> pathlib.Path:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _tmp_path(suffix: str) -> str:
    return str(_media_dir() / f"{uuid.uuid4().hex}{suffix}")


def _video_path(job_id: int) -> pathlib.Path:
    """Имя готового ролика, восстановимое из одного `job.id`.

    Случайное имя пришлось бы хранить в базе, а колонки под него нет. Имя по
    номеру задания — то же самое знание, но без правки схемы.
    """
    return _media_dir() / f"speech-{job_id}.mp4"


def _stored_video(job_id: int) -> bytes | None:
    path = _video_path(job_id)
    return path.read_bytes() if path.exists() else None


def _reserved_seconds(job: SpeechJob) -> int:
    """Сколько секунд уже забронировано за этим заданием в `request_render`.

    Отдельной колонки под бронь нет, а бронируется ровно оценка по
    длительности озвучки — значит её и надо вычесть при сверке.
    """
    return int(round(job.audio_duration_sec or 0))


async def attach_audio(db_path: str, job_id: int, audio_bytes: bytes) -> float:
    """Положить озвучку к заданию и замерить её длительность.

    Порядок именно такой: сначала звук и его фактическая длительность, потом
    всё остальное. Длительность синтеза по числу символов заранее точно не
    предсказывается, а от неё зависят и допустимость, и цена.
    """
    from bot.storage.speech_jobs import get_job

    settings = load_settings()
    audio_path = _tmp_path(".mp3")
    pathlib.Path(audio_path).write_bytes(audio_bytes)

    try:
        duration = await probe_duration(audio_path)
    except Exception:
        # Замер сорвался — файл уже на диске и не нужен больше никому.
        pathlib.Path(audio_path).unlink(missing_ok=True)
        raise

    if duration > settings.avatar_max_seconds:
        pathlib.Path(audio_path).unlink(missing_ok=True)
        raise RenderRefused(REASON_TOO_LONG, settings.avatar_max_seconds)

    previous = get_job(db_path, job_id)
    update_job(
        db_path,
        job_id,
        status=STATUS_VOICED,
        audio_path=audio_path,
        audio_duration_sec=duration,
    )

    # Переозвучка: старая дорожка заданию больше не принадлежит. Удаляем
    # только после успешной записи новой, чтобы не остаться вообще без звука.
    if previous is not None and previous.audio_path not in (None, audio_path):
        pathlib.Path(previous.audio_path).unlink(missing_ok=True)
    return duration


async def request_render(
    db_path: str, job_id: int, image_bytes: bytes, look_id: int
) -> None:
    """Запустить платный рендер, проверив лимит до обращения к провайдеру."""
    settings = load_settings()
    from bot.storage.speech_jobs import get_job

    job = get_job(db_path, job_id)
    if job is None or job.audio_path is None or not job.audio_duration_sec:
        # Не «слишком длинно» и не «кончился лимит»: пропало само задание
        # или его звук. Назвать пользователю предел формата было бы враньём.
        raise RenderRefused(REASON_NO_AUDIO, 0)

    needed = int(round(job.audio_duration_sec))
    left = seconds_left(
        db_path, job.telegram_id, settings.avatar_monthly_seconds_limit
    )
    if needed > left:
        # Единственное место, где отказ обязан случиться раньше вызова:
        # после него секунды уже оплачены, отказывать поздно.
        raise RenderRefused(REASON_LIMIT, left)

    try:
        audio_bytes = pathlib.Path(job.audio_path).read_bytes()
    except OSError as error:
        # Файл озвучки исчез (перезапуск, чистка временной папки). Наружу
        # обещан только `RenderRefused`, голый FileNotFoundError пролетел бы
        # мимо обработчиков вызывающего.
        raise RenderRefused(REASON_NO_AUDIO, 0) from error

    task_uuid = await start_render(image_bytes, audio_bytes)

    # Бронь только после того, как провайдер принял рендер: несостоявшийся
    # старт денег не стоит и лимит съедать не должен.
    add_usage(db_path, job.telegram_id, needed, 0.0)

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

    Исключение — задание в `ready`: за него уже заплачено, и его ролик лежит
    на диске. Такое задание отдаётся с диска, без опроса и без списания; так
    оплаченное видео переживает перезапуск бота между списанием и отправкой.
    """
    if job.status == STATUS_READY:
        return _stored_video(job.id)
    if job.status != STATUS_RENDERING or job.provider_task_id is None:
        return None

    status = await poll_render(job.provider_task_id)
    reserved = _reserved_seconds(job)

    if status.failed:
        logger.warning(
            "Avatar render failed",
            extra={"user_id": job.telegram_id, "operation": "speech_pipeline"},
        )
        if reserved:
            # Рендер не состоялся — бронь возвращается пользователю, иначе
            # чужая неудача навсегда съест его месячный лимит.
            add_usage(db_path, job.telegram_id, -reserved, 0.0)
        update_job(db_path, job.id, status=STATUS_FAILED, error=status.error)
        return None

    if not status.done or status.video_bytes is None:
        return None

    # Сначала ролик на диск, потом деньги. Оплачено уже всё равно: упасть
    # между списанием и отправкой можно, потерять при этом видео — нельзя.
    _video_path(job.id).write_bytes(status.video_bytes)

    settings = load_settings()
    seconds = reserved
    if status.cost_usd is not None:
        cost_rub = status.cost_usd * settings.usd_rub_rate
    else:
        # Провайдер не вернул фактическую цену — считаем по замерам тем же
        # курсом, что и фактическую, иначе строки отчёта несравнимы. Ноль
        # писать нельзя: отчёт показал бы бесплатный рендер, поэтому
        # неизвестная длительность — это громкая ошибка, а не цена 0 ₽.
        if seconds <= 0:
            raise ValueError(
                f"Длительность озвучки задания {job.id} неизвестна: "
                "оценить стоимость рендера нечем."
            )
        cost_rub = video_cost(settings.avatar_model, seconds, settings.usd_rub_rate)

    # Не вся длительность, а разница: секунды забронированы при запуске.
    # Провайдер длину готового ролика не сообщает, так что фактической
    # считается длительность озвучки; разница обычно нулевая и нужна затем,
    # чтобы сверка не удваивала бронь.
    add_usage(db_path, job.telegram_id, seconds - reserved, cost_rub)
    record_cost(
        db_path,
        job.telegram_id,
        OPERATION_RENDER,
        settings.avatar_model,
        cost_rub,
    )
    update_job(db_path, job.id, status=STATUS_READY, cost_rub=cost_rub)
    return status.video_bytes
