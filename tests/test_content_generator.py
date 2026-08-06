from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.services import ai_gateway, content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError


def test_build_prompt_contains_platform_language_and_source_text():
    prompt = content_generator.build_prompt("Исходный текст статьи", "telegram", "ru")

    assert "telegram" in prompt.lower()
    assert "ru" in prompt
    assert "Исходный текст статьи" in prompt


def test_build_prompt_for_vk_mentions_vk_platform():
    prompt = content_generator.build_prompt("Исходный текст статьи", "vk", "en")

    assert "vk" in prompt.lower()
    assert "en" in prompt


def test_build_prompt_differs_between_platforms():
    telegram_prompt = content_generator.build_prompt("текст", "telegram", "ru")
    vk_prompt = content_generator.build_prompt("текст", "vk", "ru")

    assert telegram_prompt != vk_prompt


@pytest.mark.asyncio
async def test_generate_variants_calls_generate_text_requested_count(monkeypatch):
    mock_generate = AsyncMock(side_effect=["Вариант 1", "Вариант 2", "Вариант 3"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    variants = await content_generator.generate_variants("текст", "telegram", "ru", count=3)

    assert mock_generate.await_count == 3
    assert variants == ["Вариант 1", "Вариант 2", "Вариант 3"]


@pytest.mark.asyncio
async def test_generate_variants_uses_default_count_of_three(monkeypatch):
    mock_generate = AsyncMock(side_effect=["А", "Б", "В"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    variants = await content_generator.generate_variants("текст", "vk", "ru")

    assert mock_generate.await_count == 3
    assert len(variants) == 3


@pytest.mark.asyncio
async def test_generate_variants_passes_built_prompt_to_generate_text(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants("исходник", "telegram", "ru", count=1)

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt("исходник", "telegram", "ru")


@pytest.mark.asyncio
async def test_generate_variants_passes_temperature_for_diversity(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants("текст", "telegram", "ru", count=3)

    assert mock_generate.await_count == 3
    for call in mock_generate.await_args_list:
        assert call.kwargs["temperature"] == content_generator._VARIANT_TEMPERATURE


def test_build_prompt_without_extra_instruction_is_unchanged_from_default():
    prompt = content_generator.build_prompt("текст", "telegram", "ru")

    assert prompt == content_generator.build_prompt("текст", "telegram", "ru", extra_instruction=None)


def test_build_prompt_includes_extra_instruction_when_given():
    prompt = content_generator.build_prompt(
        "текст", "telegram", "ru", extra_instruction="Make it shorter."
    )

    assert "Make it shorter." in prompt


@pytest.mark.asyncio
async def test_generate_variants_passes_extra_instruction_into_prompt(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants(
        "исходник", "telegram", "ru", count=1, extra_instruction=content_generator.SHORTEN_INSTRUCTION
    )

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt(
        "исходник", "telegram", "ru", extra_instruction=content_generator.SHORTEN_INSTRUCTION
    )
    assert content_generator.SHORTEN_INSTRUCTION in called_prompt


@pytest.mark.asyncio
async def test_generate_variants_without_extra_instruction_matches_default_prompt(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants("исходник", "telegram", "ru", count=1)

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt("исходник", "telegram", "ru")


def test_build_prompt_without_style_examples_is_unchanged_from_default():
    prompt = content_generator.build_prompt("текст", "telegram", "ru")

    assert prompt == content_generator.build_prompt(
        "текст", "telegram", "ru", extra_instruction=None, style_examples=None
    )
    assert prompt == content_generator.build_prompt(
        "текст", "telegram", "ru", extra_instruction=None, style_examples=[]
    )


def test_build_prompt_includes_style_examples_when_given():
    prompt = content_generator.build_prompt(
        "текст",
        "telegram",
        "ru",
        style_examples=["Мой старый пост номер один.", "А вот и второй пример."],
    )

    assert "Мой старый пост номер один." in prompt
    assert "А вот и второй пример." in prompt


def test_build_prompt_style_examples_do_not_affect_prompt_when_empty():
    prompt = content_generator.build_prompt("текст", "telegram", "ru", style_examples=[])

    assert prompt == content_generator.build_prompt("текст", "telegram", "ru")


@pytest.mark.asyncio
async def test_generate_variants_passes_style_examples_into_prompt(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    style_examples = ["Пример моего стиля."]
    await content_generator.generate_variants(
        "исходник", "telegram", "ru", count=1, style_examples=style_examples
    )

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt(
        "исходник", "telegram", "ru", style_examples=style_examples
    )
    assert "Пример моего стиля." in called_prompt


@pytest.mark.asyncio
async def test_generate_variants_without_style_examples_matches_default_prompt(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants("исходник", "telegram", "ru", count=1)

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt("исходник", "telegram", "ru")


@pytest.mark.asyncio
async def test_generate_variants_propagates_ai_gateway_error(monkeypatch):
    mock_generate = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    with pytest.raises(AIGatewayTimeoutError):
        await content_generator.generate_variants("текст", "telegram", "ru", count=2)


@pytest.mark.asyncio
async def test_generate_image_prompt_calls_generate_text_with_post_text(monkeypatch):
    mock_generate = AsyncMock(return_value="a vivid english description")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    result = await content_generator.generate_image_prompt("Пост про кофе")

    mock_generate.assert_awaited_once()
    called_prompt = mock_generate.await_args.args[0]
    assert "Пост про кофе" in called_prompt
    assert result == "a vivid english description"


@pytest.mark.asyncio
async def test_generate_image_prompt_strips_whitespace_from_result(monkeypatch):
    mock_generate = AsyncMock(return_value="  a vivid description  \n")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    result = await content_generator.generate_image_prompt("текст поста")

    assert result == "a vivid description"


@pytest.mark.asyncio
async def test_generate_image_prompt_propagates_ai_gateway_error(monkeypatch):
    mock_generate = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    with pytest.raises(AIGatewayTimeoutError):
        await content_generator.generate_image_prompt("текст поста")


def test_build_prompt_includes_hashtag_instruction_when_requested():
    prompt = content_generator.build_prompt("текст", "telegram", "ru", with_hashtags=True)

    assert content_generator._HASHTAG_INSTRUCTION in prompt


def test_build_prompt_without_hashtags_is_unchanged_from_default():
    prompt = content_generator.build_prompt("текст", "telegram", "ru")

    assert prompt == content_generator.build_prompt(
        "текст", "telegram", "ru", with_hashtags=False
    )
    assert content_generator._HASHTAG_INSTRUCTION not in prompt


def test_build_prompt_combines_hashtags_with_style_examples():
    prompt = content_generator.build_prompt(
        "текст",
        "telegram",
        "ru",
        style_examples=["Мой старый пост."],
        with_hashtags=True,
    )

    assert content_generator._HASHTAG_INSTRUCTION in prompt
    assert "Мой старый пост." in prompt


@pytest.mark.asyncio
async def test_generate_variants_passes_hashtag_flag_into_prompt(monkeypatch):
    mock_generate = AsyncMock(return_value="вариант")
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    await content_generator.generate_variants(
        "исходник", "telegram", "ru", count=1, with_hashtags=True
    )

    called_prompt = mock_generate.await_args.args[0]
    assert called_prompt == content_generator.build_prompt(
        "исходник", "telegram", "ru", with_hashtags=True
    )
    assert content_generator._HASHTAG_INSTRUCTION in called_prompt


def test_style_analysis_prompt_contains_every_example_and_the_language():
    prompt = content_generator.build_style_analysis_prompt(
        ["Первый пост", "Второй пост"], "ru"
    )

    assert "Первый пост" in prompt
    assert "Второй пост" in prompt
    assert "ru" in prompt


@pytest.mark.asyncio
async def test_analyze_style_strips_the_model_answer(monkeypatch):
    mock = AsyncMock(return_value="  • короткие абзацы\n• на «ты»  \n")
    monkeypatch.setattr(content_generator.ai_gateway, "generate_text", mock)

    result = await content_generator.analyze_style(["Пост"], "ru")

    assert result == "• короткие абзацы\n• на «ты»"
    mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_style_sends_the_analysis_prompt(monkeypatch):
    mock = AsyncMock(return_value="• тон")
    monkeypatch.setattr(content_generator.ai_gateway, "generate_text", mock)

    await content_generator.analyze_style(["Пост про ИИ"], "en")

    sent_prompt = mock.await_args.args[0]
    assert "Пост про ИИ" in sent_prompt
    assert sent_prompt == content_generator.build_style_analysis_prompt(
        ["Пост про ИИ"], "en"
    )


def test_prompt_includes_the_style_profile_when_given():
    prompt = content_generator.build_prompt(
        "Исходник",
        "telegram",
        "ru",
        style_profile="• короткие абзацы\n• на «ты»",
    )

    assert "• короткие абзацы" in prompt


def test_prompt_includes_both_profile_and_examples():
    prompt = content_generator.build_prompt(
        "Исходник",
        "telegram",
        "ru",
        style_examples=["Мой старый пост"],
        style_profile="• ирония",
    )

    assert "• ирония" in prompt
    assert "Мой старый пост" in prompt


def test_prompt_without_profile_or_examples_has_no_style_section():
    prompt = content_generator.build_prompt("Исходник", "telegram", "ru")

    assert "author's own voice" not in prompt
    assert "Match the writing voice" not in prompt


@pytest.mark.asyncio
async def test_generate_variants_forwards_the_style_profile(monkeypatch):
    mock = AsyncMock(return_value="вариант")
    monkeypatch.setattr(content_generator.ai_gateway, "generate_text", mock)

    await content_generator.generate_variants(
        "Исходник", "telegram", "ru", count=1, style_profile="• ирония"
    )

    assert "• ирония" in mock.await_args.args[0]


def test_telegram_prompt_asks_for_a_few_emoji_with_an_upper_bound():
    """Владелец попросила эмодзи «чуть побольше, плюс один-два, не перебарщивая».

    Просьба именно про меру: без верхней границы модели охотно засыпают
    короткий пост эмодзи, и текст перестаёт читаться. Поэтому в промпте
    названо и число, и запрет перебора.
    """
    prompt = content_generator.build_prompt(
        source_text="исходный текст",
        platform="telegram",
        content_language="ru",
    )

    assert "three or four" in prompt
    assert "do not overdo" in prompt.lower()


def test_telegram_platform_instruction_no_longer_states_a_length():
    """Regression: the platform instruction used to say "a few sentences"

    (~200-400 chars), which contradicted the per-user length budget line
    stated elsewhere in the same prompt (see post_length.build_budget_
    instruction) and made the "Развёрнутый" preset indistinguishable from
    "Средний". Length must come from the budget line alone.
    """
    prompt = content_generator.build_prompt(
        source_text="исходный текст",
        platform="telegram",
        content_language="ru",
    )

    assert "a few sentences" not in prompt


from bot.services import post_length


def test_build_prompt_includes_the_budget_when_a_preset_is_given():
    prompt = content_generator.build_prompt("текст", "telegram", "ru", length_preset="short")

    assert str(post_length.get_preset("short").target_chars) in prompt


def test_build_prompt_without_a_preset_is_unchanged_from_default():
    prompt = content_generator.build_prompt("текст", "telegram", "ru")

    assert prompt == content_generator.build_prompt(
        "текст", "telegram", "ru", length_preset=None
    )


def test_build_prompt_budget_differs_between_presets():
    short_prompt = content_generator.build_prompt(
        "текст", "telegram", "ru", length_preset="short"
    )
    expanded_prompt = content_generator.build_prompt(
        "текст", "telegram", "ru", length_preset="expanded"
    )

    assert short_prompt != expanded_prompt


@pytest.mark.asyncio
async def test_generate_variants_does_not_retry_when_the_variant_fits(monkeypatch):
    mock = AsyncMock(return_value="Короткий пост. Заходите!")
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    await content_generator.generate_variants(
        "текст", "telegram", "ru", count=2, length_preset="short"
    )

    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_generate_variants_retries_once_when_the_variant_is_too_long(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, "Коротко. Жми!"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    assert mock.await_count == 2
    assert variants == ["Коротко. Жми!"]


@pytest.mark.asyncio
async def test_generate_variants_retry_prompt_asks_for_a_smaller_number(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, "Коротко. Жми!"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    retry_prompt = mock.await_args_list[1].args[0]
    assert str(post_length.get_preset("short").retry_target_chars) in retry_prompt
    # Regression: build_prompt used to be called with the same length_preset
    # for the retry prompt, so the normal budget line's target_chars ended up
    # stated as a second, looser "hard limit" right alongside the retry's
    # smaller number.
    assert str(post_length.get_preset("short").target_chars) not in retry_prompt


@pytest.mark.asyncio
async def test_generate_variants_trims_when_the_retry_is_also_too_long(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, too_long])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    assert mock.await_count == 2
    assert post_length.measure(variants[0]) <= post_length.get_preset("short").max_units


@pytest.mark.asyncio
async def test_generate_variants_returns_a_trimmed_first_attempt_when_the_retry_fails(
    monkeypatch,
):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=[too_long, AIGatewayTimeoutError("timed out")])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=1, length_preset="short"
    )

    assert post_length.measure(variants[0]) <= post_length.get_preset("short").max_units


@pytest.mark.asyncio
async def test_generate_variants_retries_only_the_variant_that_overshot(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(side_effect=["Коротко. Жми!", too_long, "Тоже коротко. Жми!"])
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants(
        "текст", "telegram", "ru", count=2, length_preset="short"
    )

    assert mock.await_count == 3
    assert variants == ["Коротко. Жми!", "Тоже коротко. Жми!"]


@pytest.mark.asyncio
async def test_generate_variants_without_a_preset_never_retries(monkeypatch):
    too_long = "Слишком длинно. " * 60
    mock = AsyncMock(return_value=too_long)
    monkeypatch.setattr(ai_gateway, "generate_text", mock)

    variants = await content_generator.generate_variants("текст", "vk", "ru", count=2)

    assert mock.await_count == 2
    assert variants == [too_long, too_long]
