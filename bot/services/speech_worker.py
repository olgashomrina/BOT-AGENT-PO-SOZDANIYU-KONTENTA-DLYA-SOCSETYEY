"""Фоновый опрос рендеров и доставка готовых кружков.

Асинхронная задача, стартующая вместе с ботом. На каждом тике берёт задания
в статусе `rendering` (рендер идёт) и задания в `ready` без `result_file_id`
(рендер оплачен, а кружок пользователь ещё не получил) — в том числе
оставшиеся от прошлого запуска. Это и есть страховка от рестарта: рендер уже
оплачен, и потерять его нельзя.

Отсюда же главное правило модуля: сорвавшаяся доставка — это повод повторить,
а не повод закрыть задание. Файл ролика удаляется только тогда, когда его
уже некому читать: после успешной отправки либо вместе с терминальным
провалом. Терминальный провал — это ошибка, которая не пройдёт ни на какой
попытке (`_PERMANENT_DELIVERY_ERRORS`), исчерпанный предел времени на
повторы, пропавший с диска ролик или дважды подряд не зафиксированный
после отправки `file_id`. Во всех остальных случаях — повтор на следующем
тике.
"""

from __future__ import annotations

import logging
import pathlib
import uuid
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
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
    SpeechJob,
    get_job,
    get_jobs_by_status,
    update_job,
)
from bot.storage.users import get_interface_language

logger = logging.getLogger(LOGGER_NAME)

JOB_ID = "speech_render_poll"

# Сколько времени воркер повторяет доставку оплаченного ролика, прежде чем
# признать её безнадёжной. Считается от `updated_at` задания: отдельной
# колонки под счётчик попыток в схеме нет, а заводить её ради этого нельзя.
#
# Шесть часов — это заведомо больше любой временной причины (флуд-контроль
# Telegram отпускает за минуты, сеть и место на диске — за десятки минут,
# перезапуск бота укладывается в единицы минут) и заведомо меньше суток, за
# которые пользователь успеет решить, что про его оплаченный кружок забыли.
# Всё это время задание держит пользователя в REASON_BUSY, поэтому предел
# должен быть, и он должен заканчиваться внятным сообщением.
DELIVERY_RETRY_LIMIT_SECONDS = 6 * 60 * 60

# Ошибки, у которых нет ни одной попытки с шансом на успех: пользователь
# заблокировал бота или чата больше нет. Всё остальное — от 429 и обрыва
# сети до нехватки места под ffmpeg — проходит само, и повтор дешевле
# потерянного оплаченного ролика. Взяты самые узкие подходящие типы aiogram:
# TelegramAPIError накрыл бы и временные сбои, TelegramBadRequest —
# сообщения вроде «file is too big», где повтор тоже не помог бы, но и
# ошибиться в другую сторону там дороже.
_PERMANENT_DELIVERY_ERRORS = (TelegramForbiddenError, TelegramNotFound)

# Метка «ответ уже один раз пришёл без video_note» для текущего рендера.
# Отдельной колонки под неё нет и заводить нельзя, поэтому метка живёт в уже
# существующем `error` — том же поле, что несёт диагноз терминального
# провала. Это безопасно: начало нового рендера (`speech_pipeline`, запись
# `status=rendering`) явно пишет `error=None`, так что на первый случай для
# этого рендера поле гарантированно чисто, а спутать метку с чужим диагнозом
# невозможно — второй такой диагноз тут же завершает задание и стирает её.
_NO_FILE_ID_MARK = "no_file_id_once"


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


async def _notify(bot: Bot, db_path: str, telegram_id: int, key: str) -> None:
    """Сказать пользователю — и не уронить тик, если сказать не вышло.

    Уведомление никогда не важнее самой работы: 429 на одном задании не
    должен оставить недоставленными все остальные, уже оплаченные.
    """
    try:
        await bot.send_message(
            telegram_id, get_string(key, _language(db_path, telegram_id))
        )
    except Exception:
        logger.warning(
            "Speech job notification failed",
            extra={"user_id": telegram_id, "operation": "speech_worker"},
            exc_info=True,
        )


def _age_seconds(job: SpeechJob) -> float | None:
    """Сколько задание не менялось. None — если время не разобрать.

    `updated_at` пишется в UTC ISO-8601 (`bot.storage.speech_jobs`), но старые
    строки без смещения безопаснее считать теми же UTC, чем сравнивать с
    осведомлённым `now` и получить TypeError.
    """
    try:
        stamp = datetime.fromisoformat(job.updated_at)
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def _retry_limit_exceeded(job: SpeechJob) -> bool:
    """Исчерпан ли предел повторов доставки.

    Неразобранная метка времени (`_age_seconds` вернула `None`) — сегодня
    недостижимый случай (колонка `NOT NULL`, пишется только в ISO-8601), но
    если он всё же случится, склоняться нужно к завершению задания, а не к
    молчаливому бесконечному повтору: это ровно та зависшая оплата, о
    которой предупреждает соседняя проверка предела.
    """
    age = _age_seconds(job)
    return age is None or age > DELIVERY_RETRY_LIMIT_SECONDS


async def _give_up(
    bot: Bot,
    db_path: str,
    job: SpeechJob,
    error: str,
    notify_key: str = "speech_failed",
) -> None:
    """Закрыть задание терминально и сказать об этом пользователю.

    Только отсюда задание уходит в `failed` по вине доставки. Ролик здесь
    удаляется: ни `rendering`-, ни `ready`-выборка терминальное задание
    больше не подберут, читать файл некому.

    Озвучка остаётся на диске сознательно: `speech_failed` обещает, что текст
    и озвучка сохранены, а `failed` — статус, с которого повтор рендера
    законен (`speech_pipeline._ATTACHABLE_STATUSES`). Удалить дорожку значило
    бы соврать в тексте и превратить обещанный повтор в REASON_NO_AUDIO.

    `notify_key` по умолчанию — общий «съёмка не удалась», но для случая
    «кружок дошёл, а записать его было нечем» (см. `_deliver`) правда другая:
    ролик пользователь уже видел, врать про сорвавшуюся съёмку нельзя.
    """
    if get_job(db_path, job.id) is None:
        # Строки уже нет: писать в неё нечего, и рассказывать пользователю
        # о задании, которого не существует, тоже незачем.
        logger.warning(
            "Speech job vanished before it could be failed",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
        )
        return
    update_job(db_path, job.id, status=STATUS_FAILED, error=error)
    _rendered_video_path(job.id).unlink(missing_ok=True)
    await _notify(bot, db_path, job.telegram_id, notify_key)


def _keep_for_retry(db_path: str, job: SpeechJob) -> None:
    """Оставить задание в очереди на следующий тик.

    `ready` + пустой `result_file_id` — ровно то состояние, которое подбирает
    `_jobs_to_poll`, а `speech-{job_id}.mp4` на диске — то, что вернёт
    `collect_ready` без повторного списания. Запись идёт, только если статус
    ещё не тот: лишний `update_job` сдвинул бы `updated_at`, то есть отодвинул
    бы предел времени на повторы, и задание крутилось бы вечно.
    """
    current = get_job(db_path, job.id)
    if current is None or current.status == STATUS_READY:
        return
    update_job(db_path, job.id, status=STATUS_READY, result_file_id=None)


async def _deliver(bot: Bot, db_path: str, job: SpeechJob, video_bytes: bytes) -> None:
    """Собрать кружок и отправить его. Всё после отправки — лучшее усилие.

    Исключение отсюда означает ровно одно: пользователь кружок не получил.
    Ошибки уже после `send_video_note` наружу не выпускаются — кружок на
    экране, и никакая неудача с записью или уведомлением не имеет права
    увести задание из `ready` или стереть оплаченный ролик.
    """
    raw_path = _tmp_path(".mp4")
    note_path = _tmp_path(".mp4")
    try:
        pathlib.Path(raw_path).write_bytes(video_bytes)
        await to_video_note(raw_path, note_path)
        message = await bot.send_video_note(job.telegram_id, FSInputFile(note_path))
    finally:
        for path in (raw_path, note_path):
            pathlib.Path(path).unlink(missing_ok=True)

    file_id = getattr(getattr(message, "video_note", None), "file_id", None)
    if file_id is None:
        if job.error == _NO_FILE_ID_MARK:
            # Второй раз подряд для этого же рендера — не совпадение, а
            # свойство ответа: если сервер один раз прислал message без
            # video_note, он и дальше будет его присылать. Кружок при этом
            # УЖЕ доставлен (send_video_note не упал), просто зафиксировать
            # его нечем — значит и врать про сорвавшуюся съёмку нельзя,
            # и слать те же 720 кружков за 6 часов до истечения общего
            # предела тоже нельзя.
            logger.error(
                "Video note response carries no file_id twice, giving up",
                extra={"user_id": job.telegram_id, "operation": "speech_worker"},
            )
            await _give_up(
                bot,
                db_path,
                job,
                "Кружок доставлен, но идентификатор файла не получен дважды.",
                notify_key="speech_delivered_not_recorded",
            )
            return
        # Первый случай для этого рендера. Файл оркестратора остаётся на
        # месте, задание остаётся в выборке: следующий тик попробует ещё раз
        # и, если ответ будет прежним, второй заход выше уже не повторит
        # кружок в третий раз. Метка — единственное свидетельство первого
        # случая: счётчика попыток в схеме нет.
        logger.error(
            "Video note response carries no file_id",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
        )
        update_job(db_path, job.id, error=_NO_FILE_ID_MARK)
        return

    try:
        # file_id кэшируется: публикация в канал дальше бесплатна и мгновенна.
        # Статус пишем в ready и здесь: для только что оплаченного рендера
        # это переустановка того же значения, а для задания, подобранного
        # аварийным сбором по ready (см. process_rendering_jobs), это
        # единственное место, где статус вообще выставляется, — collect_ready
        # для такого задания просто отдаёт байты с диска, не трогая базу.
        update_job(
            db_path, job.id, status=STATUS_READY, result_file_id=file_id
        )
    except Exception:
        logger.error(
            "Delivered circle could not be recorded",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
            exc_info=True,
        )
        return

    # Только теперь ролик доставлен и result_file_id записан: следующий тик
    # уже не станет искать его на диске для повторной отправки. Удалить его
    # раньше значило бы потерять оплаченное видео, если отправка только что
    # упала, — RECOVERY-ветка collect_ready читает именно этот файл. Здесь же
    # заканчивается и жизнь озвучки: переснимать это задание больше нечем.
    _rendered_video_path(job.id).unlink(missing_ok=True)
    if job.audio_path:
        pathlib.Path(job.audio_path).unlink(missing_ok=True)
    await _notify(bot, db_path, job.telegram_id, "speech_ready")


def _jobs_to_poll(db_path: str) -> list[SpeechJob]:
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


async def _process_job(bot: Bot, db_path: str, job: SpeechJob) -> None:
    try:
        video_bytes = await collect_ready(db_path, job)
    except Exception:
        # Опрос провайдера сорвался. Задание остаётся как было — следующий
        # тик повторит; терять из-за этого соседние задания незачем.
        logger.warning(
            "Speech job polling failed",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
            exc_info=True,
        )
        return

    refreshed = get_job(db_path, job.id)
    if refreshed is None:
        logger.warning(
            "Speech job vanished during the tick",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
        )
        return
    if refreshed.status == STATUS_FAILED:
        # Отказал провайдер: `collect_ready` уже вернула бронь и записала
        # диагноз. Озвучка остаётся — повтор будет стоить только съёмку,
        # ровно как обещает текст.
        await _notify(bot, db_path, job.telegram_id, "speech_failed")
        return

    if video_bytes is None:
        if job.status == STATUS_READY:
            # Задание оплачено и лежит в `ready`, а ролика на диске нет:
            # его унесло перезагрузкой или чисткой временной папки.
            # Повторять нечего, а оставить как есть — значит навсегда запереть
            # пользователя в REASON_BUSY без единого слова от бота.
            await _give_up(
                bot,
                db_path,
                job,
                "Готовый ролик исчез с диска — доставить его больше нечем.",
            )
        # Иначе рендер просто ещё идёт.
        return

    try:
        await _deliver(bot, db_path, refreshed, video_bytes)
    except _PERMANENT_DELIVERY_ERRORS as error:
        logger.error(
            "Speech job delivery is impossible",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
            exc_info=True,
        )
        await _give_up(bot, db_path, job, f"Доставка невозможна: {error}")
    except Exception:
        # Ffmpeg, сеть, флуд-контроль — всё это проходит само. Ролик остаётся
        # на диске, задание — в выборке следующего тика.
        logger.error(
            "Speech job delivery failed, will retry",
            extra={"user_id": job.telegram_id, "operation": "speech_worker"},
            exc_info=True,
        )
        # Предел по времени проверяется ЗДЕСЬ, а не в начале обработки: он
        # обязан идти после хотя бы одной реальной попытки доставки. Иначе
        # задание, чей `updated_at` состарился без единой попытки (простой
        # между рендером и первым тиком — деплой, авария хоста), сдалось бы
        # молча, ни разу не попытавшись отправить лежащий на диске ролик.
        #
        # Возраст берём у `refreshed`, а не у входного `job`: для задания,
        # только что перешедшего из `rendering` в `ready` внутри
        # `collect_ready`, именно `refreshed.updated_at` — момент готовности
        # ролика, а не момент запуска рендера. Долгий рендер не должен
        # списываться на счёт ещё не начинавшихся повторов доставки.
        if _retry_limit_exceeded(refreshed):
            hours = DELIVERY_RETRY_LIMIT_SECONDS // 3600
            await _give_up(
                bot,
                db_path,
                refreshed,
                f"Кружок не удалось доставить за {hours} ч. повторов.",
            )
            return
        # Пользователю тут ничего не говорим: сказать нечего, кружок ещё
        # будет.
        _keep_for_retry(db_path, refreshed)


async def process_rendering_jobs(bot: Bot, db_path: str) -> None:
    for job in _jobs_to_poll(db_path):
        try:
            await _process_job(bot, db_path, job)
        except Exception:
            # Пачка заданий обрабатывается целиком: что бы ни случилось на
            # одном — база, диск, Telegram, — соседние оплаченные кружки
            # обязаны быть доставлены в этом же тике.
            logger.error(
                "Speech job processing failed",
                extra={"user_id": job.telegram_id, "operation": "speech_worker"},
                exc_info=True,
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
