"""Экраны речи: текст или голос → озвучка → образ → кружок.

Платит только последний шаг. Между приёмом речи и оплатой человек стоит
дважды — послушать звук и посмотреть образ бесплатно. Это главная
оптимизация расходов: платим не за ролик, а за неоплату брака.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.handlers.guards import check_limit_or_reply, check_whitelist_or_reply, safe_answer
from bot.keyboards.circle import (
    CALLBACK_SPEAK,
    CALLBACK_SPEECH_BACK_TO_TEXT,
    CALLBACK_SPEECH_CANCEL,
    CALLBACK_SPEECH_DROP,
    CALLBACK_SPEECH_OTHER_LOOK,
    CALLBACK_SPEECH_PUBLISH,
    CALLBACK_SPEECH_RENDER,
    CALLBACK_SPEECH_RETRY,
    CALLBACK_SPEECH_REVOICE,
    CALLBACK_SPEECH_REWRITE,
    CALLBACK_SPEECH_SCRIPT,
    CALLBACK_SPEECH_TO_LOOK,
    CALLBACK_SPEECH_VOICE_AS_IS,
    build_looks_keyboard,
    build_speech_failed_keyboard,
    build_speech_look_keyboard,
    build_speech_text_keyboard,
    build_speech_voiced_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import TranscriptionError, transcribe
from bot.services.avatar_gateway import AvatarGatewayError, start_render
from bot.services.content_generator import generate_spoken_script
from bot.services.speech_pipeline import (
    REASON_LIMIT,
    RenderRefused,
    attach_audio,
    request_render,
)
from bot.services.voice_gateway import VoiceGatewayError, synthesize
from bot.storage.avatar_faces import get_face
from bot.storage.avatar_looks import count_looks, get_active_look, get_looks
from bot.storage.limits import increment_usage
from bot.storage.render_usage import seconds_left
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_PUBLISHED,
    create_job,
    get_active_job,
    get_job,
    update_job,
)
from bot.storage.style_examples import KIND_SPOKEN, get_style_examples
from bot.storage.users import get_channel_id
from bot.storage.voice_profiles import get_voice_profile

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="speech")


class SpeechStates(StatesGroup):
    waiting_input = State()


def _read_bytes(path: str) -> bytes:
    # Вынесено функцией, чтобы тесты подменяли чтение диска, не трогая
    # остальную логику обработчика — тот же приём, что в double.py.
    return pathlib.Path(path).read_bytes()


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


async def _current_job(db_path: str, state: FSMContext, telegram_id: int):
    """Задание этого разговора.

    Сначала из состояния диалога, потом из базы: после рестарта бота состояние
    пусто, а оплаченное задание никуда не делось.
    """
    data = await state.get_data()
    job_id = data.get("job_id")
    job = get_job(db_path, job_id) if job_id else None
    return job or get_active_job(db_path, telegram_id)


async def _show_text_screen(message: Message, language: str, text: str) -> None:
    await message.answer(
        get_string("speech_text_received", language, text=text),
        reply_markup=build_speech_text_keyboard(language),
    )


async def _show_look_screen(
    message: Message, db_path: str, telegram_id: int, language: str
) -> None:
    active = get_active_look(db_path, telegram_id)
    await message.answer(
        get_string("speech_look_screen", language, title=active.title),
        reply_markup=build_speech_look_keyboard(
            language, has_other_looks=count_looks(db_path, telegram_id) > 1
        ),
    )


@router.callback_query(F.data == CALLBACK_SPEAK)
async def on_speak(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    # Вайтлист — он же список купивших подписку. Для callback_query
    # middleware не срабатывает, проверяем руками.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if get_face(db_path, telegram_id) is None:
        await callback.message.answer(get_string("speech_need_face", language))
        await safe_answer(callback)
        return
    if get_active_look(db_path, telegram_id) is None:
        await callback.message.answer(get_string("speech_need_look", language))
        await safe_answer(callback)
        return

    await state.set_state(SpeechStates.waiting_input)
    await callback.message.answer(get_string("speech_invite", language))
    await safe_answer(callback)


@router.message(SpeechStates.waiting_input, F.text)
async def on_text(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    job_id = create_job(db_path, telegram_id, message.text.strip())
    await state.set_state(None)
    await state.update_data(job_id=job_id)
    await _show_text_screen(message, language, message.text.strip())


@router.message(SpeechStates.waiting_input, F.voice)
async def on_voice(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    audio_path = _tmp_path(".ogg")
    try:
        await message.bot.download(message.voice.file_id, destination=audio_path)
        audio_bytes = _read_bytes(audio_path)
    finally:
        pathlib.Path(audio_path).unlink(missing_ok=True)

    transcript = ""
    try:
        transcript = await transcribe(audio_bytes)
    except TranscriptionError:
        # Расшифровка нужна только чтобы было что переписывать текстом.
        # Сам кружок снимется и без неё — звук уже есть. Не гейтим этот
        # вызов общей квотой (как и donor-транскрипция в circle.py):
        # голосовое — самый дешёвый путь и главная его часть уже бесплатна
        # без него — звук всё равно приложится к заданию.
        logger.warning(
            "Speech transcription failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )

    job_id = create_job(db_path, telegram_id, transcript)
    await state.set_state(None)
    await state.update_data(job_id=job_id)

    try:
        duration = await attach_audio(db_path, job_id, audio_bytes)
    except RenderRefused as refusal:
        await message.answer(get_string("speech_too_long", language, limit=refusal.detail))
        return

    await message.answer(
        get_string("speech_voiced", language, seconds=int(round(duration))),
        reply_markup=build_speech_voiced_keyboard(language),
    )


@router.message(SpeechStates.waiting_input)
async def on_wrong_input(message: Message, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, message.from_user.id, message.from_user.language_code)
    await message.answer(get_string("speech_expected_input", language))


@router.callback_query(F.data == CALLBACK_SPEECH_SCRIPT)
async def on_script(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    # Платный вызов ИИ (пересказ текста под устную речь) — доступ и общая
    # квота проверяются здесь же, а не только в on_speak: до этой кнопки
    # можно дойти по клавиатуре, оставшейся в чате с прошлого раза, а
    # middleware для callback_query не срабатывает вовсе.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return
    if not await check_limit_or_reply(callback, db_path, language):
        return

    job = await _current_job(db_path, state, telegram_id)
    if job is None:
        await safe_answer(callback)
        return

    settings = load_settings()
    # get_style_examples возвращает список строк, а не объектов.
    examples = get_style_examples(db_path, telegram_id, kind=KIND_SPOKEN)
    try:
        script = await generate_spoken_script(
            job.source_text,
            target_seconds=settings.avatar_target_seconds,
            spoken_examples=examples,
        )
    except Exception:
        logger.warning(
            "Spoken script generation failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )
        await callback.message.answer(get_string("speech_script_failed", language))
        await safe_answer(callback)
        return

    # Оплата — свершившийся факт с момента, когда generate_spoken_script
    # вернул текст, а не после успешной доставки в Telegram (тот же порядок,
    # что и в double.py/refine.py): сбой отправки не должен списывать деньги
    # молча.
    increment_usage(db_path, telegram_id)

    # Исходный текст не затирается: с него начинается «Переписать».
    update_job(db_path, job.id, script=script)
    await _show_text_screen(callback.message, language, script)
    await safe_answer(callback)


@router.callback_query(F.data == CALLBACK_SPEECH_VOICE_AS_IS)
async def on_voice_as_is(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    # Вайтлист проверяется независимо от ветки ниже: суфлёр бесплатен, но
    # сам факт нажатия платной кнопки должен быть доступен только своим —
    # иначе чужой человек по старой клавиатуре узнает, что синтез выключен.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    job = await _current_job(db_path, state, telegram_id)
    if job is None:
        await safe_answer(callback)
        return

    text = job.script or job.source_text
    settings = load_settings()
    profile = get_voice_profile(db_path, telegram_id)

    if not settings.avatar_voice_synthesis_enabled or profile is None:
        # Клона ещё нет — отдаём суфлёр. Это выход, а не отказ: пользователь
        # наговорит тот же текст сам, и кружок всё равно получится.
        await callback.message.answer(get_string("speech_prompter", language, text=text))
        await state.set_state(SpeechStates.waiting_input)
        await safe_answer(callback)
        return

    # Платный вызов ElevenLabs — квота проверяется прямо перед ним, не раньше:
    # бесплатная ветка суфлёра выше не должна на неё натыкаться.
    if not await check_limit_or_reply(callback, db_path, language):
        return

    try:
        audio_bytes = await synthesize(text, profile.external_voice_id)
    except VoiceGatewayError:
        logger.warning(
            "Speech synthesis failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )
        await callback.message.answer(get_string("speech_voice_failed", language))
        await safe_answer(callback)
        return

    # Списываем сразу после успешного платного вызова, до attach_audio и до
    # отправки: ffmpeg-замер длительности или сбой доставки не должны
    # обнулять уже потраченные деньги за синтез.
    increment_usage(db_path, telegram_id)

    try:
        duration = await attach_audio(db_path, job.id, audio_bytes)
    except RenderRefused as refusal:
        await callback.message.answer(
            get_string("speech_too_long", language, limit=refusal.detail)
        )
        await safe_answer(callback)
        return

    await callback.message.answer_voice(BufferedInputFile(audio_bytes, filename="speech.mp3"))
    await callback.message.answer(
        get_string("speech_voiced", language, seconds=int(round(duration))),
        reply_markup=build_speech_voiced_keyboard(language),
    )
    await safe_answer(callback)


@router.callback_query(
    F.data.in_(
        {CALLBACK_SPEECH_REWRITE, CALLBACK_SPEECH_BACK_TO_TEXT, CALLBACK_SPEECH_REVOICE}
    )
)
async def on_back_to_input(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(
        db_path, callback.from_user.id, callback.from_user.language_code
    )
    await state.set_state(SpeechStates.waiting_input)
    await callback.message.answer(get_string("speech_invite", language))
    await safe_answer(callback)


@router.callback_query(F.data == CALLBACK_SPEECH_TO_LOOK)
async def on_to_look(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    await _show_look_screen(callback.message, db_path, telegram_id, language)
    await safe_answer(callback)


@router.callback_query(F.data == CALLBACK_SPEECH_OTHER_LOOK)
async def on_other_look(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    active = get_active_look(db_path, telegram_id)
    await callback.message.answer(
        get_string(
            "looks_title",
            language,
            count=count_looks(db_path, telegram_id),
            # Активного может не быть: последний образ мог быть удалён уже
            # после того, как эта клавиатура была нарисована.
            active=active.title if active else get_string("double_look_none", language),
        ),
        reply_markup=build_looks_keyboard(language, get_looks(db_path, telegram_id)),
    )
    await safe_answer(callback)


@router.callback_query(F.data.in_({CALLBACK_SPEECH_RENDER, CALLBACK_SPEECH_RETRY}))
async def on_render(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    # Самый дорогой вызов во всём боте — проверка обязана стоять и здесь,
    # а не только на входе в сценарий: до этой кнопки можно дойти по старой
    # клавиатуре, оставшейся в чате с прошлого раза.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    job = await _current_job(db_path, state, telegram_id)
    look = get_active_look(db_path, telegram_id)
    if job is None or look is None:
        await callback.message.answer(get_string("speech_need_look", language))
        await safe_answer(callback)
        return

    # Быстрая проверка месячного лимита до скачивания образа из Telegram:
    # заведомо отказанный запрос иначе всё равно тянет фото впустую.
    # Настоящее (атомарное, без await между проверкой и бронью) решение
    # принимает request_render — это лишь дешёвый предфильтр по тому же
    # правилу, безопасный даже при гонке двух запросов подряд.
    if job.audio_duration_sec:
        settings = load_settings()
        needed = int(round(job.audio_duration_sec))
        left = seconds_left(db_path, telegram_id, settings.avatar_monthly_seconds_limit)
        if needed > left:
            await callback.message.answer(
                get_string("speech_limit_exceeded", language, left=left)
            )
            await safe_answer(callback)
            return

    look_path = _tmp_path(".jpg")
    try:
        await callback.message.bot.download(look.file_id, destination=look_path)
        image_bytes = _read_bytes(look_path)
    finally:
        pathlib.Path(look_path).unlink(missing_ok=True)

    try:
        await request_render(db_path, job.id, image_bytes, look_id=look.id)
    except RenderRefused as refusal:
        if refusal.reason == REASON_LIMIT:
            await callback.message.answer(
                get_string("speech_limit_exceeded", language, left=refusal.detail)
            )
        else:
            # REASON_NO_AUDIO/REASON_BUSY: задание пропало или уже ушло
            # дальше по статусам (стало rendering/ready/published между
            # показом клавиатуры и тапом). Числа тут нет и врать про предел
            # формата нечем — просим начать заново с чистого экрана.
            await callback.message.answer(get_string("speech_invite", language))
            await state.set_state(SpeechStates.waiting_input)
        await safe_answer(callback)
        return
    except AvatarGatewayError:
        logger.error(
            "Render start failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )
        update_job(db_path, job.id, status=STATUS_FAILED, error="запуск рендера не удался")
        await callback.message.answer(
            get_string("speech_failed", language),
            reply_markup=build_speech_failed_keyboard(language),
        )
        await safe_answer(callback)
        return

    await callback.message.answer(get_string("speech_rendering", language))
    await safe_answer(callback)


@router.callback_query(F.data == CALLBACK_SPEECH_PUBLISH)
async def on_publish(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    job = await _current_job(db_path, state, telegram_id)
    channel_id = get_channel_id(db_path, telegram_id)
    if job is None or job.result_file_id is None or channel_id is None:
        await safe_answer(callback)
        return

    # Публикация по file_id: рендер уже оплачен, второй раз платить не за что.
    await callback.message.bot.send_video_note(channel_id, job.result_file_id)
    update_job(db_path, job.id, status=STATUS_PUBLISHED)
    await callback.message.answer(get_string("publish_success", language))
    await safe_answer(callback)


@router.callback_query(F.data.in_({CALLBACK_SPEECH_CANCEL, CALLBACK_SPEECH_DROP}))
async def on_cancel(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    job = await _current_job(db_path, state, telegram_id)
    if job is not None:
        # Закрытое задание перестаёт быть активным — следующая речь начнётся
        # с чистого листа. Отдельного статуса «отменено» не заводим: для всей
        # остальной логики отменённое и несостоявшееся ведут себя одинаково.
        update_job(db_path, job.id, status=STATUS_FAILED, error="отменено пользователем")
    await state.set_state(None)
    await state.update_data(job_id=None)
    await callback.message.answer(get_string("speech_cancelled", language))
    await safe_answer(callback)
