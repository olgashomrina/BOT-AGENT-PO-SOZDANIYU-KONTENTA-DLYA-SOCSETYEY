from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from bot.services.avatar_gateway import (
    AvatarGatewayInvalidResponseError,
    AvatarGatewayUnavailableError,
    poll_render,
    start_render,
)

RUNWARE_URL = "https://runware.test/v1"
TASK_UUID = "0f5a5f4c-1a11-4d0e-9b2b-2f0f0f0f0f0f"


@pytest.fixture(autouse=True)
def _runware_env(monkeypatch):
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-test-key")
    monkeypatch.setenv("RUNWARE_BASE_URL", RUNWARE_URL)
    monkeypatch.setenv("AVATAR_MODEL", "klingai:avatar@2.0-standard")


@respx.mock
@pytest.mark.asyncio
async def test_start_render_returns_the_task_uuid():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    assert await start_render(b"image", b"audio") == TASK_UUID


@respx.mock
@pytest.mark.asyncio
async def test_start_render_sends_kling_shaped_inputs_as_base64():
    """`klingai:avatar` ждёт inputs.image и inputs.audio строками, не списками."""
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    await start_render(b"image-bytes", b"audio-bytes")

    task = json.loads(route.calls.last.request.content)[0]
    assert task["taskType"] == "videoInference"
    assert task["model"] == "klingai:avatar@2.0-standard"
    assert task["deliveryMethod"] == "async"
    assert task["includeCost"] is True
    assert task["inputs"]["image"].startswith("data:image/jpeg;base64,")
    assert task["inputs"]["audio"].startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(task["inputs"]["image"].split(",", 1)[1]) == b"image-bytes"
    assert base64.b64decode(task["inputs"]["audio"].split(",", 1)[1]) == b"audio-bytes"


@respx.mock
@pytest.mark.asyncio
async def test_start_render_never_sends_a_public_url():
    # Личное лицо и личный голос не должны существовать по ссылке ни секунды.
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    await start_render(b"image", b"audio")

    body = route.calls.last.request.content.decode()
    assert "http://" not in body
    assert "https://" not in body


@respx.mock
@pytest.mark.asyncio
async def test_pixverse_gets_its_own_top_level_shape(monkeypatch):
    # У PixVerse поля лежат на верхнем уровне, а не в inputs. Это единственная
    # причина, по которой шлюз не может быть тоньше.
    monkeypatch.setenv("AVATAR_MODEL", "pixverse:lipsync@1")
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    await start_render(b"image", b"audio")

    task = json.loads(route.calls.last.request.content)[0]
    assert "inputs" not in task
    assert task["referenceImages"][0].startswith("data:image/jpeg;base64,")
    assert task["inputAudios"][0].startswith("data:audio/mpeg;base64,")


@respx.mock
@pytest.mark.asyncio
async def test_poll_reports_a_render_still_running():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is False
    assert status.failed is False
    assert status.video_bytes is None


@respx.mock
@pytest.mark.asyncio
async def test_poll_returns_video_bytes_and_cost_when_ready():
    raw = b"mp4-bytes"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoBase64Data": base64.b64encode(raw).decode(),
                        "cost": 0.2231,
                    }
                ]
            },
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is True
    assert status.video_bytes == raw
    assert status.cost_usd == pytest.approx(0.2231)


@respx.mock
@pytest.mark.asyncio
async def test_poll_raises_a_typed_error_on_malformed_base64_video():
    # Finding 2 (final whole-branch review): base64.b64decode was unguarded,
    # so a malformed payload would raise binascii.Error/ValueError untyped,
    # escaping the AvatarGatewayError hierarchy every caller is promised.
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoBase64Data": "not-valid-base64!!!",
                    }
                ]
            },
        )
    )

    with pytest.raises(AvatarGatewayInvalidResponseError):
        await poll_render(TASK_UUID)


@respx.mock
@pytest.mark.asyncio
async def test_poll_decodes_a_line_wrapped_base64_video():
    # Finding 3 (this round): `validate=True` is stricter than the previous
    # fix needed to be — it rejects the newline-wrapped base64 bodies that
    # HTTP payloads commonly carry, even though the same bytes decode fine
    # under the plain `base64.b64decode`. Combined with finding 2, that made
    # an already-paid render fail on every tick for a perfectly valid video.
    raw = b"mp4-bytes-for-a-line-wrapped-payload-test"
    encoded = base64.b64encode(raw).decode()
    wrapped = "\n".join(encoded[i : i + 20] for i in range(0, len(encoded), 20))
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoBase64Data": wrapped,
                    }
                ]
            },
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.video_bytes == raw


@respx.mock
@pytest.mark.asyncio
async def test_poll_downloads_the_video_when_only_a_url_comes_back():
    # Runware отдаёт результат то байтами, то ссылкой. Наружу шлюз в обоих
    # случаях отдаёт байты — вызывающий код о разнице знать не должен.
    raw = b"mp4-from-url"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoURL": "https://cdn.runware.test/v.mp4",
                        "cost": 0.2,
                    }
                ]
            },
        )
    )
    respx.get("https://cdn.runware.test/v.mp4").mock(
        return_value=httpx.Response(200, content=raw)
    )

    status = await poll_render(TASK_UUID)

    assert status.video_bytes == raw


@respx.mock
@pytest.mark.asyncio
async def test_poll_reports_a_provider_error_as_failed():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "invalidWidth"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.failed is True
    assert "invalidWidth" in status.error


@respx.mock
@pytest.mark.asyncio
async def test_start_render_raises_on_a_provider_error():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "no balance"}]})
    )

    with pytest.raises(AvatarGatewayInvalidResponseError):
        await start_render(b"image", b"audio")


@respx.mock
@pytest.mark.asyncio
async def test_start_render_raises_when_the_provider_is_unreachable():
    respx.post(RUNWARE_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(AvatarGatewayUnavailableError):
        await start_render(b"image", b"audio")


@respx.mock
@pytest.mark.asyncio
async def test_start_render_raises_on_http_error_status():
    respx.post(RUNWARE_URL).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(AvatarGatewayUnavailableError):
        await start_render(b"image", b"audio")


@respx.mock
@pytest.mark.asyncio
async def test_poll_reports_a_cancelled_render_as_failed():
    # "cancelled" — терминальный статус без видео, не "ещё работает".
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "cancelled"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is False
    assert status.failed is True


@respx.mock
@pytest.mark.asyncio
async def test_poll_reports_success_without_video_as_failed():
    # "success" без videoBase64Data/videoURL — провайдер соврал, это отказ,
    # а не "ещё работает".
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "success"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is False
    assert status.failed is True
    assert status.error


@respx.mock
@pytest.mark.asyncio
async def test_poll_keeps_the_video_when_cost_is_unparseable():
    # Числовые поля провайдера ненадёжны (расхождение с фактом в 7,4 раза
    # уже наблюдалось для другой модели) — нечитаемый cost не должен стоить
    # уже оплаченного рендера.
    raw = b"mp4-bytes"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoBase64Data": base64.b64encode(raw).decode(),
                        "cost": "не число",
                    }
                ]
            },
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is True
    assert status.failed is False
    assert status.video_bytes == raw
    assert status.cost_usd is None


@respx.mock
@pytest.mark.asyncio
async def test_poll_treats_an_unknown_status_word_as_still_running():
    # Слово статуса, не входящее ни в один из известных списков, намеренно
    # читается как "ещё работает" — терять оплаченный рендер дороже, чем
    # опросить его лишний раз.
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "queued"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is False
    assert status.failed is False
