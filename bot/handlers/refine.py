from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.config import load_settings
from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language
from bot.handlers.guards import (
    check_limit_or_reply,
    check_whitelist_or_reply,
    safe_answer,
)
from bot.handlers.image_budget import ensure_image_budget
from bot.keyboards.refine import (
    CALLBACK_IMAGE_UPGRADE,
    CALLBACK_IMAGE_UPGRADE_DONE,
    build_image_upgrade_keyboard,
    build_image_upgraded_keyboard,
    build_refine_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import (
    ai_gateway,
    content_generator,
    cost_tracker,
    output_formatter,
    platform_package,
    post_length,
)
from bot.services.ai_gateway import AIGatewayError
from bot.services.content_generator import SHORTEN_INSTRUCTION
from bot.storage.costs import record_cost
from bot.storage.image_prompts import claim_image_prompt, save_image_prompt
from bot.storage.limits import increment_image_usage, increment_usage
from bot.storage.refine_context import get_refine_context, save_refine_context
from bot.storage.style_examples import get_style_examples
from bot.storage.style_profile import get_style_profile
from bot.storage.users import (
    clear_pending_media,
    get_channel_id,
    get_pending_media,
    get_post_length,
    set_pending_media,
)

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="refine")


async def _generate_and_send(
    callback: CallbackQuery,
    state: FSMContext,
    db_path: str,
    platform: str,
    shorten: bool,
) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if not await check_limit_or_reply(callback, db_path, language):
        return

    # WHY the context is keyed on this message rather than read from FSM: FSM
    # data is per chat, so the next generation overwrites it. Telegram keeps
    # old buttons alive indefinitely, so a tap on an older post would otherwise
    # regenerate from whatever was generated most recently — a different topic,
    # and with hashtags added or dropped to match that other post.
    context = get_refine_context(db_path, callback.message.chat.id, callback.message.message_id)
    if context is None:
        await callback.message.answer(get_string("error_refine_missing_context", language))
        await safe_answer(callback)
        return

    source_text = context["source_text"]
    content_language = context["content_language"]
    with_hashtags = context["with_hashtags"]
    style_examples = get_style_examples(db_path, telegram_id)
    style_profile = get_style_profile(db_path, telegram_id)

    # «Короче» теперь означает «на один пресет короче», а не расплывчатое
    # словесное указание: у нижней ступени лестницы шага нет, поэтому там
    # сохраняется прежняя формулировка. У VK пресетов нет вовсе.
    extra_instruction: str | None = None
    length_preset: str | None = None
    if platform == "telegram":
        length_preset = get_post_length(db_path, telegram_id)
        if shorten:
            shorter = post_length.next_shorter(length_preset)
            if shorter is None:
                extra_instruction = SHORTEN_INSTRUCTION
            else:
                length_preset = shorter
    elif shorten:
        extra_instruction = SHORTEN_INSTRUCTION

    try:
        variants = await content_generator.generate_variants(
            source_text,
            platform,
            content_language,
            count=1,
            extra_instruction=extra_instruction,
            style_examples=style_examples,
            with_hashtags=with_hashtags,
            style_profile=style_profile,
            length_preset=length_preset,
        )
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during refine",
            extra={"user_id": telegram_id, "operation": "refine_generate", "error_class": type(exc).__name__},
        )
        await callback.message.answer(get_string(error_key, language))
        await safe_answer(callback)
        return

    increment_usage(db_path, telegram_id)

    variant = variants[0]
    sent = await callback.message.answer(
        output_formatter.format_variant(variant),
        parse_mode=output_formatter.PARSE_MODE,
        reply_markup=build_refine_keyboard(platform, 1, language),
    )
    save_refine_context(
        db_path,
        callback.message.chat.id,
        sent.message_id,
        source_text,
        content_language,
        with_hashtags,
        platform,
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith("refine:more:"))
async def on_refine_more(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    platform = callback.data.split(":")[2]
    await _generate_and_send(callback, state, db_path, platform, shorten=False)


@router.callback_query(F.data.startswith("refine:shorten:"))
async def on_refine_shorten(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    platform = callback.data.split(":")[2]
    await _generate_and_send(callback, state, db_path, platform, shorten=True)


@router.callback_query(F.data.startswith("refine:publish:"))
async def on_refine_publish(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    channel_id = get_channel_id(db_path, telegram_id)
    if channel_id is None:
        await callback.message.answer(get_string("publish_no_channel_configured", language))
        await safe_answer(callback)
        return

    # WHY read the text off callback.message rather than re-deriving it from
    # FSM data: the publish button is attached to one already-generated,
    # already-shown variant message specifically — FSM data (source_text)
    # only ever holds the original input used to (re)generate variants, not
    # any individual variant's text (see _generate_and_send above), and
    # there can be several variant messages in the chat at once. The exact
    # text the user approved is the text of the message the button sits
    # under, sent earlier via output_formatter.format_variant() with HTML
    # parse_mode; since that formatting only escapes &/</>, Telegram hands
    # the plain (unescaped) variant text straight back as callback.message.text.
    variant_text = callback.message.text or ""
    pending_media = get_pending_media(db_path, telegram_id)

    # WHY подрезаем ДО экранирования: format_variant() превращает «&» в
    # «&amp;», и обрезка уже экранированной строки может разрубить сущность
    # пополам («&am»). Telegram отклоняет такое сообщение целиком, то есть
    # починка длины ломала публикацию вместо того, чтобы её спасать.
    # Подпись к медиа считается по разобранному тексту, поэтому мерять надо
    # именно чистый вариант.
    body = variant_text
    if pending_media is not None:
        body = post_length.trim(variant_text, post_length.TELEGRAM_CAPTION_LIMIT)
    formatted_text = output_formatter.format_variant(body)

    try:
        if pending_media is None:
            await bot.send_message(channel_id, formatted_text, parse_mode=output_formatter.PARSE_MODE)
        else:
            file_id, media_type = pending_media
            if media_type == "photo":
                await bot.send_photo(
                    channel_id,
                    photo=file_id,
                    caption=formatted_text,
                    parse_mode=output_formatter.PARSE_MODE,
                )
            else:
                await bot.send_video(
                    channel_id,
                    video=file_id,
                    caption=formatted_text,
                    parse_mode=output_formatter.PARSE_MODE,
                )
    except TelegramAPIError:
        logger.warning(
            "Failed to publish variant to channel",
            extra={"user_id": telegram_id, "operation": "publish_to_channel"},
        )
        await callback.message.answer(get_string("publish_failed", language))
        await safe_answer(callback)
        return

    if pending_media is not None:
        # Single-slot attachment is one-shot: media_attached_confirmation
        # tells the user it applies to "the next channel publish" only, so a
        # successful publish must consume it — otherwise an old photo would
        # silently keep attaching itself to every unrelated post afterward.
        clear_pending_media(db_path, telegram_id)

    await callback.message.answer(get_string("publish_success", language))
    await safe_answer(callback)


def _render_package(package: platform_package.PlatformPackage, language: str) -> str:
    """Собирает сообщение по одному пакету.

    Текст для копирования уходит в <pre>: Telegram рисует у таких блоков
    кнопку копирования, то есть «скопировал и вставил в приложение площадки»
    занимает одно касание. Расплата — моноширинный шрифт в превью; это
    осознанный размен внешнего вида на то, ради чего пакет и делается.
    """
    lines = [f"<b>{output_formatter.format_variant(package.display_name)}</b>", ""]

    if package.title:
        lines.append(get_string("package_title_label", language))
        lines.append(f"<pre>{output_formatter.format_variant(package.title)}</pre>")
        lines.append(get_string("package_body_label", language))

    body = package.caption
    if package.hashtags:
        body = f"{body}\n\n{' '.join(package.hashtags)}".strip()
    if body:
        lines.append(f"<pre>{output_formatter.format_variant(body)}</pre>")

    lines.append("")
    lines.append(get_string(package.media_spec.key, language, **package.media_spec.params))
    for note in package.notes:
        lines.append(get_string(note.key, language, **note.params))

    return "\n".join(lines)


@router.callback_query(F.data.startswith("refine:package:"))
async def on_refine_package(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    """Отдаёт пост, разложенный под Instagram, YouTube Shorts и Facebook.

    Никакой доставки: бот не публикует, не хранит токены площадок и не ходит
    к их API — обоснование в docstring bot/services/platform_package.py и в
    socseti.md. Поэтому здесь нет ни check_limit_or_reply (платного вызова
    не происходит), ни обращения к bot: всё уходит ответом в личку.
    """
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    # Тот же приём, что и в on_refine_publish выше: кнопка висит под одним
    # конкретным показанным вариантом, и его текст — это текст сообщения,
    # под которым она стоит.
    post_text = callback.message.text or ""

    await callback.message.answer(get_string("package_intro", language))
    for package in platform_package.build_all_packages(post_text):
        await callback.message.answer(
            _render_package(package, language),
            parse_mode=output_formatter.PARSE_MODE,
        )

    await safe_answer(callback)


@router.callback_query(F.data.startswith("refine:image:"))
async def on_refine_image(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if not await check_limit_or_reply(callback, db_path, language):
        return

    if not await ensure_image_budget(callback.message.answer, db_path, telegram_id, language):
        await safe_answer(callback)
        return

    # WHY read the text off callback.message rather than FSM data: same
    # reasoning as on_refine_publish above — the image button sits under one
    # already-generated variant message specifically, and that message's
    # text is the exact post this image should illustrate.
    post_text = callback.message.text or ""

    try:
        image_prompt = await content_generator.generate_image_prompt(post_text)
        image_bytes = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during image generation",
            extra={"user_id": telegram_id, "operation": "generate_image", "error_class": type(exc).__name__},
        )
        await callback.message.answer(get_string(error_key, language))
        await safe_answer(callback)
        return

    try:
        sent_message = await bot.send_photo(
            callback.message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image.png"),
            caption=get_string("image_preview_caption", language),
            reply_markup=build_image_upgrade_keyboard(language),
        )
    except TelegramAPIError:
        logger.warning(
            "Failed to deliver generated image to user",
            extra={"user_id": telegram_id, "operation": "generate_image"},
        )
        await callback.message.answer(get_string("image_delivery_failed", language))
        await safe_answer(callback)
        return

    increment_usage(db_path, telegram_id)
    increment_image_usage(db_path, telegram_id)
    image_model = load_settings().ai_gateway_image_model
    record_cost(
        db_path, telegram_id, "generate_image", image_model, cost_tracker.image_cost(image_model)
    )

    # WHY store Telegram's own file_id instead of re-sending the raw bytes:
    # the AI Gateway only hands back the image once, as base64 in memory —
    # once Telegram has ingested it into a sent message, its own file_id is
    # a durable reference we can reuse (e.g. for a later channel publish)
    # without holding onto or re-decoding the original bytes.
    file_id = sent_message.photo[-1].file_id
    set_pending_media(db_path, telegram_id, file_id, "photo")

    # WHY key by (chat, message) in the database instead of one shared FSM
    # slot: a user can generate several images in a row before tapping
    # "upgrade" on an older one — a single shared slot would silently
    # upgrade the wrong photo's prompt (and charge for it). Storing only
    # after send_photo succeeds also means a failed cheap generation never
    # overwrites a still-valid prompt from an earlier photo. Same rationale
    # and pattern as bot/storage/refine_context.py.
    save_image_prompt(db_path, callback.message.chat.id, sent_message.message_id, image_prompt)

    await callback.message.answer(get_string("image_attached_confirmation", language))
    await safe_answer(callback)


@router.callback_query(F.data == CALLBACK_IMAGE_UPGRADE)
async def on_image_upgrade(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if not await check_limit_or_reply(callback, db_path, language):
        return

    # Checked before claim_image_prompt: claiming deletes the stored prompt,
    # and a refusal must leave this photo upgradeable tomorrow rather than
    # silently consuming its one-shot prompt.
    if not await ensure_image_budget(callback.message.answer, db_path, telegram_id, language):
        await safe_answer(callback)
        return

    image_prompt = claim_image_prompt(db_path, callback.message.chat.id, callback.message.message_id)
    if not image_prompt:
        await callback.message.answer(get_string("error_refine_missing_context", language))
        await safe_answer(callback)
        return

    # WHY disable the button before calling the (slow, billed) AI Gateway
    # rather than only after: aiogram runs callback handlers as concurrent
    # tasks, so a second tap during a 10-60s premium generation would
    # otherwise fire a second, independent charge before the first call
    # ever gets to disable anything. This shrinks the double-charge window
    # down to one Telegram API round-trip. Best-effort — a failure here
    # must not block the upgrade itself.
    try:
        await callback.message.edit_reply_markup(reply_markup=build_image_upgraded_keyboard(language))
    except TelegramAPIError as exc:
        logger.warning(
            "Failed to optimistically disable image-upgrade button (likely stale)",
            extra={"error_message": str(exc)},
        )

    settings = load_settings()

    try:
        image_bytes = await ai_gateway.generate_image(
            image_prompt, model=settings.ai_gateway_premium_image_model
        )
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during image upgrade",
            extra={
                "user_id": telegram_id,
                "operation": "generate_image_upgrade",
                "error_class": type(exc).__name__,
            },
        )
        await callback.message.answer(get_string(error_key, language))
        save_image_prompt(db_path, callback.message.chat.id, callback.message.message_id, image_prompt)
        await _restore_upgrade_button(callback, language)
        await safe_answer(callback)
        return

    try:
        sent_message = await bot.send_photo(
            callback.message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image_upgraded.png"),
            caption=get_string("image_upgraded_caption", language),
        )
    except TelegramAPIError:
        logger.warning(
            "Failed to deliver upgraded image to user",
            extra={"user_id": telegram_id, "operation": "generate_image_upgrade"},
        )
        await callback.message.answer(get_string("image_delivery_failed", language))
        save_image_prompt(db_path, callback.message.chat.id, callback.message.message_id, image_prompt)
        await _restore_upgrade_button(callback, language)
        await safe_answer(callback)
        return

    increment_usage(db_path, telegram_id)
    increment_image_usage(db_path, telegram_id)
    premium_model = settings.ai_gateway_premium_image_model
    record_cost(
        db_path,
        telegram_id,
        "generate_image_upgrade",
        premium_model,
        cost_tracker.image_cost(premium_model),
    )

    file_id = sent_message.photo[-1].file_id
    set_pending_media(db_path, telegram_id, file_id, "photo")

    await safe_answer(callback)


async def _restore_upgrade_button(callback: CallbackQuery, language: str) -> None:
    # WHY restore rather than leave it disabled: the button was disabled
    # optimistically before the AI Gateway call — an error here means
    # either no charge went through (AIGatewayError) or a charge happened
    # but nothing was delivered (delivery failure); either way the user
    # must be able to tap again to retry, e.g. after topping up balance.
    try:
        await callback.message.edit_reply_markup(reply_markup=build_image_upgrade_keyboard(language))
    except TelegramAPIError as exc:
        logger.warning(
            "Failed to restore image-upgrade button after error (likely stale)",
            extra={"error_message": str(exc)},
        )


@router.callback_query(F.data == CALLBACK_IMAGE_UPGRADE_DONE)
async def on_image_upgrade_done(callback: CallbackQuery) -> None:
    # The "✅ Готово" button left behind after a successful upgrade is
    # inert by design (see design doc) — this only stops the client-side
    # loading spinner if someone taps it anyway.
    await safe_answer(callback)
