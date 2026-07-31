from __future__ import annotations

import logging

from aiogram.types import Message

from bot.keyboards.style import build_style_ready_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayError
from bot.storage.style_examples import get_style_examples
from bot.storage.style_profile import get_style_profile, set_style_profile

logger = logging.getLogger(LOGGER_NAME)

# Below this many stored style examples the bot refuses to write: fewer
# samples do not carry a recognisable voice, they just bias the model toward
# whichever single post it saw.
REQUIRED_EXAMPLES = 5


async def read_style_if_ready(
    message: Message,
    db_path: str,
    telegram_id: int,
    language: str,
    has_source_text: bool,
) -> bool:
    """Analyse the stored samples once there are enough of them, and reply.

    Shared by the two places that collect samples — /settov and the authored
    post flow. Returns True when it has answered the user, so the caller knows
    to skip its own progress message.

    Never touches the quota: reading a style is a one-off setup step, not a
    piece of delivered content, and charging for it would strand the user with
    a configured voice and no posts left for the day.
    """
    examples = get_style_examples(db_path, telegram_id)
    if len(examples) < REQUIRED_EXAMPLES:
        return False

    keyboard = build_style_ready_keyboard(language, has_source_text)
    enough_message = get_string(
        "authorpost_samples_enough",
        language,
        count=len(examples),
        required=REQUIRED_EXAMPLES,
    )

    # Already read for this set of samples. Extra samples are still stored and
    # still quoted into the prompt, but re-analysing on each one would spend an
    # AI call per message on a profile that barely moves.
    if get_style_profile(db_path, telegram_id) is not None:
        await message.answer(enough_message, reply_markup=keyboard)
        return True

    try:
        summary = await content_generator.analyze_style(examples, language)
    except AIGatewayError as exc:
        logger.warning(
            "AI Gateway error during style analysis",
            extra={
                "user_id": telegram_id,
                "operation": "analyze_style",
                "error_class": type(exc).__name__,
            },
        )
        # No profile stored, so the next sample retries the analysis. The user
        # keeps the same buttons either way — a failed read must not cost them
        # the flow they were in the middle of.
        await message.answer(enough_message, reply_markup=keyboard)
        return True

    set_style_profile(db_path, telegram_id, summary)
    logger.info(
        "Style profile read",
        extra={
            "user_id": telegram_id,
            "operation": "analyze_style",
            "example_count": len(examples),
        },
    )
    await message.answer(
        get_string("style_read_summary", language, summary=summary),
        reply_markup=keyboard,
    )
    return True
