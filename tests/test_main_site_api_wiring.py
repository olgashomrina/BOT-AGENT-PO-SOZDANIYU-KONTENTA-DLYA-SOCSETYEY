from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from bot.main import run


@pytest.mark.asyncio
async def test_run_starts_site_api_server_alongside_polling(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SITE_API_PORT", "18080")

    with patch("bot.main.Bot") as mock_bot_cls, patch(
        "bot.main.web.TCPSite"
    ) as mock_tcp_site_cls, patch("bot.main.web.AppRunner") as mock_runner_cls, patch(
        "aiogram.Dispatcher.start_polling", new_callable=AsyncMock
    ) as mock_start_polling:
        mock_bot = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        mock_runner = AsyncMock()
        mock_runner_cls.return_value = mock_runner
        mock_site = AsyncMock()
        mock_tcp_site_cls.return_value = mock_site

        await run()

        mock_runner.setup.assert_awaited_once()
        mock_tcp_site_cls.assert_called_once_with(mock_runner, "0.0.0.0", 18080)
        mock_site.start.assert_awaited_once()
        # WHY patch aiogram.Dispatcher.start_polling directly: build_dispatcher()
        # constructs a real Dispatcher internally (not injectable), and the real
        # start_polling() runs an actual infinite long-polling loop — without
        # this patch the test would hang forever instead of exercising the
        # site-API startup/cleanup wiring this test targets.
        mock_start_polling.assert_awaited_once()
        mock_runner.cleanup.assert_awaited_once()
