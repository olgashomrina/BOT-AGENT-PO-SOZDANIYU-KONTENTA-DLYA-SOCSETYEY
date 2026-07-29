from __future__ import annotations

import pytest

from bot.handlers.authorpost import router as authorpost_router
from bot.handlers.channel import router as channel_router
from bot.handlers.content import router as content_router
from bot.handlers.errors import router as errors_router
from bot.handlers.language import router as language_router
from bot.handlers.refine import router as refine_router
from bot.handlers.settov import router as settov_router
from bot.handlers.site import router as site_router
from bot.handlers.start import router as start_router
from bot.storage.db import init_db

# The 9 module-level singleton routers wired together in
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
    authorpost_router,
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
