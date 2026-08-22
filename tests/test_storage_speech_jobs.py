from __future__ import annotations

import pytest

from bot.storage.speech_jobs import (
    FORMAT_VIDEO_NOTE,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_PUBLISHED,
    STATUS_RENDERING,
    STATUS_VOICED,
    create_job,
    get_active_job,
    get_job,
    get_jobs_by_status,
    update_job,
)

TELEGRAM_ID = 701


def test_new_job_starts_as_a_draft_video_note(db_path):
    job_id = create_job(db_path, TELEGRAM_ID, "Расскажу про запуск")

    job = get_job(db_path, job_id)
    assert job.status == STATUS_DRAFT
    assert job.format == FORMAT_VIDEO_NOTE
    assert job.source_text == "Расскажу про запуск"
    assert job.script is None
    assert job.audio_path is None
    assert job.created_at and job.updated_at


def test_update_writes_the_named_fields_and_bumps_updated_at(db_path):
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    before = get_job(db_path, job_id).updated_at

    update_job(
        db_path,
        job_id,
        status=STATUS_VOICED,
        audio_path="/tmp/a.mp3",
        audio_duration_sec=28.4,
    )

    job = get_job(db_path, job_id)
    assert job.status == STATUS_VOICED
    assert job.audio_path == "/tmp/a.mp3"
    assert job.audio_duration_sec == pytest.approx(28.4)
    assert job.updated_at >= before


def test_update_refuses_an_unknown_column(db_path):
    # Иначе опечатка в имени поля молча ничего не записала бы, а задание
    # осталось бы в прежнем статусе — с уже оплаченным рендером.
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    with pytest.raises(ValueError):
        update_job(db_path, job_id, statuss=STATUS_VOICED)


def test_jobs_by_status_finds_what_the_worker_must_pick_up(db_path):
    mine = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, mine, status=STATUS_RENDERING, provider_task_id="task-1")
    create_job(db_path, TELEGRAM_ID, "другой текст")

    rendering = get_jobs_by_status(db_path, STATUS_RENDERING)

    assert [job.id for job in rendering] == [mine]
    assert rendering[0].provider_task_id == "task-1"


def test_active_job_is_the_latest_unfinished_one(db_path):
    finished = create_job(db_path, TELEGRAM_ID, "старое")
    update_job(db_path, finished, status=STATUS_PUBLISHED)
    current = create_job(db_path, TELEGRAM_ID, "новое")

    assert get_active_job(db_path, TELEGRAM_ID).id == current


def test_failed_and_published_jobs_are_not_active(db_path):
    failed = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, failed, status=STATUS_FAILED, error="провайдер отказал")

    assert get_active_job(db_path, TELEGRAM_ID) is None


def test_active_job_is_per_user(db_path):
    create_job(db_path, 702, "чужое")

    assert get_active_job(db_path, TELEGRAM_ID) is None
