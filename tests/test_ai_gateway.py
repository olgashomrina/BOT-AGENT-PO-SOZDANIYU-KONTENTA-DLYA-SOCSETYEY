from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from bot.services import ai_gateway
from bot.services.ai_gateway import (
    AIGatewayInvalidResponseError,
    AIGatewayRateLimitError,
    AIGatewayTimeoutError,
    AIGatewayUnavailableError,
    TranscriptionError,
    generate_text,
    transcribe,
)

REQUIRED_ENV = {
    "BOT_TOKEN": "123456:test-token",
    "AI_PROXY_API_KEY": "test-ai-key",
    "OWNER_CHAT_ID": "42",
}

BASE_URL = "https://fake-ai-proxy.test/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
TRANSCRIBE_URL = f"{BASE_URL}/audio/transcriptions"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_PROXY_BASE_URL", BASE_URL)
    monkeypatch.setenv("AI_GATEWAY_MAX_RETRIES", "2")
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "test-provider")
    monkeypatch.setenv("AI_GATEWAY_TEXT_MODEL", "test-text-model")
    monkeypatch.setenv("AI_GATEWAY_TRANSCRIPTION_MODEL", "test-transcription-model")


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ai_gateway, "_sleep", _fake_sleep)
    return sleeps


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


# --- generate_text: success / structural failures (no retry) ---


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_success():
    route = respx.post(CHAT_URL).mock(return_value=_chat_response("hello world"))

    result = await generate_text("write something")

    assert result == "hello world"
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_empty_response_raises_invalid_response_error():
    route = respx.post(CHAT_URL).mock(return_value=_chat_response(""))

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_text("write something")

    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_invalid_json_raises_invalid_response_error():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})
    )

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_text("write something")

    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_4xx_error_message_includes_response_body():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "You have no subscription"}})
    )

    with pytest.raises(AIGatewayInvalidResponseError) as exc_info:
        await generate_text("write something")

    assert "400" in str(exc_info.value)
    assert "You have no subscription" in str(exc_info.value)
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_uses_model_override():
    captured = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return _chat_response("ok")

    respx.post(CHAT_URL).mock(side_effect=_responder)

    await generate_text("prompt", model="custom-model")

    assert b"custom-model" in captured["body"]


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_includes_temperature_when_passed():
    captured = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _chat_response("ok")

    respx.post(CHAT_URL).mock(side_effect=_responder)

    await generate_text("prompt", temperature=0.9)

    assert captured["json"]["temperature"] == 0.9


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_omits_temperature_when_not_passed():
    captured = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _chat_response("ok")

    respx.post(CHAT_URL).mock(side_effect=_responder)

    await generate_text("prompt")

    assert "temperature" not in captured["json"]


# --- transcribe: success / structural failures (no retry) ---


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_success():
    route = respx.post(TRANSCRIBE_URL).mock(return_value=httpx.Response(200, json={"text": "hello"}))

    result = await transcribe(b"fake-audio-bytes")

    assert result == "hello"
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_empty_result_raises_transcription_error():
    route = respx.post(TRANSCRIBE_URL).mock(return_value=httpx.Response(200, json={"text": ""}))

    with pytest.raises(TranscriptionError):
        await transcribe(b"fake-audio-bytes")

    assert route.call_count == 1


# --- retry policy: timeout / connection error / 5xx / 429 ---


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_timeout_raises_after_retries_exhausted(_fast_sleep):
    route = respx.post(CHAT_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(AIGatewayTimeoutError):
        await generate_text("prompt")

    assert route.call_count == 3  # 1 initial attempt + 2 retries (AI_GATEWAY_MAX_RETRIES=2)
    assert _fast_sleep == [1, 2]


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_connection_error_raises_unavailable_after_retries(_fast_sleep):
    route = respx.post(CHAT_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(AIGatewayUnavailableError):
        await generate_text("prompt")

    assert route.call_count == 3
    assert _fast_sleep == [1, 2]


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_5xx_raises_unavailable_after_retries(_fast_sleep):
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(AIGatewayUnavailableError):
        await generate_text("prompt")

    assert route.call_count == 3
    assert _fast_sleep == [1, 2]


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_succeeds_after_transient_5xx():
    route = respx.post(CHAT_URL).mock(
        side_effect=[httpx.Response(500), _chat_response("recovered")]
    )

    result = await generate_text("prompt")

    assert result == "recovered"
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_rate_limit_retries_once_then_raises(_fast_sleep):
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429),
        ]
    )

    with pytest.raises(AIGatewayRateLimitError):
        await generate_text("prompt")

    assert route.call_count == 2
    assert _fast_sleep == [7.0]


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_rate_limit_fallback_delay_without_header(_fast_sleep):
    route = respx.post(CHAT_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(429)]
    )

    with pytest.raises(AIGatewayRateLimitError):
        await generate_text("prompt")

    assert route.call_count == 2
    assert _fast_sleep == [ai_gateway.RATE_LIMIT_FALLBACK_SECONDS]


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_rate_limit_recovers_after_one_retry():
    route = respx.post(CHAT_URL).mock(
        side_effect=[httpx.Response(429), _chat_response("ok now")]
    )

    result = await generate_text("prompt")

    assert result == "ok now"
    assert route.call_count == 2


# --- logging ---


@respx.mock
@pytest.mark.asyncio
async def test_logs_required_fields_on_final_failure(caplog):
    respx.post(CHAT_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    # Attach caplog's handler directly rather than relying on propagation to
    # the root logger: bot/logging_config.py's setup_logging() sets
    # propagate=False on the "bot" logger, and once any test in the suite
    # calls it for real (e.g. tests/test_logging_config.py), that setting
    # sticks for the rest of the process, breaking propagation-based capture.
    logger = logging.getLogger("bot")
    previous_propagate = logger.propagate
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="bot"):
            with pytest.raises(AIGatewayTimeoutError):
                await generate_text("prompt")
    finally:
        logger.removeHandler(caplog.handler)
        logger.propagate = previous_propagate

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]

    assert record.operation == "generate_text"
    assert record.error_class == "AIGatewayTimeoutError"
    assert record.error_message
    assert record.provider == "test-provider"
    assert record.model == "test-text-model"
    assert isinstance(record.duration_ms, float)
    assert record.retry_count == 2
    assert record.exc_info is not None

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 2
