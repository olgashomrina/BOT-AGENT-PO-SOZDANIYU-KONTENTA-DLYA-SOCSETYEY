from __future__ import annotations

from unittest.mock import ANY, AsyncMock, patch

import pytest
from aiogram.types import MenuButtonCommands

from bot.locales.loader import SUPPORTED_LANGUAGES
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
    ) as mock_start_polling, patch(
        "bot.main.build_digest_scheduler"
    ) as mock_scheduler_factory:
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
        # DIGEST_SEND_HOUR is not set above, so the default (9) from
        # bot/config.py must reach the scheduler factory unchanged — a bug
        # that passed the wrong settings field would go undetected otherwise.
        mock_scheduler_factory.assert_called_once_with(mock_bot, ANY, 9)
        mock_scheduler_factory.return_value.start.assert_called_once()
        mock_scheduler_factory.return_value.shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_run_configures_native_menu_button_before_polling(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SITE_API_PORT", "18081")

    with patch("bot.main.Bot") as mock_bot_cls, patch(
        "bot.main.web.TCPSite"
    ) as mock_tcp_site_cls, patch("bot.main.web.AppRunner") as mock_runner_cls, patch(
        "aiogram.Dispatcher.start_polling", new_callable=AsyncMock
    ) as mock_start_polling, patch(
        "bot.main.build_digest_scheduler"
    ) as mock_scheduler_factory:
        mock_bot = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        mock_runner_cls.return_value = AsyncMock()
        mock_tcp_site_cls.return_value = AsyncMock()

        await run()

        # One set_my_commands call per supported language, registering /start
        # so the native Telegram menu button (bottom-left of the input field)
        # can offer it without the user typing anything.
        assert mock_bot.set_my_commands.await_count == len(SUPPORTED_LANGUAGES)
        called_lang_codes = {
            call.kwargs["language_code"] for call in mock_bot.set_my_commands.await_args_list
        }
        assert called_lang_codes == set(SUPPORTED_LANGUAGES)
        for call in mock_bot.set_my_commands.await_args_list:
            (commands,) = call.args
            assert [c.command for c in commands] == ["start"]

        mock_bot.set_chat_menu_button.assert_awaited_once()
        menu_button = mock_bot.set_chat_menu_button.await_args.kwargs["menu_button"]
        assert isinstance(menu_button, MenuButtonCommands)

        # Menu button must be configured before polling starts, not after.
        assert mock_bot.set_my_commands.await_count > 0
        mock_start_polling.assert_awaited_once()
