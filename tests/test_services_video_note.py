from __future__ import annotations

import pytest

from bot.services import video_note


class _FakeProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


@pytest.fixture
def calls(monkeypatch):
    """Перехват запуска ffmpeg: настоящий двоичный файл тестам не нужен."""
    recorded: list[tuple[str, ...]] = []

    async def fake_run(*args, **kwargs):
        recorded.append(args)
        return _FakeProcess()

    monkeypatch.setattr("bot.services.ffmpeg_tools._run", fake_run)
    return recorded


@pytest.mark.asyncio
async def test_ensure_min_side_upscales_a_small_square(calls, monkeypatch):
    # Телеграмный кружок приходит 400×400, а Kling требует сторону 512–2160
    # и отвечает invalidWidth. Апскейл обязателен, а не украшение.
    monkeypatch.setattr(video_note, "_probe_side", _fake_side(400))

    await video_note.ensure_min_side("in.jpg", "out.jpg")

    args = " ".join(calls[-1])
    assert "scale=512:512" in args
    assert "out.jpg" in args


@pytest.mark.asyncio
async def test_ensure_min_side_leaves_a_big_image_alone(calls, monkeypatch):
    # Лишний прогон ffmpeg — это лишняя пересжатая картинка и потеря резкости,
    # на которой держится сходство лица.
    monkeypatch.setattr(video_note, "_probe_side", _fake_side(1024))

    result = await video_note.ensure_min_side("in.jpg", "out.jpg")

    assert result == "in.jpg"
    assert calls == []


@pytest.mark.asyncio
async def test_to_video_note_produces_a_square_h264_aac_stream(calls):
    await video_note.to_video_note("in.mp4", "out.mp4")

    args = " ".join(calls[-1])
    assert "scale=512:512" in args
    assert "libx264" in args
    assert "aac" in args
    assert "+faststart" in args
    assert args.endswith("out.mp4")


@pytest.mark.asyncio
async def test_ffmpeg_failure_surfaces_as_ffmpeg_error(monkeypatch):
    async def failing_run(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"broken input")

    monkeypatch.setattr("bot.services.ffmpeg_tools._run", failing_run)

    from bot.services.ffmpeg_tools import FfmpegError

    with pytest.raises(FfmpegError):
        await video_note.to_video_note("in.mp4", "out.mp4")


def _fake_side(value: int):
    async def _probe(path: str) -> int:
        return value

    return _probe
