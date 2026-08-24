from __future__ import annotations

import asyncio
import logging
import pathlib
import tempfile

from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


class FfmpegError(Exception):
    """ffmpeg или ffprobe завершились с ошибкой либо вернули мусор."""


# Module-level indirection so tests can replace the process launcher and
# never need a real ffmpeg binary — same trick as `_sleep` in ai_gateway.py.
_run = asyncio.create_subprocess_exec


async def _execute(*args: str) -> bytes:
    process = await _run(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode(errors="replace").strip()
        logger.error(
            "ffmpeg command failed: args=%s returncode=%s stderr=%s",
            args,
            process.returncode,
            message,
        )
        raise FfmpegError(f"Команда {args[0]} завершилась с кодом {process.returncode}")
    return stdout


async def run_ffmpeg(*args: str) -> bytes:
    """Запуск ffmpeg/ffprobe для соседних модулей.

    `video_note.py` держит свои команды у себя, но запуск процесса, разбор
    кода возврата и логирование одни на всех — дублировать их значит завести
    второе место, где эти ошибки обрабатываются по-своему.
    """
    return await _execute(*args)


async def probe_duration(path: str) -> float:
    stdout = await _execute(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        path,
    )
    raw = stdout.decode(errors="replace").strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise FfmpegError(f"ffprobe вернул неразбираемую длительность: {raw!r}") from exc


async def extract_audio(video_path: str, out_path: str) -> str:
    # Моно 16 кГц: этого достаточно для клонирования голоса и на порядок
    # экономит трафик при загрузке дорожки провайдеру.
    await _execute(
        "ffmpeg",
        "-v",
        "error",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        out_path,
    )
    return out_path


async def concat_audio(paths: list[str], out_path: str) -> str:
    if not paths:
        raise FfmpegError("Нечего склеивать: список дорожек пуст")

    # concat-демультиплексор требует файла-списка; все дорожки уже приведены
    # к одному формату в extract_audio, поэтому -c copy безопасен.
    directory = pathlib.Path(out_path).parent
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, dir=str(directory), encoding="utf-8"
    ) as handle:
        for path in paths:
            handle.write(f"file '{path}'\n")
        list_path = handle.name

    try:
        await _execute(
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c",
            "copy",
            "-y",
            out_path,
        )
    finally:
        pathlib.Path(list_path).unlink(missing_ok=True)
    return out_path
