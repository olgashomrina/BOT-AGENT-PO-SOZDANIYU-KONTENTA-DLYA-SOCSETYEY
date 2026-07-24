from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock

import pytest

from bot.services.media_cache import cache_photo


@pytest.mark.asyncio
async def test_cache_photo_downloads_to_expected_path_and_returns_url(tmp_path):
    bot = AsyncMock()
    media_dir = str(tmp_path / "media")

    result = await cache_photo(bot, "file-id-123", media_dir, "services", "card_1")

    expected_destination = pathlib.Path(media_dir) / "services" / "card_1.jpg"
    bot.download.assert_awaited_once_with("file-id-123", destination=expected_destination)
    assert result == "/media/services/card_1.jpg"
    assert expected_destination.parent.is_dir()


@pytest.mark.asyncio
async def test_cache_photo_creates_nested_directory_if_missing(tmp_path):
    bot = AsyncMock()
    media_dir = str(tmp_path / "does" / "not" / "exist" / "yet")

    await cache_photo(bot, "file-id-456", media_dir, "services", "card_2")

    assert (pathlib.Path(media_dir) / "services").is_dir()
