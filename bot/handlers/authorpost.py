from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language, send_variants
from bot.handlers.guards import (
    check_limit_or_reply,
    check_whitelist_or_reply,
    safe_answer,
)
from bot.handlers.settov import MAX_EXAMPLE_LENGTH
from bot.handlers.style_reading import REQUIRED_EXAMPLES, read_style_if_ready
from bot.keyboards.authorpost import (
    CALLBACK_ITEM_PREFIX,
    CALLBACK_NEW_SAMPLES,
    CALLBACK_NEXT,
    CALLBACK_PLATFORM_PREFIX,
    CALLBACK_SAMPLES_DONE,
    CALLBACK_START,
    CALLBACK_USE_SAVED,
    build_item_choice_keyboard,
    build_next_step_keyboard,
    build_platform_keyboard,
    build_saved_examples_keyboard,
)
from bot.keyboards.style import CALLBACK_OWN_TOPIC
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayError
from bot.storage.limits import increment_usage
from bot.storage.style_examples import (
    KIND_WRITTEN,
    add_style_example,
    clear_style_examples,
    get_style_examples,
)
from bot.storage.style_profile import clear_style_profile, get_style_profile
from bot.storage.users import get_content_language, get_post_length

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="authorpost")


class AuthorPostStates(StatesGroup):
    # Only one state, and only for the sample-collection step, which is the
    # one place this flow has to intercept ordinary text messages. Every
    # other step is a callback_query with unique callback_data. A state left
    # set outside this step would be actively harmful: route_content in
    # bot/handlers/content.py filters on StateFilter(None), so the bot would
    # stop reacting to normal messages entirely.
    collecting_examples = State()


async def _report_expired_digest(callback: CallbackQuery, language: str) -> None:
    # Reached when FSM data has no digest items — most often because the bot
    # process restarted (storage is in-memory MemoryStorage, see
    # bot/main.py), but also when a button from a previous digest is tapped
    # after a newer, shorter digest replaced the list.
    await callback.message.answer(get_string("authorpost_digest_expired", language))
    await safe_answer(callback)


@router.callback_query(F.data == CALLBACK_START)
async def on_authorpost_start(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    data = await state.get_data()
    items = data.get("digest_items") or []
    if not items:
        await _report_expired_digest(callback, language)
        return

    # Defaults to 1 rather than 0 to match the generation bot/handlers/start.py
    # stamps on the very first digest a fresh FSM has never seen before.
    generation = data.get("digest_generation", 1)
    await callback.message.answer(
        get_string("authorpost_choose_item", language),
        reply_markup=build_item_choice_keyboard(len(items), generation),
    )
    await safe_answer(callback)


@router.callback_query(F.data.startswith(f"{CALLBACK_ITEM_PREFIX}:"))
async def on_authorpost_item(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    data = await state.get_data()
    items = data.get("digest_items") or []
    current_generation = data.get("digest_generation", 1)
    # callback.data is client-supplied: a modified client can send any string
    # matching the startswith filter above, not just the generation:index
    # pairs this bot's own keyboard emitted. So both numbers are parsed
    # defensively and checked here, rather than trusted to match the keyboard
    # the bot sent — a non-integer would otherwise raise past safe_answer and
    # leave the button's spinner hanging, and a negative index would otherwise
    # silently select the last item via Python's negative indexing instead of
    # the one the user actually asked for.
    try:
        _, generation_str, index_str = callback.data.rsplit(":", 2)
        generation = int(generation_str)
        index = int(index_str)
    except ValueError:
        await _report_expired_digest(callback, language)
        return
    # A generation mismatch means this button belongs to a digest that has
    # since been replaced by a newer one in FSM data: the item list at
    # `index` now refers to a different topic's items, not the one the user
    # tapped on. Treating it as "expired" (same message as an empty list)
    # rather than silently indexing into the current list is the whole point
    # of the fix — see bot/handlers/start.py for where the generation is
    # stamped and incremented.
    if generation != current_generation or not 0 <= index < len(items):
        await _report_expired_digest(callback, language)
        return

    item = items[index]
    # source_text is the same FSM key bot/handlers/refine.py reads, so the
    # "Ещё / Короче" buttons under the generated variants work with no extra
    # wiring on this side.
    await state.update_data(source_text=item)
    logger.info(
        "Authored post source selected",
        extra={"user_id": telegram_id, "operation": "handler:authorpost", "item_index": index},
    )

    await callback.message.answer(
        get_string("authorpost_item_chosen", language, item=item),
        reply_markup=build_next_step_keyboard(language),
    )
    await safe_answer(callback)


async def _ask_for_samples(callback: CallbackQuery, state: FSMContext, language: str) -> None:
    await state.set_state(AuthorPostStates.collecting_examples)
    await callback.message.answer(
        get_string("authorpost_samples_prompt", language, required=REQUIRED_EXAMPLES)
    )
    await safe_answer(callback)


async def _ask_for_platform(callback: CallbackQuery, language: str) -> None:
    await callback.message.answer(
        get_string("authorpost_choose_platform", language),
        reply_markup=build_platform_keyboard(language),
    )
    await safe_answer(callback)


def _stored_example_count(db_path: str, telegram_id: int) -> int:
    return len(get_style_examples(db_path, telegram_id))


@router.callback_query(F.data == CALLBACK_NEXT)
async def on_authorpost_next(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    count = _stored_example_count(db_path, telegram_id)
    if count >= REQUIRED_EXAMPLES:
        await callback.message.answer(
            get_string("authorpost_saved_examples_intro", language, count=count),
            reply_markup=build_saved_examples_keyboard(language),
        )
        await safe_answer(callback)
        return

    await _ask_for_samples(callback, state, language)


@router.callback_query(F.data == CALLBACK_USE_SAVED)
async def on_authorpost_use_saved(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    await _ask_for_platform(callback, language)


@router.callback_query(F.data == CALLBACK_NEW_SAMPLES)
async def on_authorpost_new_samples(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    # Wipe rather than append: leaving the old examples in would blend two
    # eras of the user's writing under one cap, and "загрузить новые" would
    # quietly mean "загрузить ещё".
    #
    # Scoped to KIND_WRITTEN: this screen only ever collects written posts.
    # An unscoped wipe would also delete the spoken transcripts harvested from
    # the user's video-circle donors, silently destroying their double's
    # spoken-style library as a side effect of refreshing written samples.
    clear_style_examples(db_path, telegram_id, kind=KIND_WRITTEN)
    # The profile went with them: it describes posts the bot no longer has,
    # and leaving it would stop the new samples from ever being analysed.
    clear_style_profile(db_path, telegram_id)
    await callback.message.answer(get_string("authorpost_samples_cleared", language))
    await _ask_for_samples(callback, state, language)


@router.message(AuthorPostStates.collecting_examples)
async def on_authorpost_sample(message: Message, state: FSMContext, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    if not message.text:
        await message.answer(get_string("authorpost_sample_non_text", language))
        return

    if len(message.text) > MAX_EXAMPLE_LENGTH:
        await message.answer(get_string("authorpost_sample_too_long", language))
        return

    add_style_example(db_path, telegram_id, message.text)

    data = await state.get_data()
    if await read_style_if_ready(
        message, db_path, telegram_id, language, bool(data.get("source_text"))
    ):
        return

    # The counter reports everything in storage, not just this session's
    # messages: "не менее 5" means "the bot holds 5 samples of your voice",
    # so a user who already had 2 saved is done after 3 more.
    await message.answer(
        get_string(
            "authorpost_samples_progress",
            language,
            count=_stored_example_count(db_path, telegram_id),
            required=REQUIRED_EXAMPLES,
        )
    )


# No state filter on the decorator: the style-ready keyboard
# (bot/keyboards/style.py) is sent from /settov as well, whose state belongs
# to a different StatesGroup — a filtered handler would silently not fire there.
@router.callback_query(F.data == CALLBACK_SAMPLES_DONE)
async def on_authorpost_samples_done(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    # Back to None before anything else: while a state is set, route_content
    # (StateFilter(None)) never fires and the bot ignores ordinary messages.
    await state.set_state(None)
    await _ask_for_platform(callback, language)


@router.callback_query(F.data == CALLBACK_OWN_TOPIC)
async def on_authorpost_own_topic(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    # Same reason as above, and it matters more here: the very next thing the
    # user does is type their topic, and with a sample-collection state still
    # set that message would be filed as one more style sample.
    await state.set_state(None)
    await callback.message.answer(get_string("style_own_topic_prompt", language))
    await safe_answer(callback)


# callback_data suffix -> the platforms to generate for, in output order.
_PLATFORM_TARGETS: dict[str, tuple[str, ...]] = {
    "telegram": ("telegram",),
    "vk": ("vk",),
    "both": ("telegram", "vk"),
}


@router.callback_query(F.data.startswith(f"{CALLBACK_PLATFORM_PREFIX}:"))
async def on_authorpost_platform(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    source_text = data.get("source_text")
    if not source_text:
        await _report_expired_digest(callback, language)
        return

    if not await check_limit_or_reply(callback, db_path, language):
        return

    # callback.data is client-supplied, same reasoning as on_authorpost_item:
    # a modified client can send a suffix outside {"telegram", "vk", "both"},
    # the only values this bot's own keyboard emits. A raw dict lookup would
    # raise KeyError past safe_answer and leave the button's spinner
    # hanging, so an unrecognised suffix is treated the same as a stale
    # digest reference rather than trusted to match the keyboard sent.
    try:
        platforms = _PLATFORM_TARGETS[callback.data.rsplit(":", 1)[1]]
    except KeyError:
        await _report_expired_digest(callback, language)
        return

    content_language = data.get("content_language") or get_content_language(
        db_path, telegram_id
    ) or language
    settings = load_settings()
    style_examples = get_style_examples(db_path, telegram_id)
    style_profile = get_style_profile(db_path, telegram_id)

    # Only content_language is worth keeping in FSM: it is read back at the
    # top of this handler if the user runs the flow again.
    #
    # The hashtag setting deliberately does NOT go here. What keeps the
    # hashtags when the user taps "Ещё"/"Короче" is the per-message row that
    # send_variants writes (bot/storage/refine_context.py) — FSM data is per
    # chat, so an ordinary post generated afterwards would overwrite it and
    # strip the hashtags off a regeneration of one of these variants.
    await state.update_data(content_language=content_language)

    await callback.message.answer(get_string("authorpost_generating", language))

    generated: list[tuple[str, list[str]]] = []
    for platform in platforms:
        try:
            variants = await content_generator.generate_variants(
                source_text,
                platform,
                content_language,
                count=settings.content_variants_count,
                style_examples=style_examples,
                with_hashtags=True,
                style_profile=style_profile,
                # Бюджет — свойство Telegram-поста: у VK лимит на порядок
                # больше, и урезать там нечего.
                length_preset=(
                    get_post_length(db_path, telegram_id) if platform == "telegram" else None
                ),
            )
        except AIGatewayError as exc:
            error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
            logger.warning(
                "AI Gateway error during authored post generation",
                extra={
                    "user_id": telegram_id,
                    "operation": "authorpost_generate",
                    "error_class": type(exc).__name__,
                },
            )
            await callback.message.answer(get_string(error_key, language))
            await safe_answer(callback)
            return
        generated.append((platform, variants))

    # One usage unit per platform, charged only after every call succeeded:
    # a failed generation above returns early and costs the user nothing,
    # matching how bot/handlers/refine.py bills its own regenerations.
    for _ in platforms:
        increment_usage(db_path, telegram_id)

    for platform, variants in generated:
        # with_hashtags=True mirrors the generate_variants call above and the
        # FSM data recorded earlier: an authored post carries hashtags, and the
        # per-message refine context has to say so, or tapping "Ещё"/"Короче"
        # under one of these variants would regenerate it without them.
        await send_variants(
            callback.message,
            language,
            platform,
            variants,
            db_path,
            source_text,
            content_language,
            True,
        )

    await safe_answer(callback)
