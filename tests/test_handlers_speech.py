from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import speech
from bot.locales.loader import get_string
from bot.services.speech_pipeline import (
    REASON_BUSY,
    REASON_NO_AUDIO,
    REASON_TOO_LONG,
    RenderRefused,
)
from bot.storage.avatar_faces import save_face
from bot.storage.avatar_looks import SOURCE_UPLOADED, add_look
from bot.storage.limits import get_daily_count
from bot.storage.render_usage import add_usage, seconds_left
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    STATUS_VOICED,
    create_job,
    get_active_job,
    get_job,
    update_job,
)
from bot.storage.voice_profiles import save_voice_profile
from bot.storage.whitelist import add_user

TELEGRAM_ID = 1201


@pytest.fixture(autouse=True)
def _avatar_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TMP_MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("AVATAR_MONTHLY_SECONDS_LIMIT", "300")
    monkeypatch.setenv("AVATAR_MAX_SECONDS", "60")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


@pytest.fixture
def ready_double(db_path) -> int:
    save_face(db_path, TELEGRAM_ID, "photo-face")
    return add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)


def _callback(data: str = "") -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.message.answer_voice = AsyncMock()
    callback.message.bot.download = AsyncMock()
    callback.message.bot.send_video_note = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _text_message(text: str) -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.text = text
    message.voice = None
    message.answer = AsyncMock()
    message.answer_voice = AsyncMock()
    message.bot.download = AsyncMock()
    return message


def _voice_message() -> MagicMock:
    message = _text_message("")
    message.text = None
    message.voice = MagicMock(file_id="voice-1", duration=30)
    return message


@pytest.mark.asyncio
async def test_speak_refuses_without_a_face(db_path, state):
    callback = _callback()

    await speech.on_speak(callback, db_path=db_path, state=state)

    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_written_text_creates_a_draft_job(db_path, state, ready_double):
    await state.set_state(speech.SpeechStates.waiting_input)

    await speech.on_text(_text_message("Расскажу про запуск"), db_path=db_path, state=state)

    job = get_active_job(db_path, TELEGRAM_ID)
    assert job is not None
    assert job.source_text == "Расскажу про запуск"


@pytest.mark.asyncio
async def test_voice_message_becomes_the_audio_itself(
    db_path, state, ready_double, monkeypatch
):
    # Голосовое — это готовая озвучка настоящим голосом, а не сырьё для
    # пересинтеза. Это самый дешёвый путь и он работает без ElevenLabs.
    attach = AsyncMock(return_value=30.0)
    monkeypatch.setattr(speech, "attach_audio", attach)
    monkeypatch.setattr(speech, "transcribe", AsyncMock(return_value="расшифровка"))
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"voice-bytes")
    await state.set_state(speech.SpeechStates.waiting_input)

    await speech.on_voice(_voice_message(), db_path=db_path, state=state)

    attach.assert_awaited_once()
    assert get_active_job(db_path, TELEGRAM_ID).source_text == "расшифровка"


@pytest.mark.asyncio
async def test_written_text_without_synthesis_gets_a_prompter_and_costs_nothing(
    db_path, state, ready_double, monkeypatch
):
    synthesize = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(speech, "synthesize", synthesize)
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "0")
    job_id = create_job(db_path, TELEGRAM_ID, "Расскажу про запуск")
    await state.update_data(job_id=job_id)

    await speech.on_voice_as_is(_callback(), db_path=db_path, state=state)

    synthesize.assert_not_awaited()
    assert get_job(db_path, job_id).status == "draft"


@pytest.mark.asyncio
async def test_synthesis_uses_the_existing_cloned_voice(
    db_path, state, ready_double, monkeypatch
):
    # Голос уже создан этапом 1 — новый двойник ради речи не создаётся.
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", "2026-08-01")
    synthesize = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(speech, "synthesize", synthesize)
    monkeypatch.setattr(speech, "attach_audio", AsyncMock(return_value=28.0))
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "1")
    job_id = create_job(db_path, TELEGRAM_ID, "Расскажу про запуск")
    await state.update_data(job_id=job_id)

    await speech.on_voice_as_is(_callback(), db_path=db_path, state=state)

    assert synthesize.await_args.args == ("Расскажу про запуск", "voice-abc")


@pytest.mark.asyncio
async def test_stale_voice_as_is_tap_does_not_pay(
    db_path, state, ready_double, monkeypatch
):
    # «Озвучить как есть» может остаться нажимаемой на старом сообщении в
    # чате уже после того, как это же задание ушло в рендер. Синтез — платный
    # вызов ElevenLabs, и раз attach_audio всё равно откажет заданию в этом
    # статусе, платить за озвучку, которую тут же выбросят, нельзя.
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", "2026-08-01")
    synthesize = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(speech, "synthesize", synthesize)
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "1")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status=STATUS_RENDERING)
    await state.update_data(job_id=job_id)

    await speech.on_voice_as_is(_callback(), db_path=db_path, state=state)

    synthesize.assert_not_awaited()
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_voice_refusal_by_busy_job_tells_the_truth(
    db_path, state, ready_double, monkeypatch
):
    # attach_audio отказывает нулём и для "занято", и для "звука нет вовсе" —
    # только speech_too_long про эти нули врёт ("длиннее 0 секунд").
    monkeypatch.setattr(
        speech, "attach_audio", AsyncMock(side_effect=RenderRefused(REASON_BUSY, 0))
    )
    monkeypatch.setattr(speech, "transcribe", AsyncMock(return_value="расшифровка"))
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"voice-bytes")
    await state.set_state(speech.SpeechStates.waiting_input)
    message = _voice_message()

    await speech.on_voice(message, db_path=db_path, state=state)

    message.answer.assert_awaited_once_with(get_string("speech_rendering", "ru"))


@pytest.mark.asyncio
async def test_voice_as_is_refusal_by_missing_job_tells_the_truth(
    db_path, state, ready_double, monkeypatch
):
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", "2026-08-01")
    monkeypatch.setattr(speech, "synthesize", AsyncMock(return_value=b"mp3"))
    monkeypatch.setattr(
        speech, "attach_audio", AsyncMock(side_effect=RenderRefused(REASON_NO_AUDIO, 0))
    )
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "1")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await state.update_data(job_id=job_id)

    callback = _callback()
    await speech.on_voice_as_is(callback, db_path=db_path, state=state)

    callback.message.answer.assert_awaited_once_with(get_string("speech_invite", "ru"))


@pytest.mark.asyncio
async def test_voice_too_long_leaves_the_user_able_to_retry(
    db_path, state, ready_double, monkeypatch
):
    # Реальный случай отказа attach_audio: запись длиннее 60 секунд.
    # Пользователь должен суметь просто прислать что-то ещё, а не упереться
    # в состояние None, где ни on_text, ни on_voice уже не сработают.
    monkeypatch.setattr(
        speech, "attach_audio", AsyncMock(side_effect=RenderRefused(REASON_TOO_LONG, 60))
    )
    monkeypatch.setattr(speech, "transcribe", AsyncMock(return_value="расшифровка"))
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"voice-bytes")
    await state.set_state(speech.SpeechStates.waiting_input)

    await speech.on_voice(_voice_message(), db_path=db_path, state=state)

    assert await state.get_state() == speech.SpeechStates.waiting_input.state


@pytest.mark.asyncio
async def test_voice_as_is_too_long_leaves_the_user_able_to_retry(
    db_path, state, ready_double, monkeypatch
):
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", "2026-08-01")
    monkeypatch.setattr(speech, "synthesize", AsyncMock(return_value=b"mp3"))
    monkeypatch.setattr(
        speech, "attach_audio", AsyncMock(side_effect=RenderRefused(REASON_TOO_LONG, 60))
    )
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "1")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await state.update_data(job_id=job_id)

    await speech.on_voice_as_is(_callback(), db_path=db_path, state=state)

    assert await state.get_state() == speech.SpeechStates.waiting_input.state


@pytest.mark.asyncio
async def test_script_button_rewrites_the_text_without_touching_the_original(
    db_path, state, ready_double, monkeypatch
):
    monkeypatch.setattr(
        speech, "generate_spoken_script", AsyncMock(return_value="Устный вариант")
    )
    job_id = create_job(db_path, TELEGRAM_ID, "Исходный текст")
    await state.update_data(job_id=job_id)

    await speech.on_script(_callback(), db_path=db_path, state=state)

    job = get_job(db_path, job_id)
    assert job.script == "Устный вариант"
    assert job.source_text == "Исходный текст"


@pytest.mark.asyncio
async def test_render_is_refused_when_the_monthly_limit_is_out(
    db_path, state, ready_double, monkeypatch
):
    # on_render зовёт request_render, а не start_render (тот вызывается уже
    # внутри speech_pipeline) — патчим и проверяем реальный путь вызова.
    request = AsyncMock()
    monkeypatch.setattr(speech, "request_render", request)
    add_usage(db_path, TELEGRAM_ID, 300, 1350.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_render(callback, db_path=db_path, state=state)

    request.assert_not_awaited()
    assert get_job(db_path, job_id).status == STATUS_VOICED
    assert "секунды" in callback.message.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_render_starts_and_reports_the_wait(
    db_path, state, ready_double, monkeypatch
):
    monkeypatch.setattr(speech, "request_render", AsyncMock())
    monkeypatch.setattr(
        speech, "ensure_min_side", AsyncMock(side_effect=lambda src, dst: src)
    )
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"image-bytes")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_render(callback, db_path=db_path, state=state)

    speech.request_render.assert_awaited_once()
    callback.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_render_refusal_by_busy_job_reports_the_render_in_progress(
    db_path, state, ready_double, monkeypatch
):
    # REASON_BUSY значит рендер уже идёт (или уже готов) и уже оплачен.
    # Звать начать заново значило бы выбросить оплаченную работу.
    monkeypatch.setattr(
        speech, "request_render", AsyncMock(side_effect=RenderRefused(REASON_BUSY, 0))
    )
    monkeypatch.setattr(
        speech, "ensure_min_side", AsyncMock(side_effect=lambda src, dst: src)
    )
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"image-bytes")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_render(callback, db_path=db_path, state=state)

    callback.message.answer.assert_awaited_once_with(get_string("speech_rendering", "ru"))


@pytest.mark.asyncio
async def test_publishing_reuses_the_cached_file_id(
    db_path, state, ready_double, monkeypatch
):
    # Второй рендер ради публикации — это второй платёж за один и тот же ролик.
    from bot.storage.users import set_channel_id

    set_channel_id(db_path, TELEGRAM_ID, -100500)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status="ready", result_file_id="note-1")
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_publish(callback, db_path=db_path, state=state)

    callback.message.bot.send_video_note.assert_awaited_once()
    assert callback.message.bot.send_video_note.await_args.args[1] == "note-1"
    assert get_job(db_path, job_id).status == "published"


@pytest.mark.asyncio
async def test_cancel_closes_the_job_with_no_spend(db_path, state, ready_double):
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await state.update_data(job_id=job_id)

    await speech.on_cancel(_callback(), db_path=db_path, state=state)

    assert get_active_job(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_a_user_outside_the_whitelist_never_reaches_the_paid_call(
    db_path, state, ready_double, monkeypatch
):
    # Подписки в боте нет, её роль играет вайтлист. Для callback_query
    # middleware не срабатывает — если забыть проверку, кружки станут
    # бесплатными для любого, кто нажмёт кнопку.
    from bot.storage.whitelist import remove_user

    remove_user(db_path, TELEGRAM_ID)
    request = AsyncMock()
    monkeypatch.setattr(speech, "request_render", request)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)

    await speech.on_render(_callback(), db_path=db_path, state=state)

    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_input_while_waiting_is_answered(db_path, state, ready_double):
    await state.set_state(speech.SpeechStates.waiting_input)
    message = _text_message("")
    message.text = None

    await speech.on_wrong_input(message, db_path=db_path, state=state)

    message.answer.assert_awaited_once()


# Finding 1 (final whole-branch review): on_cancel used to fetch ANY
# non-terminal job (including `rendering`/`ready`) and unconditionally mark it
# `failed` — abandoning an already-paid render, never releasing its reserved
# seconds and orphaning the video/audio files on disk.
@pytest.mark.asyncio
async def test_cancelling_a_rendering_job_is_refused_and_keeps_the_reservation(
    db_path, state, ready_double
):
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )
    add_usage(db_path, TELEGRAM_ID, 30, 0.0)
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_cancel(callback, db_path=db_path, state=state)

    job = get_job(db_path, job_id)
    # Бронь всё ещё на месте — рендер и правда идёт, отменять тут нечего.
    assert seconds_left(db_path, TELEGRAM_ID, 300) == 270
    # А статус не должен был уйти в `failed`: до фикса именно это и
    # происходило, оставляя оплаченный рендер без опроса и без возврата брони.
    assert job.status == STATUS_RENDERING
    callback.message.answer.assert_awaited_once_with(
        get_string("speech_rendering", "ru")
    )


@pytest.mark.asyncio
async def test_cancelling_a_ready_job_removes_the_orphaned_files(
    db_path, state, ready_double, tmp_path
):
    audio_path = tmp_path / "voice.mp3"
    audio_path.write_bytes(b"mp3")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_READY,
        audio_path=str(audio_path),
        audio_duration_sec=30.0,
    )
    video_path = tmp_path / f"speech-{job_id}.mp4"
    video_path.write_bytes(b"mp4")
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_cancel(callback, db_path=db_path, state=state)

    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert not video_path.exists()
    assert not audio_path.exists()
    callback.message.answer.assert_awaited_once_with(
        get_string("speech_cancelled", "ru")
    )


# Finding 3: ensure_min_side was dead code — nothing wired it before the
# provider call, though the provider rejects anything under 512px on its
# short side.
@pytest.mark.asyncio
async def test_render_ensures_the_look_meets_the_providers_minimum_side(
    db_path, state, ready_double, monkeypatch
):
    monkeypatch.setattr(speech, "request_render", AsyncMock())
    ensure = AsyncMock(return_value="resized-look.jpg")
    monkeypatch.setattr(speech, "ensure_min_side", ensure, raising=False)
    read_calls: list[str] = []

    def fake_read(path: str) -> bytes:
        read_calls.append(path)
        return b"image-bytes"

    monkeypatch.setattr(speech, "_read_bytes", fake_read)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_render(callback, db_path=db_path, state=state)

    ensure.assert_awaited_once()
    # Байты для рендера должны прийти из результата ensure_min_side, а не из
    # сырого скачанного файла.
    assert read_calls == ["resized-look.jpg"]


# Finding 4: _show_look_screen crashed with AttributeError on None.title when
# the user has no active look (look deleted after voicing, or a stale button).
@pytest.mark.asyncio
async def test_look_screen_survives_no_active_look(db_path):
    save_face(db_path, TELEGRAM_ID, "photo-face")
    message = MagicMock()
    message.answer = AsyncMock()

    await speech._show_look_screen(message, db_path, TELEGRAM_ID, "ru")

    message.answer.assert_awaited_once_with(get_string("speech_need_look", "ru"))
