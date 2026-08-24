from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from bot.services import speech_pipeline
from bot.services.avatar_gateway import RenderStatus
from bot.storage.render_usage import get_month_seconds
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_RENDERING,
    STATUS_VOICED,
    create_job,
    get_job,
    update_job,
)

TELEGRAM_ID = 901


@pytest.fixture(autouse=True)
def _tmp_media(monkeypatch, tmp_path):
    monkeypatch.setenv("TMP_MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("AVATAR_MODEL", "klingai:avatar@2.0-standard")
    monkeypatch.setenv("AVATAR_MAX_SECONDS", "60")
    monkeypatch.setenv("AVATAR_MONTHLY_SECONDS_LIMIT", "300")


@pytest.fixture
def _probe(monkeypatch):
    def _set(seconds: float):
        monkeypatch.setattr(
            speech_pipeline, "probe_duration", AsyncMock(return_value=seconds)
        )

    return _set


@pytest.mark.asyncio
async def test_attach_audio_stores_the_file_and_marks_the_job_voiced(
    db_path, _probe
):
    _probe(28.4)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    duration = await attach(db_path, job_id, b"mp3-bytes")

    job = get_job(db_path, job_id)
    assert duration == pytest.approx(28.4)
    assert job.status == STATUS_VOICED
    assert job.audio_duration_sec == pytest.approx(28.4)
    with open(job.audio_path, "rb") as handle:
        assert handle.read() == b"mp3-bytes"


@pytest.mark.asyncio
async def test_audio_longer_than_the_format_allows_is_refused(db_path, _probe):
    # Video note не бывает длиннее 60 секунд. Отказ до оплаты — ноль расхода.
    _probe(75.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await attach(db_path, job_id, b"mp3-bytes")

    assert refusal.value.reason == speech_pipeline.REASON_TOO_LONG


@pytest.mark.asyncio
async def test_request_render_starts_the_provider_and_marks_rendering(
    db_path, _probe, monkeypatch
):
    _probe(30.0)
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")

    await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    job = get_job(db_path, job_id)
    assert job.status == STATUS_RENDERING
    assert job.provider_task_id == "task-1"
    assert job.look_id == 7
    start.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_is_refused_before_the_paid_call_when_the_limit_is_out(
    db_path, _probe, monkeypatch
):
    # Проверка лимита обязана стоять ДО обращения к провайдеру: после — это
    # уже оплаченный рендер, который мы просто не покажем.
    _probe(30.0)
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)
    speech_pipeline.add_usage(db_path, TELEGRAM_ID, 300, 1350.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")

    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    assert refusal.value.reason == speech_pipeline.REASON_LIMIT
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_ready_returns_none_while_the_render_runs(
    db_path, monkeypatch
):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=False, failed=False, video_bytes=None, cost_usd=None, error=None
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status=STATUS_RENDERING, provider_task_id="task-1")

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None
    assert get_job(db_path, job_id).status == STATUS_RENDERING


@pytest.mark.asyncio
async def test_collect_ready_charges_the_actual_provider_cost(db_path, monkeypatch):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=True,
                failed=False,
                video_bytes=b"mp4",
                cost_usd=0.2231,
                error=None,
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    video = await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert video == b"mp4"
    assert get_month_seconds(db_path, TELEGRAM_ID) == 30
    # 0.2231 доллара по курсу отчёта, а не оценка по прайсу.
    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.2231 * 92.0)


@pytest.mark.asyncio
async def test_collect_ready_falls_back_to_the_estimate_without_a_cost_field(
    db_path, monkeypatch
):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=True, failed=False, video_bytes=b"mp4", cost_usd=None, error=None
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.0446 * 30 * 92.0)


@pytest.mark.asyncio
async def test_a_failed_render_is_not_charged(db_path, monkeypatch):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=False,
                failed=True,
                video_bytes=None,
                cost_usd=None,
                error="invalidWidth",
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None

    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert "invalidWidth" in job.error
    assert get_month_seconds(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_polling_a_job_twice_charges_once(db_path, monkeypatch):
    # Воркер опрашивает по кругу; двойное списание за один рендер — это
    # двойные деньги в отчёте и съеденный лимит пользователя.
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=True, failed=False, video_bytes=b"mp4", cost_usd=0.2, error=None
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))
    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_month_seconds(db_path, TELEGRAM_ID) == 30


async def attach(db_path: str, job_id: int, audio: bytes) -> float:
    """Короткая обёртка: имя `attach_audio` длинное, а зовут его в каждом тесте."""
    return await speech_pipeline.attach_audio(db_path, job_id, audio)
