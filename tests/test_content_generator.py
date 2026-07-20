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
