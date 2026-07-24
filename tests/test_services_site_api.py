from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.services.site_api import build_site_api_app
from bot.storage.site_content import upsert_site_content


@pytest.mark.asyncio
async def test_get_content_returns_existing_block(db_path, tmp_path):
    upsert_site_content(
        db_path, "services", "card_1", "Текст карточки", "file-id", "/media/services/card_1.jpg"
    )
    app = build_site_api_app(db_path, media_dir=str(tmp_path))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/content/services/card_1")
        assert response.status == 200
        body = await response.json()

    assert body == {"text": "Текст карточки", "photo_path": "/media/services/card_1.jpg"}


@pytest.mark.asyncio
async def test_get_content_returns_404_for_missing_block(db_path, tmp_path):
    app = build_site_api_app(db_path, media_dir=str(tmp_path))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/content/services/unknown")
        assert response.status == 404


@pytest.mark.asyncio
async def test_get_content_with_no_photo_returns_null_photo_path(db_path, tmp_path):
    upsert_site_content(db_path, "services", "card_1", "Только текст", None, None)
    app = build_site_api_app(db_path, media_dir=str(tmp_path))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/content/services/card_1")
        body = await response.json()

    assert body == {"text": "Только текст", "photo_path": None}
