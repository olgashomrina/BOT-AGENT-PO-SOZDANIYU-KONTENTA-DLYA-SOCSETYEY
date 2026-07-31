# bot/handlers/site.py
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _finish, _resolve_language
from bot.handlers.guards import check_limit_or_reply, check_whitelist_or_reply
from bot.keyboards.site import PILOT_BLOCK, PILOT_PAGE, build_site_menu_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.media_cache import cache_photo
from bot.storage.limits import increment_usage
from bot.storage.site_content import get_site_content, upsert_site_content
from bot.storage.users import get_pending_media, set_pending_media

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="site")


@router.message(Command("site"))
async def cmd_site(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)
    settings = load_settings()

    await message.answer(
        get_string("site_menu_intro", language),
        reply_markup=build_site_menu_keyboard(settings.mini_app_url, language),
    )


@router.callback_query(F.data.startswith("site:pull:"))
async def on_site_pull(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return
    if not await check_limit_or_reply(callback, db_path, language):
        return

    _, _, page, block_id = callback.data.split(":")
    content = get_site_content(db_path, page, block_id)

    if content is None or not content.text:
        await callback.message.answer(get_string("site_pull_empty", language))
        await callback.answer()
        return

    if content.photo_file_id:
        set_pending_media(db_path, telegram_id, content.photo_file_id, "photo")

    increment_usage(db_path, telegram_id)
    await _finish(callback.message, language, content.text, state, telegram_id, db_path)
    await callback.answer()


@router.callback_query(F.data.startswith("site:push:"))
async def on_site_push(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    variant_text = callback.message.text or ""
    pending_media = get_pending_media(db_path, telegram_id)
    existing = get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK)

    photo_file_id = existing.photo_file_id if existing else None
    photo_static_path = existing.photo_static_path if existing else None

    if pending_media is not None:
        file_id, media_type = pending_media
        if media_type == "photo":
            settings = load_settings()
            try:
                photo_static_path = await cache_photo(
                    bot, file_id, settings.site_media_dir, PILOT_PAGE, PILOT_BLOCK
                )
            except (TelegramAPIError, OSError):
                logger.warning(
                    "Failed to cache photo for site push",
                    extra={"user_id": telegram_id, "operation": "site_push"},
                )
                await callback.message.answer(get_string("site_push_photo_failed", language))
                await callback.answer()
                return
            photo_file_id = file_id

    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, variant_text, photo_file_id, photo_static_path)

    await callback.message.answer(get_string("site_push_success", language))
    await callback.answer()
