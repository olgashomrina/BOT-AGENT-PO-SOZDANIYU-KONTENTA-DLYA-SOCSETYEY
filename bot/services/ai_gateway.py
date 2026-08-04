from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, NoReturn

import httpx

from bot.config import Settings, load_settings
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

RATE_LIMIT_FALLBACK_SECONDS = 5.0

SleepFn = Callable[[float], Awaitable[None]]

# Module-level indirection so tests can replace the sleep implementation and
# avoid real waits during retry-backoff tests.
_sleep: SleepFn = asyncio.sleep


class AIGatewayError(Exception):
    """Base class for all AI Gateway failures."""


class AIGatewayTimeoutError(AIGatewayError):
    pass


class AIGatewayRateLimitError(AIGatewayError):
    pass


class AIGatewayUnavailableError(AIGatewayError):
    pass


class AIGatewayInvalidResponseError(AIGatewayError):
    pass


class AIGatewayOutOfBudgetError(AIGatewayError):
    """The proxy refused the call because the account balance is too low.

    vsegpt.ru answers this with HTTP 400 and a message like "Potentially out
    of budget: 32->700, expected price 0.05664, but you have only 0.017680 on
    account" — confirmed against production on 2026-07-31. Without its own
    class it lands in AIGatewayInvalidResponseError and the user is told the
    AI answered incorrectly, which sent us hunting for a bug in the bot for a
    day while the real cause was an empty account (see dengi.md).
    """


class TranscriptionError(AIGatewayError):
    pass


@dataclass
class _CallResult:
    response: httpx.Response
    retry_count: int


def _fields(
    operation: str,
    provider: str,
    model: str,
    duration_ms: float,
    retry_count: int,
    error_class: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "provider": provider,
        "model": model,
        "duration_ms": round(duration_ms, 1),
        "retry_count": retry_count,
        "error_class": error_class,
        "error_message": error_message,
    }


def _info(operation: str, provider: str, model: str, duration_ms: float, retry_count: int) -> None:
    logger.info(
        "AI Gateway call succeeded: operation=%s provider=%s model=%s duration_ms=%.1f retry_count=%d",
        operation,
        provider,
        model,
        duration_ms,
        retry_count,
        extra=_fields(operation, provider, model, duration_ms, retry_count),
    )


def _warn(
    operation: str,
    provider: str,
    model: str,
    duration_ms: float,
    retry_count: int,
    error_class: str,
    error_message: str,
) -> None:
    logger.warning(
        "AI Gateway retryable failure: operation=%s error_class=%s error_message=%s "
        "provider=%s model=%s duration_ms=%.1f retry_count=%d",
        operation,
        error_class,
        error_message,
        provider,
        model,
        duration_ms,
        retry_count,
        extra=_fields(operation, provider, model, duration_ms, retry_count, error_class, error_message),
    )


def _fail(
    exc: AIGatewayError,
    *,
    operation: str,
    provider: str,
    model: str,
    duration_ms: float,
    retry_count: int,
) -> NoReturn:
    # Re-raise/catch locally so `exc_info=True` has a real traceback to log,
    # even for failures (e.g. HTTP status codes) that never went through a
    # Python exception before this point.
    try:
        raise exc
    except AIGatewayError:
        logger.error(
            "AI Gateway call failed: operation=%s error_class=%s error_message=%s "
            "provider=%s model=%s duration_ms=%.1f retry_count=%d",
            operation,
            type(exc).__name__,
            str(exc),
            provider,
            model,
            duration_ms,
            retry_count,
            extra=_fields(operation, provider, model, duration_ms, retry_count, type(exc).__name__, str(exc)),
            exc_info=True,
        )
        raise


def _response_snippet(response: httpx.Response, limit: int = 300) -> str:
    # Best-effort diagnostic text for logs only (never shown to end users —
    # see bot/locales/*.py error_* keys for the user-facing taxonomy
    # messages). The provider's error body is what actually explains 4xx
    # failures (e.g. billing/subscription issues), which a bare status code
    # doesn't.
    try:
        text = response.text
    except Exception:
        return "<не удалось прочитать тело ответа>"
    text = text.strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text or "<пустое тело ответа>"


# Substrings that mark a 4xx as "your account is out of money" rather than
# "your request was malformed". Matched case-insensitively against the
# provider's error body. The first two are what vsegpt.ru actually sends
# (confirmed live, 2026-07-31); the rest are cheap insurance against wording
# changes and against a different proxy being configured.
_OUT_OF_BUDGET_MARKERS = (
    "out of budget",
    "add some money",
    "insufficient",
    "недостаточно средств",
    "пополните баланс",
)


def _is_out_of_budget(response: httpx.Response) -> bool:
    # 402 Payment Required means exactly this and nothing else — it is how
    # openrouter.ai reports an empty account, and it needs no body sniffing.
    # vsegpt.ru instead answers 400 with the reason in the body, hence the
    # marker list.
    if response.status_code == 402:
        return True
    try:
        text = response.text
    except Exception:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _OUT_OF_BUDGET_MARKERS)


def _retry_after_seconds(response: httpx.Response) -> float:
    header = response.headers.get("Retry-After")
    if header is None:
        return RATE_LIMIT_FALLBACK_SECONDS
    try:
        return float(header)
    except ValueError:
        return RATE_LIMIT_FALLBACK_SECONDS


async def _call_with_retries(
    *,
    request: Callable[[], Awaitable[httpx.Response]],
    operation: str,
    provider: str,
    model: str,
    max_retries: int,
    sleep: SleepFn,
) -> _CallResult:
    retry_count = 0
    while True:
        attempt_started = time.monotonic()
        try:
            response = await request()
        except httpx.TimeoutException as exc:
            duration_ms = (time.monotonic() - attempt_started) * 1000
            if retry_count < max_retries:
                _warn(operation, provider, model, duration_ms, retry_count, type(exc).__name__, str(exc))
                await sleep(2**retry_count)
                retry_count += 1
                continue
            mapped: AIGatewayError = AIGatewayTimeoutError("Тайм-аут при обращении к AI-прокси")
            mapped.__cause__ = exc
            _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)
        except httpx.HTTPError as exc:
            duration_ms = (time.monotonic() - attempt_started) * 1000
            if retry_count < max_retries:
                _warn(operation, provider, model, duration_ms, retry_count, type(exc).__name__, str(exc))
                await sleep(2**retry_count)
                retry_count += 1
                continue
            mapped = AIGatewayUnavailableError("Не удалось связаться с AI-прокси")
            mapped.__cause__ = exc
            _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)
        else:
            duration_ms = (time.monotonic() - attempt_started) * 1000

            if response.status_code == 429:
                if retry_count < 1:
                    delay = _retry_after_seconds(response)
                    _warn(operation, provider, model, duration_ms, retry_count, "AIGatewayRateLimitError", "HTTP 429")
                    await sleep(delay)
                    retry_count += 1
                    continue
                _fail(
                    AIGatewayRateLimitError("Провайдер AI-прокси вернул 429 (rate limit)"),
                    operation=operation,
                    provider=provider,
                    model=model,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                )

            if response.status_code >= 500:
                if retry_count < max_retries:
                    _warn(
                        operation,
                        provider,
                        model,
                        duration_ms,
                        retry_count,
                        "AIGatewayUnavailableError",
                        f"HTTP {response.status_code}",
                    )
                    await sleep(2**retry_count)
                    retry_count += 1
                    continue
                _fail(
                    AIGatewayUnavailableError(f"AI-прокси вернул ошибку {response.status_code}"),
                    operation=operation,
                    provider=provider,
                    model=model,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                )

            if response.status_code >= 400:
                # Checked before the generic 4xx branch: an empty balance is a
                # money problem the owner can fix, not a malformed request, and
                # the two need different messages to the user and different
                # reactions from us.
                if _is_out_of_budget(response):
                    _fail(
                        AIGatewayOutOfBudgetError(
                            "На балансе AI-прокси не хватает средств: "
                            f"{_response_snippet(response)}"
                        ),
                        operation=operation,
                        provider=provider,
                        model=model,
                        duration_ms=duration_ms,
                        retry_count=retry_count,
                    )
                _fail(
                    AIGatewayInvalidResponseError(
                        f"AI-прокси вернул ошибку {response.status_code}: {_response_snippet(response)}"
                    ),
                    operation=operation,
                    provider=provider,
                    model=model,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                )

            _info(operation, provider, model, duration_ms, retry_count)
            return _CallResult(response=response, retry_count=retry_count)


def _parse_text_response(
    response: httpx.Response,
    operation: str,
    provider: str,
    model: str,
    retry_count: int,
    duration_ms: float,
) -> str:
    try:
        payload = response.json()
    except ValueError as exc:
        mapped: AIGatewayError = AIGatewayInvalidResponseError("Не удалось разобрать ответ ИИ-модели")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        mapped = AIGatewayInvalidResponseError("Ответ ИИ-модели не прошёл базовую валидацию")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    if not content or not content.strip():
        _fail(
            AIGatewayInvalidResponseError("Получен пустой ответ от ИИ-модели"),
            operation=operation,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )

    return content


def _parse_transcription_response(
    response: httpx.Response,
    operation: str,
    provider: str,
    model: str,
    retry_count: int,
    duration_ms: float,
) -> str:
    try:
        payload = response.json()
    except ValueError as exc:
        mapped: AIGatewayError = TranscriptionError("Не удалось разобрать ответ сервиса транскрипции")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    text = payload.get("text") if isinstance(payload, dict) else None
    if not text or not text.strip():
        _fail(
            TranscriptionError("Получен пустой результат транскрипции"),
            operation=operation,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )

    return text


def _parse_image_response(
    response: httpx.Response,
    operation: str,
    provider: str,
    model: str,
    retry_count: int,
    duration_ms: float,
) -> bytes:
    try:
        payload = response.json()
    except ValueError as exc:
        mapped: AIGatewayError = AIGatewayInvalidResponseError("Не удалось разобрать ответ сервиса генерации изображений")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    try:
        b64_data = payload["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError) as exc:
        mapped = AIGatewayInvalidResponseError("Ответ сервиса генерации изображений не прошёл базовую валидацию")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    if not b64_data or not b64_data.strip():
        _fail(
            AIGatewayInvalidResponseError("Получено пустое изображение от ИИ-модели"),
            operation=operation,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )

    try:
        return base64.b64decode(b64_data)
    except (binascii.Error, ValueError) as exc:
        mapped = AIGatewayInvalidResponseError("Не удалось декодировать изображение от ИИ-модели")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)


def _text_endpoint(settings: Settings) -> tuple[str, str, str, str]:
    """Куда идти за текстом: адрес, ключ, имя провайдера и модель по умолчанию.

    Провайдер выбирается на операцию: тексты и картинки могут жить у Runware,
    а распознавание речи обязано остаться у vsegpt, потому что у Runware его
    нет вовсе. Текстовый эндпоинт Runware openai-совместим, поэтому меняются
    только эти четыре значения — тело запроса и разбор ответа общие.
    """
    if settings.text_provider.lower() == RUNWARE_PROVIDER:
        return (
            settings.runware_base_url,
            settings.runware_api_key,
            RUNWARE_PROVIDER,
            settings.runware_text_model,
        )
    return (
        settings.ai_proxy_base_url,
        settings.ai_proxy_api_key,
        settings.ai_gateway_provider,
        settings.ai_gateway_text_model,
    )


async def generate_text(prompt: str, model: str | None = None, temperature: float | None = None) -> str:
    settings = load_settings()
    base_url, api_key, provider, default_model = _text_endpoint(settings)
    resolved_model = model or default_model
    operation = "generate_text"
    overall_started = time.monotonic()

    async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        return await client.post("/chat/completions", json=payload)

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=settings.ai_gateway_timeout_seconds,
        headers={"Authorization": f"Bearer {api_key}"},
    ) as client:
        result = await _call_with_retries(
            request=lambda: _do_request(client),
            operation=operation,
            provider=provider,
            model=resolved_model,
            max_retries=settings.ai_gateway_max_retries,
            sleep=_sleep,
        )

    duration_ms = (time.monotonic() - overall_started) * 1000
    return _parse_text_response(
        result.response, operation, provider, resolved_model, result.retry_count, duration_ms
    )


# Container signatures, longest-prefix first where they could overlap. Only
# formats Telegram can actually deliver are listed; anything else falls back
# to OGG, which is what a `voice` message always is.
_AUDIO_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"OggS", "telegram-voice.ogg", "audio/ogg"),
    (b"RIFF", "telegram-voice.wav", "audio/wav"),
    (b"fLaC", "telegram-voice.flac", "audio/flac"),
    (b"ID3", "telegram-voice.mp3", "audio/mpeg"),
    (b"\xff\xfb", "telegram-voice.mp3", "audio/mpeg"),
    (b"\xff\xf3", "telegram-voice.mp3", "audio/mpeg"),
    (b"\x1a\x45\xdf\xa3", "telegram-voice.webm", "audio/webm"),
)
_DEFAULT_AUDIO_PART = ("telegram-voice.ogg", "audio/ogg")


def _audio_part_metadata(audio_bytes: bytes) -> tuple[str, str]:
    """Filename and MIME type for the multipart audio part, from the bytes.

    Transcription hosts pick their decoder from this metadata rather than by
    sniffing the payload, so a wrong label is not cosmetic: openrouter.ai
    answers a mislabelled part with a bare `Provider returned 400`.

    This used to be hardcoded to OGG because a Telegram `voice` message
    always is one — but `handle_voice` also accepts `message.audio`, which is
    any file the user sent: mp3, m4a, wav. Those were being labelled as OGG.
    """
    for signature, filename, media_type in _AUDIO_SIGNATURES:
        if audio_bytes.startswith(signature):
            return filename, media_type
    # MP4/M4A keeps its marker at offset 4, after the box length.
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        return "telegram-voice.m4a", "audio/mp4"
    return _DEFAULT_AUDIO_PART


async def transcribe(audio_bytes: bytes, language_hint: str | None = None) -> str:
    settings = load_settings()
    resolved_model = settings.ai_gateway_transcription_model
    operation = "transcribe"
    overall_started = time.monotonic()

    async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
        data: dict[str, str] = {"model": resolved_model, "response_format": "json"}
        if language_hint:
            data["language"] = language_hint
        filename, media_type = _audio_part_metadata(audio_bytes)
        files = {"file": (filename, audio_bytes, media_type)}
        return await client.post("/audio/transcriptions", data=data, files=files)

    async with httpx.AsyncClient(
        base_url=settings.ai_proxy_base_url,
        timeout=settings.ai_gateway_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.ai_proxy_api_key}"},
    ) as client:
        result = await _call_with_retries(
            request=lambda: _do_request(client),
            operation=operation,
            provider=settings.ai_gateway_provider,
            model=resolved_model,
            max_retries=settings.ai_gateway_max_retries,
            sleep=_sleep,
        )

    duration_ms = (time.monotonic() - overall_started) * 1000
    return _parse_transcription_response(
        result.response, operation, settings.ai_gateway_provider, resolved_model, result.retry_count, duration_ms
    )


RUNWARE_PROVIDER = "runware"


def _runware_dimensions(size: str) -> tuple[int, int]:
    """`"1024x1024"` → `(1024, 1024)`.

    Runware принимает ширину и высоту числами, а не строкой размера, как
    openai-совместимые модели. Разбор терпимый: при неразборчивом значении
    берём квадрат 1024, потому что уронить генерацию из-за настройки размера
    хуже, чем нарисовать картинку не того размера.
    """
    try:
        width, height = (int(part) for part in size.lower().split("x", 1))
    except (ValueError, AttributeError):
        return 1024, 1024
    return width, height


def _parse_runware_image_response(
    response: httpx.Response,
    operation: str,
    provider: str,
    model: str,
    retry_count: int,
    duration_ms: float,
) -> bytes:
    """Картинка из ответа Runware.

    Формат другой, чем у openai-совместимых шлюзов: ответ — объект с массивом
    `data` по одной записи на задачу, картинка лежит в `imageBase64Data`.
    Ошибки Runware кладёт в отдельный массив `errors` и отвечает при этом
    двумя сотнями, поэтому одного HTTP-кода мало — надо смотреть тело.
    """
    try:
        payload = response.json()
    except ValueError as exc:
        mapped: AIGatewayError = AIGatewayInvalidResponseError(
            "Не удалось разобрать ответ сервиса генерации изображений"
        )
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        message = str(errors[0].get("message", "")) if isinstance(errors[0], dict) else str(errors[0])
        _fail(
            AIGatewayInvalidResponseError(f"Сервис генерации изображений вернул ошибку: {message}"),
            operation=operation,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )

    try:
        b64_data = payload["data"][0]["imageBase64Data"]
    except (KeyError, IndexError, TypeError) as exc:
        mapped = AIGatewayInvalidResponseError("Ответ сервиса генерации изображений не прошёл базовую валидацию")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)

    if not b64_data or not b64_data.strip():
        _fail(
            AIGatewayInvalidResponseError("Получено пустое изображение от ИИ-модели"),
            operation=operation,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=retry_count,
        )

    try:
        return base64.b64decode(b64_data)
    except (binascii.Error, ValueError) as exc:
        mapped = AIGatewayInvalidResponseError("Не удалось декодировать изображение от ИИ-модели")
        mapped.__cause__ = exc
        _fail(mapped, operation=operation, provider=provider, model=model, duration_ms=duration_ms, retry_count=retry_count)


def _runware_model(requested: str | None, settings: Settings) -> str:
    """Модель Runware по тому, что попросил вызывающий код.

    Хендлеры просят модель словами того провайдера, который был настроен, —
    например `bot/handlers/refine.py` передаёт слаг vsegpt из
    `AI_GATEWAY_PREMIUM_IMAGE_MODEL`. Отправить такую строку в Runware значит
    сломать кнопку «Сделать реалистичнее», поэтому чужие слаги не передаются
    дальше, а переводятся: премиальный — в премиальный, любой другой — в
    модель по умолчанию. Свои идентификаторы Runware (вида `runware:100@1`)
    проходят как есть.
    """
    if not requested:
        return settings.runware_image_model
    if requested == settings.ai_gateway_premium_image_model:
        return settings.runware_premium_image_model
    if "@" in requested:
        return requested
    return settings.runware_image_model


async def _generate_image_runware(prompt: str, model: str | None, size: str | None) -> bytes:
    settings = load_settings()
    resolved_model = _runware_model(model, settings)
    width, height = _runware_dimensions(size or settings.ai_gateway_image_size)
    operation = "generate_image"
    overall_started = time.monotonic()

    async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
        payload = [
            {
                "taskType": "imageInference",
                # Runware требует UUIDv4 и сверяет по нему ответ с запросом;
                # своего он не придумывает и отвергает любую другую строку.
                "taskUUID": str(uuid.uuid4()),
                "positivePrompt": prompt,
                "width": width,
                "height": height,
                "model": resolved_model,
                "numberResults": 1,
                # base64Data, а не URL: бот возвращает байты, и лишний поход
                # за картинкой по ссылке — это ещё одна точка отказа.
                "outputType": "base64Data",
            }
        ]
        # Полный адрес, а не base_url плюс путь: у Runware все задачи идут в
        # один-единственный эндпоинт, а httpx при пустом пути дописал бы к
        # адресу косую черту.
        return await client.post(settings.runware_base_url, json=payload)

    async with httpx.AsyncClient(
        timeout=settings.ai_gateway_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.runware_api_key}"},
    ) as client:
        result = await _call_with_retries(
            request=lambda: _do_request(client),
            operation=operation,
            provider=RUNWARE_PROVIDER,
            model=resolved_model,
            max_retries=settings.ai_gateway_max_retries,
            sleep=_sleep,
        )

    duration_ms = (time.monotonic() - overall_started) * 1000
    return _parse_runware_image_response(
        result.response, operation, RUNWARE_PROVIDER, resolved_model, result.retry_count, duration_ms
    )


async def generate_image(prompt: str, model: str | None = None, size: str | None = None) -> bytes:
    settings = load_settings()
    if settings.image_provider.lower() == RUNWARE_PROVIDER:
        return await _generate_image_runware(prompt, model, size)
    resolved_model = model or settings.ai_gateway_image_model
    resolved_size = size or settings.ai_gateway_image_size
    operation = "generate_image"
    overall_started = time.monotonic()

    async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "n": 1,
            "size": resolved_size,
            # vsegpt.ru's Flux models reject requests without this — they
            # only support returning the image inline as base64, not as a
            # hosted URL (confirmed live: "Only response_format = b64_json
            # is not supported" when this was omitted). Standard OpenAI-style
            # image models accept this param too, so it's safe if the
            # configured model changes later.
            "response_format": "b64_json",
        }
        return await client.post("/images/generations", json=payload)

    async with httpx.AsyncClient(
        base_url=settings.ai_proxy_base_url,
        timeout=settings.ai_gateway_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.ai_proxy_api_key}"},
    ) as client:
        result = await _call_with_retries(
            request=lambda: _do_request(client),
            operation=operation,
            provider=settings.ai_gateway_provider,
            model=resolved_model,
            max_retries=settings.ai_gateway_max_retries,
            sleep=_sleep,
        )

    duration_ms = (time.monotonic() - overall_started) * 1000
    return _parse_image_response(
        result.response, operation, settings.ai_gateway_provider, resolved_model, result.retry_count, duration_ms
    )


# openrouter.ai keeps the remaining balance in a different place, under a
# different endpoint, in a different currency — so it gets an explicit reader
# rather than the tolerant walk below.
OPENROUTER_PROVIDER = "openrouter"
_OPENROUTER_BALANCE_PATH = "/credits"
_DEFAULT_BALANCE_PATH = "/balance"


def _extract_openrouter_balance(payload: Any) -> float | None:
    """Remaining credits from openrouter.ai's `GET /credits`, in dollars.

    Confirmed against a live account on 2026-07-31:

        {"data": {"total_credits": 20, "total_usage": 1.2842976}}

    Both numbers are lifetime totals, so the remaining balance is their
    difference. This must not go through `_extract_balance`: that walk would
    return `total_credits` — everything ever topped up — and the low-balance
    warning would then never fire.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    try:
        return float(data["total_credits"]) - float(data["total_usage"])
    except (KeyError, TypeError, ValueError):
        return None


def _extract_balance(payload: Any) -> float | None:
    """Find the account balance anywhere in a `GET /balance` payload.

    Confirmed against production on 2026-07-31, vsegpt.ru answers:

        {"status": "ok", "data": {"credits": "0.017680",
         "subscription_status": "ok", "subscription_end": "...", ...}}

    — note the balance is nested and arrives as a *string*. The walk stays
    tolerant rather than reading `data.credits` directly: the shape is
    undocumented, so it can change without notice, and this also survives
    `{"balance": 12.3}` and similar variants. Returns None when nothing
    plausible is found, and the caller logs the raw body.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if any(token in key.lower() for token in ("balance", "credit", "amount")):
                    return float(value)
            if isinstance(value, str) and any(
                token in key.lower() for token in ("balance", "credit", "amount")
            ):
                try:
                    return float(value)
                except ValueError:
                    continue
        for value in payload.values():
            found = _extract_balance(value)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_balance(item)
            if found is not None:
                return found
    return None


async def get_balance() -> float:
    """Remaining account balance at the AI proxy, **in rubles**.

    Rubles regardless of provider: openrouter.ai bills in dollars, and the
    whole point of this number is to compare it against a budget the owner
    thinks about in rubles (`BALANCE_ALERT_THRESHOLD_RUB`, and the "this buys
    N more pictures" estimates). The conversion uses `USD_RUB_RATE`, which is
    a rough constant rather than a live rate — good enough for a warning
    threshold, and never used to bill anyone.

    Raises AIGatewayError (the same hierarchy as every other call here) when
    the proxy is unreachable or answers in an unrecognisable shape.
    """
    settings = load_settings()
    operation = "get_balance"
    # Not a model call; the log fields still want the field filled in.
    model = "-"
    is_openrouter = settings.ai_gateway_provider.lower() == OPENROUTER_PROVIDER
    path = _OPENROUTER_BALANCE_PATH if is_openrouter else _DEFAULT_BALANCE_PATH
    overall_started = time.monotonic()

    async with httpx.AsyncClient(
        base_url=settings.ai_proxy_base_url,
        timeout=settings.ai_gateway_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.ai_proxy_api_key}"},
    ) as client:
        result = await _call_with_retries(
            request=lambda: client.get(path),
            operation=operation,
            provider=settings.ai_gateway_provider,
            model=model,
            max_retries=settings.ai_gateway_max_retries,
            sleep=_sleep,
        )

    duration_ms = (time.monotonic() - overall_started) * 1000

    try:
        payload = result.response.json()
    except ValueError as exc:
        mapped: AIGatewayError = AIGatewayInvalidResponseError(
            "Не удалось разобрать ответ о балансе AI-прокси"
        )
        mapped.__cause__ = exc
        _fail(
            mapped,
            operation=operation,
            provider=settings.ai_gateway_provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=result.retry_count,
        )

    balance = (
        _extract_openrouter_balance(payload) if is_openrouter else _extract_balance(payload)
    )
    if balance is None:
        _fail(
            AIGatewayInvalidResponseError(
                "В ответе о балансе AI-прокси не найдено числовое значение: "
                f"{_response_snippet(result.response)}"
            ),
            operation=operation,
            provider=settings.ai_gateway_provider,
            model=model,
            duration_ms=duration_ms,
            retry_count=result.retry_count,
        )

    if is_openrouter:
        balance *= settings.usd_rub_rate

    _info(operation, settings.ai_gateway_provider, model, duration_ms, result.retry_count)
    return balance
