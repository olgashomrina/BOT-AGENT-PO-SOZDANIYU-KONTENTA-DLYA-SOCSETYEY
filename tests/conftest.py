from __future__ import annotations

import pytest

from bot.handlers.authorpost import router as authorpost_router
from bot.handlers.channel import router as channel_router
from bot.handlers.circle import router as circle_router
from bot.handlers.content import router as content_router
from bot.handlers.costs import router as costs_router
from bot.handlers.errors import router as errors_router
from bot.handlers.language import router as language_router
from bot.handlers.refine import router as refine_router
from bot.handlers.settov import router as settov_router
from bot.handlers.site import router as site_router
from bot.handlers.start import router as start_router
from bot.storage.db import init_db

# The module-level singleton routers wired together in
# bot/main.py::build_dispatcher(). aiogram's Router.parent_router setter
# permanently refuses to re-attach a router that already has a parent
# (RuntimeError: "Router is already attached to ..."), and there's no
# built-in detach mechanism. Several tests attach these real singletons to
# their own scratch Dispatcher (test_error_handling.py) or exercise the real
# build_dispatcher() (test_main_site_api_wiring.py). Without cleanup, whichever
# test runs first "claims" a router and any later test doing the same collides
# — a fragile, collection-order-dependent failure. Resetting _parent_router
# here after every test keeps this symmetric regardless of test/collection
# order.
_SINGLETON_ROUTERS = (
    start_router,
    language_router,
    channel_router,
    site_router,
    settov_router,
    costs_router,
    authorpost_router,
    circle_router,
    content_router,
    refine_router,
    errors_router,
)


@pytest.fixture(autouse=True)
def _reset_singleton_routers():
    yield
    for router in _SINGLETON_ROUTERS:
        router._parent_router = None


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


# Обязательные переменные окружения для всего прогона.
#
# Хендлеры зовут `load_settings()` внутри себя, а он через `load_dotenv`
# подхватывает файл `.env` из корня проекта. На машине разработчика и на
# сервере такой файл есть, поэтому тесты кружочков проходили — и молча
# зависели от чужого файла с настоящими секретами. На GitHub Actions `.env`
# нет, и те же восемь тестов падали там с 31.07.2026 каждым запуском, а
# заодно валили выкладку. Значения заведомо ненастоящие: тест, которому
# нужен живой ключ, — это не тест.
#
# Тесты самой конфигурации это не ломает: они удаляют нужные переменные
# через `monkeypatch.delenv` уже после этой фикстуры и передают в
# `load_settings` заведомо отсутствующий файл.
_REQUIRED_ENV = {
    "BOT_TOKEN": "123456:test-token",
    "AI_PROXY_API_KEY": "test-ai-key",
    "OWNER_CHAT_ID": "42",
}


@pytest.fixture(autouse=True)
def _required_env(monkeypatch):
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
