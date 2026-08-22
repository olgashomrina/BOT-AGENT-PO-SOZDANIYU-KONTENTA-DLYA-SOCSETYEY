from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

PROVIDER_NAME = "elevenlabs"
# Одноязычные модели читают русский с акцентом. Мультиязычная — единственная,
# на которой клон звучит как оригинал.
SYNTHESIS_MODEL = "eleven_multilingual_v2"

_TIMEOUT_SECONDS = 120.0


class VoiceGatewayError(Exception):
    """Базовый класс всех отказов шлюза голоса."""


class VoiceGatewayUnavailableError(VoiceGatewayError):
    pass


class VoiceGatewayInvalidResponseError(VoiceGatewayError):
    pass


def _client() -> httpx.AsyncClient:
    settings = load_settings()
    if not settings.elevenlabs_api_key:
        raise VoiceGatewayError(
            "ELEVENLABS_API_KEY не задан — клонирование голоса недоступно"
        )
    return httpx.AsyncClient(
        base_url=settings.elevenlabs_base_url,
        timeout=_TIMEOUT_SECONDS,
        headers={"xi-api-key": settings.elevenlabs_api_key},
    )


def _check_status(response: httpx.Response, operation: str) -> None:
    if response.status_code >= 400:
        logger.error(
            "Voice gateway call failed: operation=%s provider=%s status=%s",
            operation,
            PROVIDER_NAME,
            response.status_code,
        )
        raise VoiceGatewayError(
            f"Провайдер голоса вернул ошибку {response.status_code}"
        )


async def clone_voice(audio_bytes: bytes, name: str) -> str:
    operation = "clone_voice"
    client = _client()
    async with client:
        try:
            response = await client.post(
                "/voices/add",
                data={"name": name},
                files={"files": ("voice.wav", audio_bytes, "audio/wav")},
            )
        except httpx.HTTPError as exc:
            logger.error(
                "Voice gateway transport failure: operation=%s error=%s",
                operation,
                exc,
                exc_info=True,
            )
            raise VoiceGatewayUnavailableError(
                "Не удалось связаться с провайдером голоса"
            ) from exc

    _check_status(response, operation)

    try:
        payload: Any = response.json()
        voice_id = payload["voice_id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise VoiceGatewayInvalidResponseError(
            "Ответ провайдера голоса не содержит идентификатора голоса"
        ) from exc

    if not voice_id:
        raise VoiceGatewayInvalidResponseError(
            "Провайдер вернул пустой идентификатор голоса"
        )

    logger.info("Voice cloned: provider=%s operation=%s", PROVIDER_NAME, operation)
    return str(voice_id)


async def delete_voice(voice_id: str) -> None:
    operation = "delete_voice"
    client = _client()
    async with client:
        try:
            response = await client.delete(f"/voices/{voice_id}")
        except httpx.HTTPError as exc:
            raise VoiceGatewayUnavailableError(
                "Не удалось связаться с провайдером голоса"
            ) from exc

    _check_status(response, operation)
    logger.info("Voice deleted: provider=%s operation=%s", PROVIDER_NAME, operation)


async def synthesize(text: str, voice_id: str) -> bytes:
    """Озвучка текста готовым клонированным голосом.

    Голос уже создан этапом 1 и живёт у провайдера под своим идентификатором —
    сюда он приходит параметром. Пересоздавать голос ради каждой речи не нужно
    и нельзя: это главное требование сценария.
    """
    operation = "synthesize"
    client = _client()
    async with client:
        try:
            response = await client.post(
                f"/text-to-speech/{voice_id}",
                json={"text": text, "model_id": SYNTHESIS_MODEL},
            )
        except httpx.HTTPError as exc:
            logger.error(
                "Voice gateway transport failure: operation=%s error=%s",
                operation,
                exc,
                exc_info=True,
            )
            raise VoiceGatewayUnavailableError(
                "Не удалось связаться с провайдером голоса"
            ) from exc

    _check_status(response, operation)

    audio = response.content
    if not audio:
        raise VoiceGatewayInvalidResponseError("Провайдер вернул пустую озвучку")

    logger.info(
        "Voice synthesized: provider=%s operation=%s", PROVIDER_NAME, operation
    )
    return audio
