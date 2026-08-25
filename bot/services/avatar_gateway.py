"""Говорящее видео из картинки и звука.

Один интерфейс на все движки: запустить рендер, потом опрашивать. Асинхронно,
потому что рендер занимает минуты (на пяти секундах замерено 213–520 с), и
держать ради него HTTP-соединение нельзя.

Про бота этот модуль не знает ничего: на вход байты, на выход байты. Смена
движка — правка `AVATAR_MODEL` в `.env`; разная форма входа у разных движков
живёт в `_build_inputs` и больше нигде.

Тело запроса не проверено живым вызовом провайдера — оно получено разбором
ошибок валидации 06.08. Перед первым живым прогоном его нужно сверить с
рабочим скриптом `/root/avatar_live_test.py` на сервере 159.194.214.72.
"""

from __future__ import annotations

import base64
import binascii
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

PROVIDER_NAME = "runware"

_TIMEOUT_SECONDS = 120.0

# Полный словарь статусов провайдера нам не известен. Слово, которого нет ни
# в одном из двух множеств ниже, намеренно считается "ещё работает": принять
# незнакомое "в процессе" за отказ и выбросить уже оплаченный рендер — ошибка
# дороже, чем один лишний цикл опроса.
_FAILURE_STATUSES = frozenset(
    {"error", "failed", "cancelled", "canceled", "expired", "rejected"}
)
_SUCCESS_STATUSES = frozenset({"success", "completed", "done"})


class AvatarGatewayError(Exception):
    """Базовый класс всех отказов шлюза говорящего видео."""


class AvatarGatewayUnavailableError(AvatarGatewayError):
    pass


class AvatarGatewayInvalidResponseError(AvatarGatewayError):
    pass


@dataclass(frozen=True)
class RenderStatus:
    done: bool
    failed: bool
    video_bytes: bytes | None
    cost_usd: float | None
    error: str | None


def _data_uri(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode()


def _build_inputs(model: str, image: str, audio: str) -> dict[str, Any]:
    """Форма входа под конкретный движок.

    Получена разбором ошибок валидации 06.08 (docs/reference-video-avatar-
    engines.md). У PixVerse поля лежат на верхнем уровне задачи, у остальных —
    внутри `inputs`, и это единственное, что мешает шлюзу быть тоньше.
    """
    if model.startswith("pixverse:"):
        return {"referenceImages": [image], "inputAudios": [audio]}
    return {"inputs": {"image": image, "audio": audio}}


async def _post(payload: list[dict[str, Any]], operation: str) -> dict[str, Any]:
    settings = load_settings()
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS,
        headers={"Authorization": f"Bearer {settings.runware_api_key}"},
    ) as client:
        try:
            response = await client.post(settings.runware_base_url, json=payload)
        except httpx.HTTPError as exc:
            logger.error(
                "Avatar gateway transport failure: operation=%s error=%s",
                operation,
                exc,
                exc_info=True,
            )
            raise AvatarGatewayUnavailableError(
                "Не удалось связаться с сервисом видео"
            ) from exc

    if response.status_code >= 400:
        logger.error(
            "Avatar gateway call failed: operation=%s provider=%s status=%s",
            operation,
            PROVIDER_NAME,
            response.status_code,
        )
        raise AvatarGatewayUnavailableError(
            f"Сервис видео вернул ошибку {response.status_code}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AvatarGatewayInvalidResponseError(
            "Не удалось разобрать ответ сервиса видео"
        ) from exc

    if not isinstance(body, dict):
        raise AvatarGatewayInvalidResponseError(
            "Ответ сервиса видео не прошёл базовую валидацию"
        )
    return body


def _provider_error(body: dict[str, Any]) -> str | None:
    """Текст отказа, который Runware кладёт в `errors` при HTTP 200."""
    errors = body.get("errors")
    if not errors:
        return None
    first = errors[0]
    return str(first.get("message", first)) if isinstance(first, dict) else str(first)


def _first_task(body: dict[str, Any]) -> dict[str, Any]:
    try:
        task = body["data"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise AvatarGatewayInvalidResponseError(
            "Ответ сервиса видео не содержит задачи"
        ) from exc
    if not isinstance(task, dict):
        raise AvatarGatewayInvalidResponseError(
            "Ответ сервиса видео не прошёл базовую валидацию"
        )
    return task


async def start_render(image_bytes: bytes, audio_bytes: bytes) -> str:
    operation = "start_render"
    settings = load_settings()
    model = settings.avatar_model
    task_uuid = str(uuid.uuid4())

    task: dict[str, Any] = {
        "taskType": "videoInference",
        # Runware требует UUIDv4 и сверяет по нему ответ с запросом; своего
        # он не придумывает и любую другую строку отвергает.
        "taskUUID": task_uuid,
        "model": model,
        # Рендер идёт минутами — синхронного ответа тут не существует.
        "deliveryMethod": "async",
        # Фактическая цена приходит в ответе; по прайсу считать нельзя,
        # у одной модели документация разошлась с фактом в 7,4 раза.
        "includeCost": True,
    }
    task.update(
        _build_inputs(
            model,
            _data_uri(image_bytes, "image/jpeg"),
            _data_uri(audio_bytes, "audio/mpeg"),
        )
    )

    body = await _post([task], operation)
    error = _provider_error(body)
    if error:
        raise AvatarGatewayInvalidResponseError(f"Сервис видео отказал: {error}")

    returned = _first_task(body).get("taskUUID") or task_uuid
    logger.info(
        "Avatar render started: provider=%s model=%s operation=%s",
        PROVIDER_NAME,
        model,
        operation,
    )
    return str(returned)


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise AvatarGatewayUnavailableError(
                "Не удалось скачать готовое видео"
            ) from exc
    if response.status_code >= 400:
        raise AvatarGatewayUnavailableError(
            f"Скачивание видео вернуло ошибку {response.status_code}"
        )
    return response.content


async def poll_render(task_uuid: str) -> RenderStatus:
    operation = "poll_render"
    body = await _post(
        [{"taskType": "getResponse", "taskUUID": task_uuid}], operation
    )

    error = _provider_error(body)
    if error:
        return RenderStatus(
            done=False, failed=True, video_bytes=None, cost_usd=None, error=error
        )

    task = _first_task(body)
    status = str(task.get("status", "")).lower()
    if status in _FAILURE_STATUSES:
        return RenderStatus(
            done=False,
            failed=True,
            video_bytes=None,
            cost_usd=None,
            error=str(task.get("error") or "рендер не удался"),
        )

    encoded = task.get("videoBase64Data")
    url = task.get("videoURL")
    if not encoded and not url:
        if status in _SUCCESS_STATUSES:
            # Провайдер отчитался об успехе, но видео не приложил — это уже
            # не "ещё работает", а отказ, просто без слова "error".
            return RenderStatus(
                done=False,
                failed=True,
                video_bytes=None,
                cost_usd=None,
                error="Сервис видео сообщил об успехе, но не вернул видео",
            )
        return RenderStatus(
            done=False, failed=False, video_bytes=None, cost_usd=None, error=None
        )

    # Наружу — всегда байты. То, что провайдер иногда отвечает ссылкой,
    # а иногда телом, остаётся его личным делом.
    if encoded:
        try:
            # Без validate=True: провайдеры оборачивают base64 переводами
            # строк в HTTP-теле, а строгий режим считает перенос строки
            # непечатным мусором и валит уже оплаченный рендер на ровном
            # месте. Обычный b64decode переносы строк спокойно пропускает
            # и всё равно ловит настоящий брак — не кратную 4 длину,
            # нехватку паддинга — тем же binascii.Error.
            video_bytes = base64.b64decode(encoded)
        except binascii.Error as exc:
            # Битый base64 — уже не сеть и не HTTP-статус, а сам провайдер
            # прислал мусор вместо оплаченного видео. Наружу обещаны только
            # подклассы AvatarGatewayError; голый binascii.Error пролетел бы
            # мимо всех обработчиков вызывающего.
            raise AvatarGatewayInvalidResponseError(
                "Не удалось разобрать видео из ответа сервиса"
            ) from exc
    else:
        video_bytes = await _download(str(url))
    cost = task.get("cost")
    try:
        cost_usd = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        # Числовые поля провайдера ненадёжны (документированная цена одной
        # модели разошлась с фактом в 7,4 раза) — нечитаемый cost не должен
        # стоить уже оплаченного и успешно скачанного рендера.
        logger.warning(
            "Avatar gateway got an unparseable cost: provider=%s operation=%s cost=%r",
            PROVIDER_NAME,
            operation,
            cost,
        )
        cost_usd = None
    logger.info(
        "Avatar render ready: provider=%s operation=%s", PROVIDER_NAME, operation
    )
    return RenderStatus(
        done=True,
        failed=False,
        video_bytes=video_bytes,
        cost_usd=cost_usd,
        error=None,
    )
