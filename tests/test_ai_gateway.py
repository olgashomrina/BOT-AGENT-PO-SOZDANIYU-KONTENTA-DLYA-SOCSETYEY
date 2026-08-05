from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest
import respx

from bot.services import ai_gateway
from bot.services.ai_gateway import (
    AIGatewayInvalidResponseError,
    AIGatewayOutOfBudgetError,
    AIGatewayRateLimitError,
    AIGatewayTimeoutError,
    AIGatewayUnavailableError,
    TranscriptionError,
    generate_image,
    generate_text,
    get_balance,
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
IMAGE_URL = f"{BASE_URL}/images/generations"
BALANCE_URL = f"{BASE_URL}/balance"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("AI_PROXY_BASE_URL", BASE_URL)
    monkeypatch.setenv("AI_GATEWAY_MAX_RETRIES", "2")
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "test-provider")
    monkeypatch.setenv("AI_GATEWAY_TEXT_MODEL", "test-text-model")
    monkeypatch.setenv("AI_GATEWAY_TRANSCRIPTION_MODEL", "test-transcription-model")
    monkeypatch.setenv("AI_GATEWAY_IMAGE_MODEL", "test-image-model")
    monkeypatch.setenv("AI_GATEWAY_IMAGE_SIZE", "512x512")


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ai_gateway, "_sleep", _fake_sleep)
    return sleeps


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _image_response(raw_bytes: bytes) -> httpx.Response:
    b64 = base64.b64encode(raw_bytes).decode()
    return httpx.Response(200, json={"data": [{"b64_json": b64}]})


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


# The exact body vsegpt.ru returns on an empty balance, captured from
# production on 2026-07-31.
_OUT_OF_BUDGET_BODY = {
    "error": {
        "message": (
            "Potentially out of budget: 32->700, expected price 0.05664, but "
            "you have only 0.017680 on account. Please, add some money to "
            "balance to proceed: https://vsegpt.ru/User/Money"
        ),
        "code": 400,
    }
}


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_out_of_budget_raises_its_own_error():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(400, json=_OUT_OF_BUDGET_BODY)
    )

    # Not AIGatewayInvalidResponseError: an empty balance is the owner's to
    # fix and must not read to the user as "the AI answered incorrectly".
    with pytest.raises(AIGatewayOutOfBudgetError) as exc_info:
        await generate_text("write something")

    assert "0.017680" in str(exc_info.value)
    # Retrying a call the account cannot pay for only burns time — the answer
    # will not change until money is added.
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_out_of_budget_raises_its_own_error():
    respx.post(TRANSCRIBE_URL).mock(return_value=httpx.Response(400, json=_OUT_OF_BUDGET_BODY))

    with pytest.raises(AIGatewayOutOfBudgetError):
        await transcribe(b"audio-bytes")


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_out_of_budget_raises_its_own_error():
    respx.post(IMAGE_URL).mock(return_value=httpx.Response(400, json=_OUT_OF_BUDGET_BODY))

    with pytest.raises(AIGatewayOutOfBudgetError):
        await generate_image("a cat")


@respx.mock
@pytest.mark.asyncio
async def test_http_402_is_out_of_budget_whatever_the_body_says():
    # openrouter.ai reports an empty account with 402 Payment Required rather
    # than with vsegpt.ru's 400-plus-explanation, so the status alone has to
    # be enough.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            402, json={"error": {"message": "This request requires more credits", "code": 402}}
        )
    )

    with pytest.raises(AIGatewayOutOfBudgetError):
        await generate_text("write something")


@respx.mock
@pytest.mark.asyncio
async def test_ordinary_4xx_is_still_an_invalid_response_error():
    # Guards the marker matching: a plain bad request must not be reported as
    # a money problem.
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "Unknown model"}})
    )

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_text("write something")


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
async def test_transcribe_sends_telegram_voice_as_ogg_opus_with_json_response():
    """VseGPT's STT host selects the decoder from the multipart file metadata."""
    captured: dict[str, bytes] = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return httpx.Response(200, json={"text": "hello"})

    respx.post(TRANSCRIBE_URL).mock(side_effect=_responder)

    await transcribe(b"fake-audio-bytes", language_hint="ru")

    assert b'filename="telegram-voice.ogg"' in captured["content"]
    assert b"Content-Type: audio/ogg" in captured["content"]
    assert b'name="response_format"' in captured["content"]
    assert b"json" in captured["content"]


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_empty_result_raises_transcription_error():
    route = respx.post(TRANSCRIBE_URL).mock(return_value=httpx.Response(200, json={"text": ""}))

    with pytest.raises(TranscriptionError):
        await transcribe(b"fake-audio-bytes")

    assert route.call_count == 1


# --- generate_image: success / structural failures (no retry) ---


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_success():
    route = respx.post(IMAGE_URL).mock(return_value=_image_response(b"fake-png-bytes"))

    result = await generate_image("a cat astronaut")

    assert result == b"fake-png-bytes"
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_empty_b64_json_raises_invalid_response_error():
    route = respx.post(IMAGE_URL).mock(return_value=httpx.Response(200, json={"data": [{"b64_json": ""}]}))

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_image("a cat astronaut")

    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_invalid_base64_raises_invalid_response_error():
    route = respx.post(IMAGE_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"b64_json": "not-valid-base64!!"}]})
    )

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_image("a cat astronaut")

    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_missing_data_raises_invalid_response_error():
    route = respx.post(IMAGE_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_image("a cat astronaut")

    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_invalid_json_raises_invalid_response_error():
    route = respx.post(IMAGE_URL).mock(
        return_value=httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})
    )

    with pytest.raises(AIGatewayInvalidResponseError):
        await generate_image("a cat astronaut")

    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_4xx_error_message_includes_response_body():
    route = respx.post(IMAGE_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "You have no subscription"}})
    )

    with pytest.raises(AIGatewayInvalidResponseError) as exc_info:
        await generate_image("a cat astronaut")

    assert "400" in str(exc_info.value)
    assert "You have no subscription" in str(exc_info.value)
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_uses_default_model_and_size_from_settings():
    captured = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _image_response(b"fake-png-bytes")

    respx.post(IMAGE_URL).mock(side_effect=_responder)

    await generate_image("a cat astronaut")

    assert captured["json"]["model"] == "test-image-model"
    assert captured["json"]["size"] == "512x512"
    assert captured["json"]["prompt"] == "a cat astronaut"
    assert captured["json"]["n"] == 1
    assert captured["json"]["response_format"] == "b64_json"


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_uses_model_and_size_override():
    captured = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _image_response(b"fake-png-bytes")

    respx.post(IMAGE_URL).mock(side_effect=_responder)

    await generate_image("a cat astronaut", model="custom-image-model", size="256x256")

    assert captured["json"]["model"] == "custom-image-model"
    assert captured["json"]["size"] == "256x256"


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_5xx_raises_unavailable_after_retries(_fast_sleep):
    route = respx.post(IMAGE_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(AIGatewayUnavailableError):
        await generate_image("a cat astronaut")

    assert route.call_count == 3
    assert _fast_sleep == [1, 2]


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_rate_limit_retries_once_then_raises(_fast_sleep):
    route = respx.post(IMAGE_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(429)]
    )

    with pytest.raises(AIGatewayRateLimitError):
        await generate_image("a cat astronaut")

    assert route.call_count == 2


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


# --- get_balance ---


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_reads_a_flat_balance_field():
    respx.get(BALANCE_URL).mock(return_value=httpx.Response(200, json={"balance": 123.45}))

    assert await get_balance() == pytest.approx(123.45)


# --- audio part metadata ---


@pytest.mark.parametrize(
    "payload, expected",
    [
        (b"OggS\x00\x02" + b"\x00" * 20, ("telegram-voice.ogg", "audio/ogg")),
        (b"RIFF\x24\x08\x00\x00WAVEfmt ", ("telegram-voice.wav", "audio/wav")),
        (b"fLaC\x00\x00\x00\x22", ("telegram-voice.flac", "audio/flac")),
        (b"ID3\x03\x00\x00\x00", ("telegram-voice.mp3", "audio/mpeg")),
        (b"\xff\xfb\x90\x00", ("telegram-voice.mp3", "audio/mpeg")),
        (b"\x00\x00\x00\x20ftypM4A ", ("telegram-voice.m4a", "audio/mp4")),
        (b"\x1a\x45\xdf\xa3\x01\x00", ("telegram-voice.webm", "audio/webm")),
    ],
)
def test_audio_part_metadata_identifies_the_container(payload, expected):
    assert ai_gateway._audio_part_metadata(payload) == expected


def test_audio_part_metadata_falls_back_to_ogg():
    # A Telegram `voice` message is always OGG, so that is the safe default
    # for anything unrecognised.
    assert ai_gateway._audio_part_metadata(b"\x00\x01\x02\x03") == (
        "telegram-voice.ogg",
        "audio/ogg",
    )


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_labels_the_part_with_the_real_container():
    # openrouter.ai picks its decoder from this metadata and answers a
    # mislabelled part with a bare "Provider returned 400" — so an mp3 sent
    # as message.audio must not go out labelled as OGG.
    route = respx.post(TRANSCRIBE_URL).mock(
        return_value=httpx.Response(200, json={"text": "ok"})
    )

    await transcribe(b"ID3\x03\x00\x00\x00 pretend mp3")

    body = route.calls[0].request.content
    assert b"telegram-voice.mp3" in body
    assert b"audio/mpeg" in body


CREDITS_URL = f"{BASE_URL}/credits"

# Captured from a live openrouter.ai account on 2026-07-31. Both numbers are
# lifetime totals; the remaining balance is their difference.
_OPENROUTER_CREDITS = {"data": {"total_credits": 20, "total_usage": 1.2842976}}


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_uses_the_credits_endpoint_for_openrouter(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "openrouter")
    monkeypatch.setenv("USD_RUB_RATE", "100")
    respx.get(CREDITS_URL).mock(return_value=httpx.Response(200, json=_OPENROUTER_CREDITS))

    # (20 - 1.2842976) dollars, reported in rubles because every budget in the
    # project is in rubles.
    assert await get_balance() == pytest.approx(1871.57024)


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_does_not_mistake_total_credits_for_the_remainder(monkeypatch):
    # The trap this exists for: a tolerant search for a "credits"-ish key
    # finds total_credits — everything ever topped up — and the low-balance
    # warning would then never fire. Spent almost everything here.
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "openrouter")
    monkeypatch.setenv("USD_RUB_RATE", "100")
    respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(
            200, json={"data": {"total_credits": 20, "total_usage": 19.9}}
        )
    )

    assert await get_balance() == pytest.approx(10.0)


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_raises_on_unrecognisable_openrouter_shape(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "openrouter")
    respx.get(CREDITS_URL).mock(return_value=httpx.Response(200, json={"data": {"nope": 1}}))

    with pytest.raises(AIGatewayInvalidResponseError):
        await get_balance()


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_reads_the_real_vsegpt_response():
    # Captured from production on 2026-07-31 — the shape this actually has to
    # work against: nested under "data", key named "credits", value a string.
    respx.get(BALANCE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "data": {
                    "credits": "0.017680",
                    "subscription_status": "ok",
                    "subscription_end": "2026-08-22 07:34:58",
                    "user_status": 2,
                    "user_status_text": "Less than 10 credits on account. ",
                },
            },
        )
    )

    assert await get_balance() == pytest.approx(0.01768)


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_reads_a_nested_balance_field():
    # vsegpt.ru does not document the response shape, so the parser has to
    # cope with the plausible variants rather than one guessed schema.
    respx.get(BALANCE_URL).mock(
        return_value=httpx.Response(200, json={"data": {"credits": 7.5, "other": "x"}})
    )

    assert await get_balance() == pytest.approx(7.5)


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_reads_a_numeric_string():
    respx.get(BALANCE_URL).mock(return_value=httpx.Response(200, json={"balance": "0.42"}))

    assert await get_balance() == pytest.approx(0.42)


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_reads_zero_as_zero_not_as_missing():
    # An empty account is exactly the case this exists for — it must not be
    # mistaken for "shape not recognised".
    respx.get(BALANCE_URL).mock(return_value=httpx.Response(200, json={"balance": 0}))

    assert await get_balance() == 0.0


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_raises_on_unrecognisable_shape():
    respx.get(BALANCE_URL).mock(return_value=httpx.Response(200, json={"status": "ok"}))

    with pytest.raises(AIGatewayInvalidResponseError):
        await get_balance()


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_raises_on_non_json_body():
    respx.get(BALANCE_URL).mock(return_value=httpx.Response(200, text="not json"))

    with pytest.raises(AIGatewayInvalidResponseError):
        await get_balance()


@respx.mock
@pytest.mark.asyncio
async def test_get_balance_raises_on_rejected_api_key():
    # The real symptom of a wrong key, verified live against api.vsegpt.ru.
    respx.get(BALANCE_URL).mock(
        return_value=httpx.Response(403, json={"error": {"message": "Incorrect API key.", "code": 403}})
    )

    with pytest.raises(AIGatewayInvalidResponseError):
        await get_balance()


# --- generate_image через Runware: у него свой формат запроса и ответа ---

RUNWARE_URL = "https://runware.test/v1"


@pytest.fixture
def _runware_env(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "runware")
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-test-key")
    monkeypatch.setenv("RUNWARE_BASE_URL", RUNWARE_URL)
    monkeypatch.setenv("RUNWARE_IMAGE_MODEL", "runware:100@1")


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_via_runware_returns_decoded_bytes(_runware_env):
    raw = b"runware-image-bytes"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskType": "imageInference",
                        "imageBase64Data": base64.b64encode(raw).decode(),
                    }
                ]
            },
        )
    )

    assert await generate_image("a cat astronaut") == raw


@respx.mock
@pytest.mark.asyncio
async def test_generate_image_via_runware_sends_a_task_shaped_request(_runware_env):
    """Runware ждёт массив задач, а не openai-совместимое тело запроса."""
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"imageBase64Data": base64.b64encode(b"x").decode()}]}
        )
    )

    await generate_image("рыжий кот в скафандре", size="768x512")

    body = json.loads(route.calls.last.request.content)
    assert isinstance(body, list) and len(body) == 1
    task = body[0]
    assert task["taskType"] == "imageInference"
    assert task["positivePrompt"] == "рыжий кот в скафандре"
    assert task["model"] == "runware:100@1"
    assert task["width"] == 768
    assert task["height"] == 512
    assert task["outputType"] == "base64Data"
    assert route.calls.last.request.headers["Authorization"] == "Bearer rw-test-key"


@respx.mock
@pytest.mark.asyncio
async def test_runware_translates_the_premium_model_into_its_own(_runware_env, monkeypatch):
    """Кнопка «Сделать реалистичнее» просит модель словами vsegpt.

    `bot/handlers/refine.py` передаёт `AI_GATEWAY_PREMIUM_IMAGE_MODEL`, то есть
    слаг vsegpt. Для Runware это бессмысленная строка, и запрос упал бы — а
    пользователь увидел бы поломку ровно на кнопке улучшения качества.
    """
    monkeypatch.setenv("AI_GATEWAY_PREMIUM_IMAGE_MODEL", "img-flux/pro1.1")
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"imageBase64Data": base64.b64encode(b"x").decode()}]}
        )
    )

    await generate_image("кот", model="img-flux/pro1.1")

    task = json.loads(route.calls.last.request.content)[0]
    assert task["model"] == "runware:101@1"


@respx.mock
@pytest.mark.asyncio
async def test_runware_reports_errors_returned_with_http_200(_runware_env):
    """Runware сообщает об отказе телом, а не кодом ответа.

    HTTP 200 с непустым `errors` — это провал задачи (нехватка баланса,
    неизвестная модель). Без разбора тела бот принял бы такой ответ за успех
    и упал бы позже, на попытке декодировать отсутствующую картинку.
    """
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "errors": [
                    {"code": "insufficientCredits", "message": "Insufficient available balance."}
                ],
            },
        )
    )

    with pytest.raises(AIGatewayInvalidResponseError) as exc_info:
        await generate_image("кот")

    assert "Insufficient available balance." in str(exc_info.value)


# --- generate_text через Runware: протокол тот же, меняются адрес и ключ ---


@respx.mock
@pytest.mark.asyncio
async def test_generate_text_via_runware_uses_its_endpoint_key_and_model(monkeypatch):
    monkeypatch.setenv("TEXT_PROVIDER", "runware")
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-test-key")
    monkeypatch.setenv("RUNWARE_BASE_URL", RUNWARE_URL)
    monkeypatch.setenv("RUNWARE_TEXT_MODEL", "deepseek-v4-flash")
    route = respx.post(f"{RUNWARE_URL}/chat/completions").mock(
        return_value=_chat_response("готовый пост")
    )

    assert await generate_text("напиши пост") == "готовый пост"

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer rw-test-key"
    assert json.loads(request.content)["model"] == "deepseek-v4-flash"


@respx.mock
@pytest.mark.asyncio
async def test_transcribe_locally_makes_no_network_call(monkeypatch):
    """С провайдером `local` расшифровка не должна никуда ходить.

    respx без замоканных маршрутов роняет любой исходящий запрос, поэтому
    сам факт успешного возврата доказывает, что в сеть никто не пошёл.
    """
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "local")
    from bot.services import local_transcriber

    async def _fake(audio_bytes, language_hint=None):
        assert audio_bytes == b"voice-bytes"
        return "Создай мне пост про отпуск."

    monkeypatch.setattr(local_transcriber, "transcribe_locally", _fake)

    assert await transcribe(b"voice-bytes", language_hint="ru") == "Создай мне пост про отпуск."
