from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services import speech_worker
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    create_job,
    get_job,
    update_job,
)

TELEGRAM_ID = 1001


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
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_temporary_files_are_cleaned_up_after_delivery(
    db_path, monkeypatch, audio_file
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
async def test_a_delivery_crash_also_cleans_up_the_orchestrators_video_file(
    db_path, monkeypatch, audio_file, tmp_path
):
    # Ролик доставить не удалось (например, ffmpeg упал), задание уходит в
    # failed терминально — ни rendering-, ни ready-выборка его больше не
    # подберут, значит файл оркестратора больше некому прочитать.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=RuntimeError("ffmpeg boom"))
    )
    job_id = _rendering_job(db_path, audio_file)
    rendered_path = tmp_path / f"speech-{job_id}.mp4"
    rendered_path.write_bytes(b"mp4")
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    assert not rendered_path.exists()
    assert get_job(db_path, job_id).status == STATUS_FAILED
    bot.send_message.assert_awaited_once()


def test_scheduler_runs_on_the_configured_interval(db_path):
    scheduler = speech_worker.build_speech_scheduler(_bot(), db_path, 20)

    job = scheduler.get_job("speech_render_poll")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 20


async def _write_note(src_path: str, out_path: str, *args, **kwargs) -> str:
    pathlib.Path(out_path).write_bytes(b"note")
    return out_path
