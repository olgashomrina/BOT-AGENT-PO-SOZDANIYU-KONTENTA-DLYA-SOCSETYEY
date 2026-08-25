"""Экраны лица и образов двойника.

Отдельно от `circle.py`: тот отвечает за сбор кружков-доноров и голос, и вместе
эти три сценария не помещаются в один читаемый файл.
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
from bot.handlers.guards import check_whitelist_or_reply
from bot.keyboards.circle import (
    CALLBACK_FACE,
    CALLBACK_LOOK_ACTIVATE_PREFIX,
    CALLBACK_LOOK_ADD_PHOTO,
    CALLBACK_LOOK_ADD_PROMPT,
    CALLBACK_LOOK_DELETE_PREFIX,
    CALLBACK_LOOKS,
    build_look_actions_keyboard,
    build_looks_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import AIGatewayError, edit_image
from bot.services.cost_tracker import image_cost
from bot.services.look_prompt import build_look_prompt, mentions_hair
from bot.storage.avatar_faces import get_face, save_face
from bot.storage.avatar_looks import (
    SOURCE_GENERATED,
    SOURCE_UPLOADED,
    add_look,
    count_looks,
    delete_look,
    get_active_look,
    get_look,
    get_looks,
    set_active_look,
)
from bot.storage.costs import record_cost

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="double")

OPERATION_LOOK = "avatar_look"

# Длинное описание в подписи кнопки не помещается, а короткое — вся навигация
# по образам. Режем по границе, а не по букве.
_TITLE_LIMIT = 40


class DoubleStates(StatesGroup):
    waiting_face = State()
    waiting_look_photo = State()
    waiting_look_prompt = State()


def _read_bytes(path: str) -> bytes:
    # Вынесено функцией, чтобы тесты подменяли чтение диска — тот же приём,
    # что в circle.py.
    return pathlib.Path(path).read_bytes()


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


def _short_title(text: str, fallback: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return fallback
    return cleaned if len(cleaned) <= _TITLE_LIMIT else cleaned[: _TITLE_LIMIT - 1] + "…"


async def show_looks(message: Message, db_path: str, telegram_id: int, language: str) -> None:
    # Публичная функция: task-18 отдаёт её как интерфейс, которым сможет
    # пользоваться экран речи (task 19) — например, после того как активный
    # образ сменился прямо из галереи.
    looks = get_looks(db_path, telegram_id)
    active = get_active_look(db_path, telegram_id)
    await message.answer(
        get_string(
            "looks_title",
            language,
            count=len(looks),
            active=active.title if active else get_string("double_look_none", language),
        ),
        reply_markup=build_looks_keyboard(language, looks),
    )


@router.callback_query(F.data == CALLBACK_FACE)
async def on_face_request(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, callback.from_user.id, callback.from_user.language_code)
    await state.set_state(DoubleStates.waiting_face)
    await callback.message.answer(get_string("face_invite", language))
    await callback.answer()


@router.message(DoubleStates.waiting_face, F.photo)
async def on_face_photo(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    # Последний элемент — самый крупный размер. Сходство лица держится на
    # резкости, брать мелкий превью нельзя.
    save_face(db_path, telegram_id, message.photo[-1].file_id)
    await state.set_state(None)
    await message.answer(get_string("face_saved", language))
    await show_looks(message, db_path, telegram_id, language)


@router.message(DoubleStates.waiting_face)
async def on_face_wrong_input(message: Message, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, message.from_user.id, message.from_user.language_code)
    await message.answer(get_string("face_expected_photo", language))


@router.callback_query(F.data == CALLBACK_LOOKS)
async def on_looks(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    await state.set_state(None)
    await show_looks(callback.message, db_path, telegram_id, language)
    await callback.answer()


@router.callback_query(F.data == CALLBACK_LOOK_ADD_PHOTO)
async def on_look_add_photo(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, callback.from_user.id, callback.from_user.language_code)
    await state.set_state(DoubleStates.waiting_look_photo)
    await callback.message.answer(get_string("looks_upload_invite", language))
    await callback.answer()


@router.message(DoubleStates.waiting_look_photo, F.photo)
async def on_look_photo(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    title = _short_title(
        message.caption or "", f"Образ {count_looks(db_path, telegram_id) + 1}"
    )
    add_look(db_path, telegram_id, message.photo[-1].file_id, title, SOURCE_UPLOADED)
    await state.set_state(None)
    await message.answer(get_string("looks_saved", language))
    await show_looks(message, db_path, telegram_id, language)


@router.message(DoubleStates.waiting_look_photo)
async def on_look_photo_wrong_input(message: Message, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, message.from_user.id, message.from_user.language_code)
    await message.answer(get_string("face_expected_photo", language))


@router.callback_query(F.data == CALLBACK_LOOK_ADD_PROMPT)
async def on_look_add_prompt(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    # WhitelistMiddleware зарегистрирован только на сообщениях (bot/main.py) и
    # для callback_query не срабатывает вовсе. Отсюда уходит платный вызов,
    # поэтому проверка нужна руками — так же, как в остальных хендлерах.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if get_face(db_path, telegram_id) is None:
        # Отказ до денег и до состояния: генерировать образ не из чего.
        await callback.message.answer(get_string("looks_need_face", language))
        await callback.answer()
        return

    await state.set_state(DoubleStates.waiting_look_prompt)
    await callback.message.answer(get_string("looks_prompt_invite", language))
    await callback.answer()


@router.message(DoubleStates.waiting_look_prompt, F.text)
async def on_look_prompt(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)
    description = message.text.strip()

    face = get_face(db_path, telegram_id)
    if face is None:
        await message.answer(get_string("looks_need_face", language))
        await state.set_state(None)
        return

    if mentions_hair(description):
        # Предупреждение, а не запрет: владелец решила эту возможность оставить,
        # но модель на таких просьбах уводит и лицо тоже.
        await message.answer(get_string("looks_hair_warning", language))

    await message.answer(get_string("looks_building", language))

    face_path = _tmp_path(".jpg")
    try:
        await message.bot.download(face.file_id, destination=face_path)
        image_bytes = await edit_image(
            _read_bytes(face_path), build_look_prompt(description)
        )
    except AIGatewayError:
        logger.warning(
            "Look generation failed",
            extra={"user_id": telegram_id, "operation": "handler:double"},
            exc_info=True,
        )
        await message.answer(get_string("looks_failed", language))
        await state.set_state(None)
        return
    finally:
        pathlib.Path(face_path).unlink(missing_ok=True)

    settings = load_settings()
    sent = await message.answer_photo(
        BufferedInputFile(image_bytes, filename="look.jpg")
    )
    add_look(
        db_path,
        telegram_id,
        sent.photo[-1].file_id,
        _short_title(description, f"Образ {count_looks(db_path, telegram_id) + 1}"),
        SOURCE_GENERATED,
        prompt=description,
    )
    record_cost(
        db_path,
        telegram_id,
        OPERATION_LOOK,
        settings.avatar_look_model,
        image_cost(settings.avatar_look_model),
    )

    await state.set_state(None)
    await message.answer(get_string("looks_saved", language))
    await show_looks(message, db_path, telegram_id, language)


@router.callback_query(F.data.startswith(f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:"))
async def on_look_activate(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    look_id = int(callback.data.rsplit(":", 1)[1])

    set_active_look(db_path, telegram_id, look_id)
    look = get_look(db_path, telegram_id, look_id)
    if look is not None:
        await callback.message.answer_photo(
            look.file_id,
            caption=get_string("looks_activated", language),
            reply_markup=build_look_actions_keyboard(language, look_id, is_active=True),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CALLBACK_LOOK_DELETE_PREFIX}:"))
async def on_look_delete(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    look_id = int(callback.data.rsplit(":", 1)[1])

    delete_look(db_path, telegram_id, look_id)
    await callback.message.answer(get_string("look_deleted", language))
    await show_looks(callback.message, db_path, telegram_id, language)
    await callback.answer()
