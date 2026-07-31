from __future__ import annotations

import pytest

from bot.services import ffmpeg_tools


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b"" if self.returncode == 0 else b"boom"


def _fake_run(stdout: bytes = b"", returncode: int = 0):
    calls: list[tuple[str, ...]] = []

    async def runner(*args, **kwargs):
        calls.append(args)
        return _FakeProcess(stdout=stdout, returncode=returncode)

    runner.calls = calls
    return runner


@pytest.mark.asyncio
async def test_probe_duration_parses_ffprobe_output(monkeypatch):
    runner = _fake_run(stdout=b"31.480000\n")
    monkeypatch.setattr(ffmpeg_tools, "_run", runner)

    duration = await ffmpeg_tools.probe_duration("donor.mp4")

    assert duration == pytest.approx(31.48)
    assert "ffprobe" in runner.calls[0][0]
    assert "donor.mp4" in runner.calls[0]


@pytest.mark.asyncio
async def test_probe_duration_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(ffmpeg_tools, "_run", _fake_run(returncode=1))

    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.probe_duration("donor.mp4")


@pytest.mark.asyncio
async def test_probe_duration_raises_on_unparsable_output(monkeypatch):
    monkeypatch.setattr(ffmpeg_tools, "_run", _fake_run(stdout=b"N/A\n"))

    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.probe_duration("donor.mp4")


@pytest.mark.asyncio
async def test_extract_audio_returns_output_path(monkeypatch):
    runner = _fake_run()
    monkeypatch.setattr(ffmpeg_tools, "_run", runner)

    result = await ffmpeg_tools.extract_audio("donor.mp4", "donor.wav")

    assert result == "donor.wav"
    assert "-vn" in runner.calls[0]


@pytest.mark.asyncio
async def test_extract_audio_raises_on_failure(monkeypatch):
    monkeypatch.setattr(ffmpeg_tools, "_run", _fake_run(returncode=1))

    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.extract_audio("donor.mp4", "donor.wav")


@pytest.mark.asyncio
async def test_concat_audio_writes_list_file_and_returns_path(monkeypatch, tmp_path):
    runner = _fake_run()
    monkeypatch.setattr(ffmpeg_tools, "_run", runner)
    out_path = str(tmp_path / "voice.wav")

    result = await ffmpeg_tools.concat_audio(
        [str(tmp_path / "a.wav"), str(tmp_path / "b.wav")], out_path
    )

    assert result == out_path
    assert "concat" in runner.calls[0]


@pytest.mark.asyncio
async def test_concat_audio_rejects_empty_input(tmp_path):
    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.concat_audio([], str(tmp_path / "voice.wav"))
