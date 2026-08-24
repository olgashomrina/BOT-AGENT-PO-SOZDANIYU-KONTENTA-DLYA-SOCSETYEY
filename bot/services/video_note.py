"""Приведение картинки и видео к тому, что принимают провайдер и Telegram.

Два ограничения, оба куплены ошибками (docs/reference-video-avatar-engines.md):
Kling отвечает `invalidWidth` на телеграмных кружках 400×400 и требует сторону
512–2160; Telegram принимает video note только квадратом, H.264 + AAC
и с `+faststart`.
"""

from __future__ import annotations

from bot.services.ffmpeg_tools import FfmpegError, run_ffmpeg

# Практический размер кружка. Больше Telegram всё равно ужмёт, меньше —
# заметно мылит лицо.
VIDEO_NOTE_SIDE = 512

# Нижняя граница провайдера, а не наше пожелание.
MIN_PROVIDER_SIDE = 512


async def _probe_side(path: str) -> int:
    """Меньшая сторона картинки в пикселях."""
    stdout = await run_ffmpeg(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        path,
    )
    raw = stdout.decode(errors="replace").strip()
    try:
        width, height = (int(part) for part in raw.split("x")[:2])
    except ValueError as exc:
        raise FfmpegError(f"ffprobe вернул неразбираемый размер: {raw!r}") from exc
    return min(width, height)


async def ensure_min_side(
    src_path: str, out_path: str, min_side: int = MIN_PROVIDER_SIDE
) -> str:
    """Путь к картинке, у которой обе стороны не меньше `min_side`.

    Если исходник и так крупный, возвращается он сам: лишний прогон ffmpeg —
    это лишнее пересжатие, а сходство лица держится на резкости.
    """
    if await _probe_side(src_path) >= min_side:
        return src_path

    # Апскейлим только меньшую сторону до min_side, большая тянется следом
    # с сохранением пропорций — здесь не требуется квадрат, это работа
    # to_video_note, а тут распрямление лица было бы искажением.
    await run_ffmpeg(
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-vf",
        f"scale=w='if(lt(iw,ih),{min_side},-1)':"
        f"h='if(lt(iw,ih),-1,{min_side})':flags=lanczos",
        out_path,
    )
    return out_path


async def to_video_note(
    src_path: str, out_path: str, side: int = VIDEO_NOTE_SIDE
) -> str:
    await run_ffmpeg(
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-vf",
        f"scale={side}:{side}:force_original_aspect_ratio=increase,crop={side}:{side}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        out_path,
    )
    return out_path
