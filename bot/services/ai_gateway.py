from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, NoReturn

import httpx

from bot.config import load_settings
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


async def generate_text(prompt: str, model: str | None = None, temperature: float | None = None) -> str:
    settings = load_settings()
    resolved_model = model or settings.ai_gateway_text_model
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
    return _parse_text_response(
        result.response, operation, settings.ai_gateway_provider, resolved_model, result.retry_count, duration_ms
    )


async def transcribe(audio_bytes: bytes, language_hint: str | None = None) -> str:
    settings = load_settings()
    resolved_model = settings.ai_gateway_transcription_model
    operation = "transcribe"
    overall_started = time.monotonic()

    async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
        data: dict[str, str] = {"model": resolved_model}
        if language_hint:
            data["language"] = language_hint
        files = {"file": ("audio.ogg", audio_bytes, "application/octet-stream")}
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
