from __future__ import annotations

import logging
import pathlib
import uuid
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.keyboards.circle import (
    CALLBACK_ADD_DONORS,
    CALLBACK_CONSENT_ACCEPT,
    CALLBACK_DELETE,
    CALLBACK_DELETE_CONFIRM,
    CALLBACK_DONORS_DONE,
    CALLBACK_MY_DOUBLE,
    build_consent_keyboard,
    build_delete_confirm_keyboard,
    build_donors_keyboard,
    build_my_double_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import TranscriptionError, transcribe
from bot.services.ffmpeg_tools import (
    FfmpegError,
    concat_audio,
    extract_audio,
    probe_duration,
)
from bot.services.voice_gateway import (
    PROVIDER_NAME,
    VoiceGatewayError,
    clone_voice,
    delete_voice,
)
from bot.storage.avatar_donors import (
    MIN_DONOR_COUNT,
    MIN_DONOR_SECONDS,
    add_donor,
    clear_donors,
    count_donors,
    get_donors,
)
from bot.storage.avatar_faces import get_face
from bot.storage.avatar_looks import count_looks, get_active_look
from bot.storage.style_examples import (
    KIND_SPOKEN,
    add_style_example,
    clear_style_examples,
)
from bot.storage.voice_profiles import (
    delete_voice_profile,
    get_voice_profile,
    save_voice_profile,
)

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="circle")


class CircleStates(StatesGroup):
    collecting_donors = State()


def _read_bytes(path: str) -> bytes:
    # Вынесено отдельной функцией, чтобы тесты подменяли чтение диска, не
    # трогая остальную логику обработчика.
    return pathlib.Path(path).read_bytes()


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


@router.callback_query(F.data == CALLBACK_MY_DOUBLE)
async def on_my_double(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    donors = count_donors(db_path, telegram_id)
    profile = get_voice_profile(db_path, telegram_id)
    face = get_face(db_path, telegram_id)
    active_look = get_active_look(db_path, telegram_id)
    looks_count = count_looks(db_path, telegram_id)

    if donors == 0 and profile is None and face is None:
        await callback.message.answer(
            get_string("double_consent_text", language),
            reply_markup=build_consent_keyboard(language),
        )
        await callback.answer()
        return

    await callback.message.answer(
        get_string(
            "double_status_full",
            language,
            face=get_string(
                "double_face_present" if face else "double_face_missing", language
            ),
            looks=looks_count,
            active=active_look.title
            if active_look
            else get_string("double_look_none", language),
        ),
        reply_markup=build_my_double_keyboard(
            language, has_face=face is not None, has_look=active_look is not None
        ),
    )
    await callback.answer()


@router.callback_query(F.data.in_({CALLBACK_CONSENT_ACCEPT, CALLBACK_ADD_DONORS}))
async def on_consent_accept(
    callback: CallbackQuery, db_path: str, state: FSMContext
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    await state.set_state(CircleStates.collecting_donors)
    # Момент согласия фиксируем здесь и переносим в voice_profiles при
    # создании голоса — это и есть юридический артефакт.
    await state.update_data(consent_at=datetime.now(timezone.utc).isoformat())

    collected = count_donors(db_path, telegram_id)
    await callback.message.answer(
        get_string("double_donors_invite", language, minimum=MIN_DONOR_COUNT),
        reply_markup=build_donors_keyboard(
            language, can_finish=collected >= MIN_DONOR_COUNT
        ),
    )
    await callback.answer()


@router.message(CircleStates.collecting_donors, F.video_note)
async def on_donor_video_note(
    message: Message, db_path: str, state: FSMContext
) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    video_path = _tmp_path(".mp4")
    audio_path = _tmp_path(".wav")
    try:
        await message.bot.download(message.video_note.file_id, destination=video_path)
        try:
            duration = await probe_duration(video_path)
        except FfmpegError:
            # ffprobe не смог прочитать файл — доверяем длительности,
            # которую Telegram кладёт в само сообщение.
            duration = float(message.video_note.duration)

        if duration < MIN_DONOR_SECONDS:
            await message.answer(
                get_string("double_donor_too_short", language, minimum=MIN_DONOR_SECONDS),
                reply_markup=build_donors_keyboard(
                    language,
                    can_finish=count_donors(db_path, telegram_id) >= MIN_DONOR_COUNT,
                ),
            )
            return

        transcript: str | None = None
        try:
            await extract_audio(video_path, audio_path)
            transcript = await transcribe(_read_bytes(audio_path))
        except (FfmpegError, TranscriptionError):
            # Донор всё равно ценен: устный стиль соберётся из остальных.
            logger.warning(
                "Donor transcription failed",
                extra={"user_id": telegram_id, "operation": "handler:circle"},
                exc_info=True,
            )

        add_donor(
            db_path,
            telegram_id,
            message.video_note.file_id,
            int(duration),
            transcript,
        )
        if transcript:
            add_style_example(db_path, telegram_id, transcript, kind=KIND_SPOKEN)
    finally:
        pathlib.Path(video_path).unlink(missing_ok=True)
        pathlib.Path(audio_path).unlink(missing_ok=True)

    collected = count_donors(db_path, telegram_id)
    await message.answer(
        get_string(
            "double_donor_saved", language, collected=collected, minimum=MIN_DONOR_COUNT
        ),
        reply_markup=build_donors_keyboard(
            language, can_finish=collected >= MIN_DONOR_COUNT
        ),
    )


@router.callback_query(F.data == CALLBACK_DONORS_DONE)
async def on_donors_done(
    callback: CallbackQuery, db_path: str, state: FSMContext
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    donors = get_donors(db_path, telegram_id)
    if len(donors) < MIN_DONOR_COUNT:
        await callback.message.answer(
            get_string("double_need_more_donors", language, minimum=MIN_DONOR_COUNT)
        )
        await callback.answer()
        return

    await callback.message.answer(get_string("double_voice_building", language))

    audio_paths: list[str] = []
    combined_path = _tmp_path(".wav")
    try:
        for donor in donors:
            video_path = _tmp_path(".mp4")
            audio_path = _tmp_path(".wav")
            await callback.message.bot.download(donor.file_id, destination=video_path)
            await extract_audio(video_path, audio_path)
            pathlib.Path(video_path).unlink(missing_ok=True)
            audio_paths.append(audio_path)

        # Один кружок — 30-60 секунд, а клонированию нужны 1-2 минуты речи,
        # поэтому дорожки всех доноров склеиваются в одну.
        await concat_audio(audio_paths, combined_path)
        voice_id = await clone_voice(_read_bytes(combined_path), f"double-{telegram_id}")
    except (FfmpegError, VoiceGatewayError):
        logger.error(
            "Voice cloning failed",
            extra={"user_id": telegram_id, "operation": "handler:circle"},
            exc_info=True,
        )
        await callback.message.answer(get_string("double_voice_failed", language))
        await callback.answer()
        return
    finally:
        for path in [*audio_paths, combined_path]:
            pathlib.Path(path).unlink(missing_ok=True)

    data = await state.get_data()
    consent_at = data.get("consent_at") or datetime.now(timezone.utc).isoformat()
    save_voice_profile(db_path, telegram_id, PROVIDER_NAME, voice_id, consent_at)

    # Состояние сбрасываем немедленно: пока оно выставлено, обычные текстовые
    # сообщения перехватывает этот роутер, и бот перестаёт отвечать на всё
    # остальное (та же причина, что в сценарии авторского поста).
    await state.set_state(None)
    await callback.message.answer(
        get_string("double_ready", language, donors=len(donors)),
        reply_markup=build_my_double_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == CALLBACK_DELETE)
async def on_delete_request(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    await callback.message.answer(
        get_string("double_delete_confirm_text", language),
        reply_markup=build_delete_confirm_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == CALLBACK_DELETE_CONFIRM)
async def on_delete_confirm(
    callback: CallbackQuery, db_path: str, state: FSMContext
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    profile = get_voice_profile(db_path, telegram_id)
    if profile is not None:
        try:
            await delete_voice(profile.external_voice_id)
        except VoiceGatewayError:
            # Локальные данные стираем в любом случае: обещание «удалю всё»
            # не должно зависеть от доступности чужого сервиса. Осиротевший
            # голос у провайдера удаляется руками, это видно в логах.
            logger.error(
                "Provider voice deletion failed, wiping local data anyway",
                extra={"user_id": telegram_id, "operation": "handler:circle"},
                exc_info=True,
            )

    delete_voice_profile(db_path, telegram_id)
    clear_donors(db_path, telegram_id)
    clear_style_examples(db_path, telegram_id, kind=KIND_SPOKEN)
    await state.set_state(None)

    await callback.message.answer(get_string("double_deleted", language))
    await callback.answer()


@router.message(CircleStates.collecting_donors)
async def on_non_video_note(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    await message.answer(
        get_string("double_expected_video_note", language),
        reply_markup=build_donors_keyboard(
            language, can_finish=count_donors(db_path, telegram_id) >= MIN_DONOR_COUNT
        ),
    )
