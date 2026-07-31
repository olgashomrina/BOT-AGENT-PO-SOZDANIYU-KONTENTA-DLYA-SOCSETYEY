from __future__ import annotations

import httpx
import pytest
import respx

from bot.services import voice_gateway

BASE_URL = "https://api.elevenlabs.io/v1"


@pytest.fixture(autouse=True)
def _configure_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "voice-key")


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_returns_voice_id():
    route = respx.post(f"{BASE_URL}/voices/add").mock(
        return_value=httpx.Response(200, json={"voice_id": "voice-abc"})
    )

    voice_id = await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")

    assert voice_id == "voice-abc"
    assert route.called
    assert route.calls[0].request.headers["xi-api-key"] == "voice-key"


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_raises_on_missing_voice_id():
    respx.post(f"{BASE_URL}/voices/add").mock(
        return_value=httpx.Response(200, json={"detail": "no id here"})
    )

    with pytest.raises(voice_gateway.VoiceGatewayInvalidResponseError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_raises_on_http_error():
    respx.post(f"{BASE_URL}/voices/add").mock(return_value=httpx.Response(422))

    with pytest.raises(voice_gateway.VoiceGatewayError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_raises_on_transport_error():
    respx.post(f"{BASE_URL}/voices/add").mock(
        side_effect=httpx.ConnectError("no network")
    )

    with pytest.raises(voice_gateway.VoiceGatewayUnavailableError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@pytest.mark.asyncio
async def test_clone_voice_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")

    with pytest.raises(voice_gateway.VoiceGatewayError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@respx.mock
@pytest.mark.asyncio
async def test_delete_voice_calls_provider():
    route = respx.delete(f"{BASE_URL}/voices/voice-abc").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    await voice_gateway.delete_voice("voice-abc")

    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_delete_voice_raises_on_http_error():
    respx.delete(f"{BASE_URL}/voices/voice-abc").mock(
        return_value=httpx.Response(500)
    )

    with pytest.raises(voice_gateway.VoiceGatewayError):
        await voice_gateway.delete_voice("voice-abc")
