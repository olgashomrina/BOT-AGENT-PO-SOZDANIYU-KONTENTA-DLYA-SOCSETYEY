from __future__ import annotations

import pathlib
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest

from bot.services import speech_pipeline
from bot.services.avatar_gateway import AvatarGatewayError, RenderStatus
from bot.storage.render_usage import add_usage, get_month_seconds
from bot.storage.speech_jobs import (
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_READY,
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
async def test_a_failed_probe_leaves_no_audio_file_behind(
    db_path, monkeypatch, tmp_path
):
    # Файл уже записан на диск к моменту замера: сорвавшийся замер не должен
    # оставлять его в /tmp навсегда.
    monkeypatch.setattr(
        speech_pipeline, "probe_duration", AsyncMock(side_effect=RuntimeError("ffprobe"))
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    with pytest.raises(RuntimeError):
        await attach(db_path, job_id, b"mp3-bytes")

    assert list(tmp_path.glob("*.mp3")) == []


@pytest.mark.asyncio
async def test_reattaching_audio_removes_the_previous_file(
    db_path, _probe, tmp_path
):
    # Пользователь переозвучил текст: старая дорожка больше не принадлежит
    # заданию и не должна оставаться на диске сиротой.
    _probe(20.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"first")
    first_path = get_job(db_path, job_id).audio_path

    await attach(db_path, job_id, b"second")

    second_path = get_job(db_path, job_id).audio_path
    assert second_path != first_path
    assert not pathlib.Path(first_path).exists()
    assert pathlib.Path(second_path).read_bytes() == b"second"


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
async def test_a_job_without_audio_is_refused_with_its_own_reason(
    db_path, monkeypatch
):
    # Пропавшее задание — это не «звук длиннее минуты»: сказать пользователю
    # про 60 секунд, когда исчез сам файл, значит соврать.
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    assert refusal.value.reason == speech_pipeline.REASON_NO_AUDIO
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_vanished_audio_file_is_refused_instead_of_crashing(
    db_path, _probe, monkeypatch
):
    # Наружу из этого модуля обещан только `RenderRefused`; голый
    # FileNotFoundError вылетел бы мимо всех обработчиков вызывающего.
    _probe(30.0)
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")
    pathlib.Path(get_job(db_path, job_id).audio_path).unlink()

    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    assert refusal.value.reason == speech_pipeline.REASON_NO_AUDIO
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_started_render_reserves_the_seconds_at_once(
    db_path, _probe, monkeypatch
):
    # Секунды запущенного, но ещё не забранного рендера обязаны быть видны
    # проверке лимита — иначе следующий запрос увидит полный остаток.
    _probe(30.0)
    monkeypatch.setattr(speech_pipeline, "start_render", AsyncMock(return_value="task-1"))
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")

    await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    assert get_month_seconds(db_path, TELEGRAM_ID) == 30


@pytest.mark.asyncio
async def test_a_render_the_provider_refused_to_start_reserves_nothing(
    db_path, _probe, monkeypatch
):
    # Несостоявшийся старт денег не стоит: съедать за него лимит нельзя.
    _probe(30.0)
    monkeypatch.setattr(
        speech_pipeline, "start_render", AsyncMock(side_effect=AvatarGatewayError("нет"))
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")

    with pytest.raises(AvatarGatewayError):
        await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    assert get_month_seconds(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_back_to_back_renders_cannot_outspend_the_limit(
    db_path, _probe, monkeypatch
):
    # Два запроса подряд, ни один ещё не забран: второй обязан увидеть
    # секунды первого, иначе оплачиваются оба.
    monkeypatch.setenv("AVATAR_MONTHLY_SECONDS_LIMIT", "45")
    _probe(30.0)
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)

    first = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, first, b"mp3")
    await speech_pipeline.request_render(db_path, first, b"image", look_id=7)

    second = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, second, b"mp3")
    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await speech_pipeline.request_render(db_path, second, b"image", look_id=7)

    assert refusal.value.reason == speech_pipeline.REASON_LIMIT
    start.assert_awaited_once()


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
    _poll(monkeypatch, cost_usd=0.2231)
    job_id = _rendering_job(db_path)

    video = await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert video == b"mp4"
    assert get_month_seconds(db_path, TELEGRAM_ID) == 30
    # 0.2231 доллара по курсу отчёта, а не оценка по прайсу.
    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.2231 * 92.0)


@pytest.mark.asyncio
async def test_collect_ready_falls_back_to_the_estimate_without_a_cost_field(
    db_path, monkeypatch
):
    _poll(monkeypatch, cost_usd=None)
    job_id = _rendering_job(db_path)

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.0446 * 30 * 92.0)


@pytest.mark.asyncio
async def test_both_charging_branches_use_the_configured_exchange_rate(
    db_path, monkeypatch
):
    # Фактическая цена и оценка обязаны считаться по одному курсу, иначе
    # строки отчёта, посчитанные разными ветками, несравнимы.
    monkeypatch.setenv("USD_RUB_RATE", "100.0")
    _poll(monkeypatch, cost_usd=None)
    job_id = _rendering_job(db_path)

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.0446 * 30 * 100.0)


@pytest.mark.asyncio
async def test_collect_ready_books_only_the_unreserved_difference(
    db_path, _probe, monkeypatch
):
    # Полный путь: старт бронирует секунды, сбор их сверяет. За одно задание
    # в счётчике должна остаться ровно его длительность, а не двойная.
    _probe(30.0)
    monkeypatch.setattr(speech_pipeline, "start_render", AsyncMock(return_value="task-1"))
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")
    await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)
    _poll(monkeypatch, cost_usd=0.2)

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_month_seconds(db_path, TELEGRAM_ID) == 30


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
    job_id = _rendering_job(db_path)

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None

    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert "invalidWidth" in job.error
    # Бронь возвращается: несостоявшийся рендер не съедает месячный лимит.
    assert get_month_seconds(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_polling_a_job_twice_charges_once(db_path, monkeypatch):
    # Воркер опрашивает по кругу; двойное списание за один рендер — это
    # двойные деньги в отчёте и съеденный лимит пользователя.
    _poll(monkeypatch, cost_usd=0.2)
    job_id = _rendering_job(db_path)

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))
    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_month_seconds(db_path, TELEGRAM_ID) == 30
    assert _ledger_rows(db_path) == 1


@pytest.mark.asyncio
async def test_the_finished_video_is_on_disk_before_the_charge(
    db_path, monkeypatch, tmp_path
):
    # Деньги уже уплачены провайдеру: если списание упадёт, ролик обязан
    # лежать на диске, а не только в возвращаемом значении.
    _poll(monkeypatch, cost_usd=0.2)
    monkeypatch.setattr(
        speech_pipeline, "add_usage", Mock(side_effect=RuntimeError("диск"))
    )
    job_id = _rendering_job(db_path)

    with pytest.raises(RuntimeError):
        await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert _video_file(tmp_path, job_id).read_bytes() == b"mp4"


@pytest.mark.asyncio
async def test_a_ready_job_is_recovered_from_disk_without_charging_again(
    db_path, monkeypatch, tmp_path
):
    # Бот перезапустился между списанием и отправкой: оплаченный ролик надо
    # отдать, а не потерять, — и не заплатить за него второй раз.
    poll = _poll(monkeypatch, cost_usd=0.2)
    job_id = _rendering_job(db_path)
    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))
    assert get_job(db_path, job_id).status == STATUS_READY

    again = await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert again == b"mp4"
    poll.assert_awaited_once()
    assert get_month_seconds(db_path, TELEGRAM_ID) == 30
    assert _ledger_rows(db_path) == 1
    assert _video_file(tmp_path, job_id).exists()


@pytest.mark.asyncio
async def test_a_ready_job_without_its_file_returns_none(
    db_path, monkeypatch, tmp_path
):
    poll = _poll(monkeypatch, cost_usd=0.2)
    job_id = _rendering_job(db_path)
    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))
    _video_file(tmp_path, job_id).unlink()

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None
    poll.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_job_that_is_not_rendering_is_never_polled(db_path, monkeypatch):
    # Повторный опрос чужого taskUUID — это второй платёж за тот же рендер.
    poll = _poll(monkeypatch, cost_usd=0.2)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status=STATUS_DRAFT, provider_task_id="task-1")

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None

    poll.assert_not_awaited()
    assert _ledger_rows(db_path) == 0


@pytest.mark.asyncio
async def test_a_render_without_a_known_duration_is_not_priced_at_zero(
    db_path, monkeypatch
):
    # Оценка от нулевой длительности — это бесплатный рендер в отчёте, ровно
    # то, чего код обещает не допускать. Лучше громкая ошибка.
    _poll(monkeypatch, cost_usd=None)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status=STATUS_RENDERING, provider_task_id="task-1")

    with pytest.raises(ValueError):
        await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert _ledger_rows(db_path) == 0
    assert get_job(db_path, job_id).cost_rub is None


async def attach(db_path: str, job_id: int, audio: bytes) -> float:
    """Короткая обёртка: имя `attach_audio` длинное, а зовут его в каждом тесте."""
    return await speech_pipeline.attach_audio(db_path, job_id, audio)


def _poll(monkeypatch, *, cost_usd: float | None) -> AsyncMock:
    """Провайдер, у которого рендер готов."""
    poll = AsyncMock(
        return_value=RenderStatus(
            done=True, failed=False, video_bytes=b"mp4", cost_usd=cost_usd, error=None
        )
    )
    monkeypatch.setattr(speech_pipeline, "poll_render", poll)
    return poll


def _rendering_job(db_path: str, seconds: float = 30.0) -> int:
    """Задание в рендере — ровно в том виде, в каком его оставляет
    `request_render`: с уже забронированными секундами месячного лимита."""
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=seconds,
    )
    add_usage(db_path, TELEGRAM_ID, int(round(seconds)), 0.0)
    return job_id


def _video_file(tmp_path, job_id: int) -> pathlib.Path:
    return pathlib.Path(tmp_path) / f"speech-{job_id}.mp4"


def _ledger_rows(db_path: str) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM cost_log").fetchone()[0])
    finally:
        connection.close()
