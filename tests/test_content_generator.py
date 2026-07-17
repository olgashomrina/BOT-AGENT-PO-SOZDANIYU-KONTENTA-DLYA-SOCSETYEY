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


@pytest.mark.asyncio
async def test_generate_variants_propagates_ai_gateway_error(monkeypatch):
    mock_generate = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    with pytest.raises(AIGatewayTimeoutError):
        await content_generator.generate_variants("текст", "telegram", "ru", count=2)
