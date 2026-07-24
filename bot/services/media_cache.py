from __future__ import annotations

import pathlib

from aiogram import Bot


async def cache_photo(bot: Bot, file_id: str, media_dir: str, page: str, block_id: str) -> str:
    directory = pathlib.Path(media_dir) / page
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{block_id}.jpg"
    await bot.download(file_id, destination=destination)
    return f"/media/{page}/{block_id}.jpg"
