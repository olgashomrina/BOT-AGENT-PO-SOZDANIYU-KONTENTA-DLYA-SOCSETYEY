from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from bot.locales.loader import get_string
from bot.services import speech_worker
from bot.storage.db import get_connection
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    create_job,
    get_job,
    update_job,
)

TELEGRAM_ID = 1001


def _blocked() -> TelegramForbiddenError:
    return TelegramForbiddenError(
        method=SendMessage(chat_id=TELEGRAM_ID, text="x"),
        message="bot was blocked by the user",
    )


def _age_job(db_path: str, job_id: int, seconds: float) -> None:
    """Отодвинуть `updated_at` задания в прошлое.

    Возраст задания — единственные часы воркера: колонки под счётчик
    попыток в схеме нет, а заводить её ради теста нельзя.
    """
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    connection = get_connection(db_path)
    try:
        connection.execute(
            "UPDATE speech_jobs SET updated_at = ? WHERE id = ?", (stamp, job_id)
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def _tmp_media(monkeypatch, tmp_path):
    monkeypatch.setenv("TMP_MEDIA_DIR", str(tmp_path))


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.send_video_note = AsyncMock(
        return_value=MagicMock(video_note=MagicMock(file_id="note-1"))
    )
    bot.send_message = AsyncMock()
    return bot


def _rendering_job(db_path: str, audio_path: str) -> int:
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
        audio_path=audio_path,
    )
    return job_id


@pytest.fixture
def audio_file(tmp_path) -> str:
    path = tmp_path / "voice.mp3"
    path.write_bytes(b"mp3")
    return str(path)


@pytest.mark.asyncio
async def test_ready_render_is_sent_as_a_video_note(
    db_path, monkeypatch, audio_file
):
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_awaited_once()
    job = get_job(db_path, job_id)
    assert job.status == STATUS_READY
    assert job.result_file_id == "note-1"
    # Не «какое-нибудь сообщение», а именно то: перепутанные местами
    # speech_ready и speech_failed прошли бы проверку на количество вызовов.
    bot.send_message.assert_awaited_once_with(
        TELEGRAM_ID, get_string("speech_ready", "ru")
    )


@pytest.mark.asyncio
async def test_a_job_still_rendering_is_left_alone(db_path, monkeypatch, audio_file):
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=None)
    )
    job_id = _rendering_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_not_awaited()
    assert get_job(db_path, job_id).status == STATUS_RENDERING


@pytest.mark.asyncio
async def test_a_failed_job_tells_the_user_and_is_not_sent(
    db_path, monkeypatch, audio_file
):
    async def fail(db_path_arg, job):
        update_job(db_path_arg, job.id, status=STATUS_FAILED, error="провайдер отказал")
        return None

    monkeypatch.setattr(speech_worker, "collect_ready", fail)
    _rendering_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_not_awaited()
    bot.send_message.assert_awaited_once_with(
        TELEGRAM_ID, get_string("speech_failed", "ru")
    )


@pytest.mark.asyncio
async def test_temporary_files_are_cleaned_up_after_delivery(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Кэш озвучки и скачанное видео не должны копиться в TMP_MEDIA_DIR:
    # media_cache.py уже отучил нас надеяться, что кто-то приберёт потом.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    _rendering_job(db_path, audio_file)

    await speech_worker.process_rendering_jobs(_bot(), db_path)

    assert not pathlib.Path(audio_file).exists()
    # Скачанный ролик и собранный кружок живут во временной папке под
    # случайными именами — проверяем, что после доставки там не осталось
    # ни одного mp4.
    assert list(tmp_path.glob("*.mp4")) == []


@pytest.mark.asyncio
async def test_one_broken_job_does_not_stop_the_others(
    db_path, monkeypatch, audio_file
):
    # Рестарт подбирает пачку заданий; исключение на первом не должно
    # оставить остальные висеть в rendering навсегда.
    calls: list[int] = []

    async def flaky(db_path_arg, job):
        calls.append(job.id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return b"mp4"

    monkeypatch.setattr(speech_worker, "collect_ready", flaky)
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    _rendering_job(db_path, audio_file)
    _rendering_job(db_path, audio_file)

    await speech_worker.process_rendering_jobs(_bot(), db_path)

    assert len(calls) == 2


def _ready_job(db_path: str, audio_path: str) -> int:
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_READY,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
        audio_path=audio_path,
    )
    return job_id


@pytest.mark.asyncio
async def test_a_ready_job_left_over_from_a_crash_is_still_delivered(
    db_path, monkeypatch, audio_file
):
    # Задание 13: между записью ready и отправкой кружка бот мог упасть.
    # Секунды и деньги уже списаны, а get_jobs_by_status(rendering) такое
    # задание больше не видит — воркер обязан подобрать его отдельно.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _ready_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_awaited_once()
    assert get_job(db_path, job_id).result_file_id == "note-1"


@pytest.mark.asyncio
async def test_an_already_delivered_ready_job_is_not_resent(
    db_path, monkeypatch, audio_file
):
    # Как только result_file_id записан, кружок уже у пользователя — слать
    # его второй раз на каждом тике было бы явным браком.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    job_id = _ready_job(db_path, audio_file)
    update_job(db_path, job_id, result_file_id="note-already")
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_orchestrators_video_file_is_removed_after_delivery(
    db_path, monkeypatch, audio_file, tmp_path
):
    # speech_pipeline.py кладёт готовый ролик по имени speech-{id}.mp4 и явно
    # передаёт его удаление воркеру (см. докстринг _video_path). Без этого
    # временная папка растёт на один файл с каждым рендером.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    rendered_path = tmp_path / f"speech-{job_id}.mp4"
    rendered_path.write_bytes(b"mp4")

    await speech_worker.process_rendering_jobs(_bot(), db_path)

    assert not rendered_path.exists()


@pytest.mark.asyncio
async def test_a_delivery_failure_keeps_the_paid_video_for_the_next_tick(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Отправка сорвалась на ffmpeg или на 429 — это состояние проходит само.
    # Ролик уже оплачен: стереть его и закрыть задание значило бы обменять
    # временную ошибку на безвозвратно потерянные деньги пользователя.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker,
        "to_video_note",
        AsyncMock(side_effect=RuntimeError("ffmpeg boom")),
    )
    job_id = _rendering_job(db_path, audio_file)
    rendered_path = tmp_path / f"speech-{job_id}.mp4"
    rendered_path.write_bytes(b"mp4")
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    assert rendered_path.exists()
    job = get_job(db_path, job_id)
    assert job.status == STATUS_READY
    assert job.result_file_id is None
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_job_left_over_from_a_delivery_failure_is_retried_next_tick(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Ровно та выборка, ради которой ready без result_file_id вообще
    # подбирается: прошлый тик не смог отправить, этот обязан повторить.
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _ready_job(db_path, audio_file)
    (tmp_path / f"speech-{job_id}.mp4").write_bytes(b"mp4")
    _age_job(db_path, job_id, 60)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_awaited_once()
    assert get_job(db_path, job_id).result_file_id == "note-1"


@pytest.mark.asyncio
async def test_a_job_retrying_for_too_long_fails_and_tells_the_user(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Повтор ограничен временем, а не числом попыток (колонки под счётчик
    # нет). Когда предел исчерпан, пользователю обязаны сказать: молча
    # крутиться вечно — худший из возможных исходов.
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _ready_job(db_path, audio_file)
    rendered_path = tmp_path / f"speech-{job_id}.mp4"
    rendered_path.write_bytes(b"mp4")
    _age_job(db_path, job_id, speech_worker.DELIVERY_RETRY_LIMIT_SECONDS + 60)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_not_awaited()
    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert job.error
    assert not rendered_path.exists()
    bot.send_message.assert_awaited_once_with(
        TELEGRAM_ID, get_string("speech_failed", "ru")
    )


@pytest.mark.asyncio
async def test_a_permanently_undeliverable_circle_fails_terminally(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Пользователь заблокировал бота: повтор не поможет ни на каком тике.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    rendered_path = tmp_path / f"speech-{job_id}.mp4"
    rendered_path.write_bytes(b"mp4")
    bot = _bot()
    bot.send_video_note = AsyncMock(side_effect=_blocked())

    await speech_worker.process_rendering_jobs(bot, db_path)

    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert not rendered_path.exists()


@pytest.mark.asyncio
async def test_a_ready_job_whose_video_vanished_is_failed_and_the_user_is_told(
    db_path, audio_file
):
    # Файл унесло перезагрузкой или чисткой временной папки. Повторять
    # нечего, а ready навсегда держит пользователя в REASON_BUSY: задание
    # обязано закрыться с диагнозом, а пользователь — узнать об этом.
    job_id = _ready_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert job.error
    bot.send_message.assert_awaited_once_with(
        TELEGRAM_ID, get_string("speech_failed", "ru")
    )


@pytest.mark.asyncio
async def test_a_failure_while_telling_the_user_does_not_undo_the_delivery(
    db_path, monkeypatch, audio_file
):
    # Кружок уже на экране у пользователя. Всё, что случается после
    # send_video_note, — лучшее усилие: сорвавшееся уведомление не имеет
    # права увести задание в failed, которое уже никогда не опубликуешь.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    bot = _bot()
    bot.send_message = AsyncMock(side_effect=_blocked())

    await speech_worker.process_rendering_jobs(bot, db_path)

    job = get_job(db_path, job_id)
    assert job.status == STATUS_READY
    assert job.result_file_id == "note-1"


@pytest.mark.asyncio
async def test_a_response_without_a_video_note_does_not_burn_the_paid_video(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Ответ Telegram без поля video_note — это AttributeError уже после
    # отправки. Задание при этом не провалено, а ролик остаётся на диске:
    # только он и позволит записать file_id на следующем тике.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    rendered_path = tmp_path / f"speech-{job_id}.mp4"
    rendered_path.write_bytes(b"mp4")
    bot = _bot()
    bot.send_video_note = AsyncMock(return_value=MagicMock(video_note=None))

    await speech_worker.process_rendering_jobs(bot, db_path)

    assert get_job(db_path, job_id).status != STATUS_FAILED
    assert rendered_path.exists()


@pytest.mark.asyncio
async def test_the_audio_survives_a_delivery_failure(
    db_path, monkeypatch, audio_file, tmp_path
):
    # speech_failed обещает: «Текст и озвучка сохранены». Задание в failed
    # переозвучке и повтору подлежит, и повтор читает именно этот файл —
    # удалить его значило бы соврать пользователю и сорвать повтор.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker,
        "to_video_note",
        AsyncMock(side_effect=RuntimeError("ffmpeg boom")),
    )
    job_id = _rendering_job(db_path, audio_file)
    (tmp_path / f"speech-{job_id}.mp4").write_bytes(b"mp4")

    await speech_worker.process_rendering_jobs(_bot(), db_path)

    assert pathlib.Path(audio_file).exists()


@pytest.mark.asyncio
async def test_the_audio_survives_a_terminal_delivery_failure(
    db_path, monkeypatch, audio_file, tmp_path
):
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    (tmp_path / f"speech-{job_id}.mp4").write_bytes(b"mp4")
    bot = _bot()
    bot.send_video_note = AsyncMock(side_effect=_blocked())

    await speech_worker.process_rendering_jobs(bot, db_path)

    assert get_job(db_path, job_id).status == STATUS_FAILED
    assert pathlib.Path(audio_file).exists()


@pytest.mark.asyncio
async def test_a_notification_failure_on_one_job_does_not_block_the_next(
    db_path, monkeypatch, audio_file
):
    # Тик обрабатывает пачку: сорвавшееся уведомление по первому заданию
    # не должно оставить второе, уже оплаченное, недоставленным.
    first = _rendering_job(db_path, audio_file)

    async def collect(db_path_arg, job):
        if job.id == first:
            update_job(db_path_arg, job.id, status=STATUS_FAILED, error="отказ")
            return None
        return b"mp4"

    monkeypatch.setattr(speech_worker, "collect_ready", collect)
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    second = _rendering_job(db_path, audio_file)
    bot = _bot()
    bot.send_message = AsyncMock(side_effect=_blocked())

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_awaited_once()
    assert get_job(db_path, second).result_file_id == "note-1"


def test_scheduler_runs_on_the_configured_interval(db_path):
    scheduler = speech_worker.build_speech_scheduler(_bot(), db_path, 20)

    job = scheduler.get_job("speech_render_poll")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 20
    # «Без наложения запусков»: второй тик не стартует поверх первого,
    # а пропущенные не копятся очередью одинаковых прогонов.
    assert job.max_instances == 1
    assert job.coalesce is True


async def _write_note(src_path: str, out_path: str, *args, **kwargs) -> str:
    pathlib.Path(out_path).write_bytes(b"note")
    return out_path
