# Пилот двусторонней синхронизации бота с сайтом (bot_site) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working pilot where the bot can push generated text+photo to one service card on `services.html` and pull that card's current content back into the bot for editing, plus a "МОЙ САЙТ" button that opens the live site as a Telegram Mini App.

**Architecture:** A read-only `aiohttp.web` API runs inside the existing bot process (long polling + web server share one event loop), backed by a new `site_content` SQLite table. The bot writes to that table directly in handler code (no HTTP round-trip for writes). A one-time JS snippet (delivered via `bot_site/`, not committed to the site's own repo) makes `services.html` fetch and render that table's content for one card.

**Tech Stack:** Python, aiogram 3.29 (existing), aiohttp (already installed transitively via aiogram, no new dependency), SQLite (existing `bot/storage/db.py`), nginx + Let's Encrypt/certbot + sslip.io (new, server-side only).

## Global Constraints

- No public write endpoint — the API (`bot/services/site_api.py`) only ever exposes `GET` routes; the bot writes to `site_content` directly in its own handler code, never over HTTP to itself.
- HTTPS is mandatory for the public API host (GitHub Pages serves the site over HTTPS; browsers block HTTPS→HTTP fetches as mixed content) — use nginx + Let's Encrypt via the free `147-45-175-189.sslip.io` hostname, not plain HTTP.
- Telegram `file_id` stays the source of truth for photos (existing project convention, see `bot/handlers/refine.py:254-260`) — any file saved to local disk is a cache for public HTTP serving only, regenerated from `file_id` on each push.
- Every new user-facing string must exist in all 4 locale files (`bot/locales/ru.py`, `en.py`, `vi.py`, `zh.py`) — enforced by `tests/test_localization.py::test_all_locales_have_identical_keys`, which fails the whole suite if any key set differs.
- Pilot scope only: `page="services"`, `block_id="card_1"` — no other of the 9 site pages, no other service cards, no video (text + photo only). Do not build a page/card selector UI.
- `site_content` is a brand-new table — add it via `CREATE TABLE IF NOT EXISTS` in `bot/storage/db.py`'s `SCHEMA` string. No `ALTER TABLE` migration helper is needed (those only exist for new columns on the already-deployed `users` table, e.g. `_ensure_channel_id_column`).
- aiohttp is already installed (transitive dependency of aiogram) — do not add FastAPI, Flask, or any other web framework.

---

### Task 1: `site_content` storage layer

**Files:**
- Modify: `bot/storage/db.py` (add table to `SCHEMA`)
- Create: `bot/storage/site_content.py`
- Test: `tests/test_storage_site_content.py`

**Interfaces:**
- Produces: `SiteContent` dataclass (`text: str`, `photo_file_id: str | None`, `photo_static_path: str | None`, `updated_at: str`); `upsert_site_content(db_path: str, page: str, block_id: str, text: str, photo_file_id: str | None, photo_static_path: str | None) -> None`; `get_site_content(db_path: str, page: str, block_id: str) -> SiteContent | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage_site_content.py
from __future__ import annotations

from bot.storage.site_content import get_site_content, upsert_site_content


def test_unknown_block_returns_none(db_path):
    assert get_site_content(db_path, "services", "card_1") is None


def test_upsert_then_get_returns_stored_content(db_path):
    upsert_site_content(
        db_path, "services", "card_1", "Текст карточки", "file-id-1", "/media/services/card_1.jpg"
    )

    content = get_site_content(db_path, "services", "card_1")

    assert content.text == "Текст карточки"
    assert content.photo_file_id == "file-id-1"
    assert content.photo_static_path == "/media/services/card_1.jpg"
    assert content.updated_at


def test_upsert_twice_overwrites_previous_value(db_path):
    upsert_site_content(db_path, "services", "card_1", "Старый текст", "old-file-id", "/media/services/card_1.jpg")
    upsert_site_content(db_path, "services", "card_1", "Новый текст", "new-file-id", "/media/services/card_1.jpg")

    content = get_site_content(db_path, "services", "card_1")

    assert content.text == "Новый текст"
    assert content.photo_file_id == "new-file-id"


def test_upsert_with_no_photo_stores_none(db_path):
    upsert_site_content(db_path, "services", "card_1", "Только текст", None, None)

    content = get_site_content(db_path, "services", "card_1")

    assert content.photo_file_id is None
    assert content.photo_static_path is None


def test_different_block_ids_do_not_collide(db_path):
    upsert_site_content(db_path, "services", "card_1", "Карточка 1", None, None)
    upsert_site_content(db_path, "services", "card_2", "Карточка 2", None, None)

    assert get_site_content(db_path, "services", "card_1").text == "Карточка 1"
    assert get_site_content(db_path, "services", "card_2").text == "Карточка 2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage_site_content.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.storage.site_content'`

- [ ] **Step 3: Add the table to the schema**

In `bot/storage/db.py`, add to the `SCHEMA` string (after the existing `style_examples` table, still inside the triple-quoted string):

```python
CREATE TABLE IF NOT EXISTS site_content (
    page TEXT NOT NULL,
    block_id TEXT NOT NULL,
    text TEXT,
    photo_file_id TEXT,
    photo_static_path TEXT,
    updated_at TEXT,
    PRIMARY KEY (page, block_id)
);
```

- [ ] **Step 4: Write the storage module**

```python
# bot/storage/site_content.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection


@dataclass(frozen=True)
class SiteContent:
    text: str
    photo_file_id: str | None
    photo_static_path: str | None
    updated_at: str


def upsert_site_content(
    db_path: str,
    page: str,
    block_id: str,
    text: str,
    photo_file_id: str | None,
    photo_static_path: str | None,
) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO site_content (page, block_id, text, photo_file_id, photo_static_path, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(page, block_id) DO UPDATE SET "
            "text = excluded.text, photo_file_id = excluded.photo_file_id, "
            "photo_static_path = excluded.photo_static_path, updated_at = excluded.updated_at",
            (page, block_id, text, photo_file_id, photo_static_path, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def get_site_content(db_path: str, page: str, block_id: str) -> SiteContent | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT text, photo_file_id, photo_static_path, updated_at "
            "FROM site_content WHERE page = ? AND block_id = ?",
            (page, block_id),
        ).fetchone()
        if row is None:
            return None
        return SiteContent(text=row[0], photo_file_id=row[1], photo_static_path=row[2], updated_at=row[3])
    finally:
        connection.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_storage_site_content.py tests/test_storage_db.py -v`
Expected: PASS (all tests, including the existing `test_storage_db.py` suite, which must still pass unchanged)

- [ ] **Step 6: Commit**

```bash
git add bot/storage/db.py bot/storage/site_content.py tests/test_storage_site_content.py
git commit -m "feat: add site_content storage layer for site sync pilot"
```

---

### Task 2: Config settings for Mini App URL and site API

**Files:**
- Modify: `bot/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Settings.mini_app_url: str`, `Settings.site_api_host: str`, `Settings.site_api_port: int`, `Settings.site_media_dir: str` — all optional with defaults, read later by `bot/main.py`, `bot/handlers/site.py`, `bot/services/site_api.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_load_settings_mini_app_url_defaults_to_empty(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("MINI_APP_URL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.mini_app_url == ""


def test_load_settings_site_api_defaults(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("SITE_API_HOST", raising=False)
    monkeypatch.delenv("SITE_API_PORT", raising=False)
    monkeypatch.delenv("SITE_MEDIA_DIR", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.site_api_host == "0.0.0.0"
    assert settings.site_api_port == 8080
    assert settings.site_media_dir == "site_media"


def test_load_settings_reads_site_api_overrides(monkeypatch, tmp_path):
    _set_required_env(
        monkeypatch,
        {
            "MINI_APP_URL": "https://olgashomrina.github.io/my-lending-test/",
            "SITE_API_HOST": "127.0.0.1",
            "SITE_API_PORT": "9090",
            "SITE_MEDIA_DIR": "custom_media",
        },
    )

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.mini_app_url == "https://olgashomrina.github.io/my-lending-test/"
    assert settings.site_api_host == "127.0.0.1"
    assert settings.site_api_port == 9090
    assert settings.site_media_dir == "custom_media"


def test_load_settings_raises_when_site_api_port_not_numeric(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"SITE_API_PORT": "not-a-number"})

    with pytest.raises(ConfigError):
        load_settings(env_file=_missing_env_file(tmp_path))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'mini_app_url'`

- [ ] **Step 3: Update `bot/config.py`**

Add near the other `DEFAULT_*` constants:

```python
DEFAULT_MINI_APP_URL = ""
DEFAULT_SITE_API_HOST = "0.0.0.0"
DEFAULT_SITE_API_PORT = 8080
DEFAULT_SITE_MEDIA_DIR = "site_media"
```

Add fields to the `Settings` dataclass (after `content_variants_count`):

```python
    mini_app_url: str
    site_api_host: str
    site_api_port: int
    site_media_dir: str
```

In `load_settings`, after the `content_variants_count` block, add:

```python
    mini_app_url = os.environ.get("MINI_APP_URL", DEFAULT_MINI_APP_URL)
    site_api_host = os.environ.get("SITE_API_HOST", DEFAULT_SITE_API_HOST)
    site_media_dir = os.environ.get("SITE_MEDIA_DIR", DEFAULT_SITE_MEDIA_DIR)

    try:
        site_api_port = int(os.environ.get("SITE_API_PORT", DEFAULT_SITE_API_PORT))
    except ValueError as exc:
        raise ConfigError("SITE_API_PORT должен быть целым числом.") from exc
```

And add the four fields to the final `return Settings(...)` call:

```python
        mini_app_url=mini_app_url,
        site_api_host=site_api_host,
        site_api_port=site_api_port,
        site_media_dir=site_media_dir,
```

- [ ] **Step 4: Update `.env.example`**

Replace the existing trailing block (`MINI_APP_URL=` and its comment) with:

```
# Ссылка на задеплоенный Mini App (веб-страницу), которую бот открывает
# внутри Telegram.
MINI_APP_URL=

# Настройки внутреннего веб-сервера, который отдаёт вашему сайту
# актуальный текст/фото карточки услуги (пилот, см. docs/superpowers/specs/
# 2026-07-24-site-sync-pilot-design.md). Необязательно, есть значения по
# умолчанию — трогать нужно только на реальном сервере, не на своём
# компьютере.
SITE_API_HOST=0.0.0.0
SITE_API_PORT=8080
SITE_MEDIA_DIR=site_media
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/config.py .env.example tests/test_config.py
git commit -m "feat: add MINI_APP_URL and site API settings to config"
```

---

### Task 3: Media cache service

**Files:**
- Create: `bot/services/media_cache.py`
- Test: `tests/test_services_media_cache.py`

**Interfaces:**
- Consumes: `aiogram.Bot.download(file_id, destination=...)` (already used by aiogram; see `.venv/Lib/site-packages/aiogram/client/bot.py:462`).
- Produces: `async def cache_photo(bot: Bot, file_id: str, media_dir: str, page: str, block_id: str) -> str` — downloads the photo and returns its public path (e.g. `/media/services/card_1.jpg`), consumed by `bot/handlers/site.py` in Task 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services_media_cache.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services_media_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.services.media_cache'`

- [ ] **Step 3: Write the implementation**

```python
# bot/services/media_cache.py
from __future__ import annotations

import pathlib

from aiogram import Bot


async def cache_photo(bot: Bot, file_id: str, media_dir: str, page: str, block_id: str) -> str:
    directory = pathlib.Path(media_dir) / page
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{block_id}.jpg"
    await bot.download(file_id, destination=destination)
    return f"/media/{page}/{block_id}.jpg"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_services_media_cache.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/media_cache.py tests/test_services_media_cache.py
git commit -m "feat: add media_cache service to download Telegram photos for site serving"
```

---

### Task 4: Site API (aiohttp, read-only)

**Files:**
- Create: `bot/services/site_api.py`
- Test: `tests/test_services_site_api.py`

**Interfaces:**
- Consumes: `bot.storage.site_content.get_site_content`.
- Produces: `build_site_api_app(db_path: str, media_dir: str) -> aiohttp.web.Application`, consumed by `bot/main.py` in Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_services_site_api.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services_site_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.services.site_api'`

- [ ] **Step 3: Write the implementation**

```python
# bot/services/site_api.py
from __future__ import annotations

from aiohttp import web

from bot.storage.site_content import get_site_content


def build_site_api_app(db_path: str, media_dir: str) -> web.Application:
    app = web.Application()
    app["db_path"] = db_path
    app.router.add_get("/content/{page}/{block_id}", handle_get_content)
    app.router.add_static("/media/", media_dir, show_index=False)
    return app


async def handle_get_content(request: web.Request) -> web.Response:
    page = request.match_info["page"]
    block_id = request.match_info["block_id"]
    db_path = request.app["db_path"]

    content = get_site_content(db_path, page, block_id)
    if content is None:
        return web.json_response({"error": "not_found"}, status=404)

    return web.json_response({"text": content.text, "photo_path": content.photo_static_path})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_services_site_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/site_api.py tests/test_services_site_api.py
git commit -m "feat: add read-only site content API (aiohttp)"
```

---

### Task 5: Keyboards and locale strings

**Files:**
- Create: `bot/keyboards/site.py`
- Modify: `bot/keyboards/refine.py`
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`
- Test: `tests/test_keyboards_site.py`, `tests/test_keyboards_refine.py`

**Interfaces:**
- Produces: `bot.keyboards.site.build_site_menu_keyboard(mini_app_url: str, lang: str) -> InlineKeyboardMarkup`, `bot.keyboards.site.PILOT_PAGE = "services"`, `bot.keyboards.site.PILOT_BLOCK = "card_1"`, `bot.keyboards.site.CALLBACK_PULL_PREFIX = "site:pull"`; `bot.keyboards.refine.CALLBACK_SITE_PUSH_PREFIX = "site:push"` (new export alongside the existing ones) — consumed by `bot/handlers/site.py` in Task 6.

- [ ] **Step 1: Add the new locale keys**

In `bot/locales/ru.py`, add (near the other `refine`/`publish` keys):

```python
    "site_menu_intro": (
        "Здесь можно открыть ваш сайт или забрать содержимое карточки услуги "
        "для правки."
    ),
    "open_site_button": "МОЙ САЙТ",
    "pull_from_site_button": "Забрать карточку «Услуги»",
    "site_push_button": "Залить на сайт",
    "site_pull_empty": (
        "На сайте пока ничего не залито для этой карточки — сначала "
        "используйте кнопку «Залить на сайт»."
    ),
    "site_push_success": "Готово! Карточка на сайте обновлена.",
    "site_push_photo_failed": (
        "Не получилось скачать фото для сайта — попробуйте ещё раз чуть "
        "позже."
    ),
```

In `bot/locales/en.py`, add:

```python
    "site_menu_intro": (
        "Here you can open your site or pull the service card content for editing."
    ),
    "open_site_button": "MY SITE",
    "pull_from_site_button": "Pull the 'Services' card",
    "site_push_button": "Push to site",
    "site_pull_empty": (
        "Nothing has been pushed to this card on the site yet — use the "
        "'Push to site' button first."
    ),
    "site_push_success": "Done! The card on the site has been updated.",
    "site_push_photo_failed": "Couldn't download the photo for the site — please try again in a moment.",
```

In `bot/locales/vi.py`, add:

```python
    "site_menu_intro": (
        "Ở đây bạn có thể mở trang web hoặc lấy nội dung thẻ dịch vụ về để chỉnh sửa."
    ),
    "open_site_button": "TRANG WEB CỦA TÔI",
    "pull_from_site_button": "Lấy thẻ 'Dịch vụ'",
    "site_push_button": "Đăng lên trang web",
    "site_pull_empty": (
        "Chưa có nội dung nào được đăng cho thẻ này trên trang web — hãy "
        "dùng nút 'Đăng lên trang web' trước."
    ),
    "site_push_success": "Xong! Thẻ trên trang web đã được cập nhật.",
    "site_push_photo_failed": "Không thể tải ảnh cho trang web — vui lòng thử lại sau.",
```

In `bot/locales/zh.py`, add:

```python
    "site_menu_intro": "在这里可以打开您的网站，或取回服务卡片内容进行编辑。",
    "open_site_button": "我的网站",
    "pull_from_site_button": "取回'服务'卡片",
    "site_push_button": "发布到网站",
    "site_pull_empty": "该卡片尚未发布到网站——请先使用'发布到网站'按钮。",
    "site_push_success": "完成！网站上的卡片已更新。",
    "site_push_photo_failed": "未能下载网站用的图片——请稍后重试。",
```

- [ ] **Step 2: Run the localization parity test**

Run: `pytest tests/test_localization.py -v`
Expected: PASS (all 4 locale files now have identical key sets again)

- [ ] **Step 3: Write the failing keyboard tests**

```python
# tests/test_keyboards_site.py
from __future__ import annotations

from bot.keyboards.site import PILOT_BLOCK, PILOT_PAGE, build_site_menu_keyboard
from bot.locales.loader import get_string


def test_includes_open_site_button_when_url_set():
    keyboard = build_site_menu_keyboard("https://olgashomrina.github.io/my-lending-test/", "ru")

    first_row = keyboard.inline_keyboard[0]
    assert first_row[0].text == get_string("open_site_button", "ru")
    assert first_row[0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


def test_omits_open_site_button_when_url_missing():
    keyboard = build_site_menu_keyboard("", "ru")

    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}"


def test_pull_button_text_and_callback_data():
    keyboard = build_site_menu_keyboard("https://example.com/", "en")

    pull_button = keyboard.inline_keyboard[-1][0]
    assert pull_button.text == get_string("pull_from_site_button", "en")
    assert pull_button.callback_data == f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}"
```

```python
# tests/test_keyboards_refine.py
from __future__ import annotations

from bot.keyboards.refine import CALLBACK_SITE_PUSH_PREFIX, build_refine_keyboard
from bot.locales.loader import get_string


def test_includes_site_push_button():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    last_row = keyboard.inline_keyboard[-1]
    assert last_row[0].text == get_string("site_push_button", "ru")
    assert last_row[0].callback_data == f"{CALLBACK_SITE_PUSH_PREFIX}:telegram:1"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_keyboards_site.py tests/test_keyboards_refine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.keyboards.site'` and `ImportError: cannot import name 'CALLBACK_SITE_PUSH_PREFIX'`

- [ ] **Step 5: Write `bot/keyboards/site.py`**

```python
# bot/keyboards/site.py
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.locales.loader import get_string

CALLBACK_PULL_PREFIX = "site:pull"
PILOT_PAGE = "services"
PILOT_BLOCK = "card_1"


def build_site_menu_keyboard(mini_app_url: str, lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mini_app_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("open_site_button", lang),
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("pull_from_site_button", lang),
                callback_data=f"{CALLBACK_PULL_PREFIX}:{PILOT_PAGE}:{PILOT_BLOCK}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 6: Update `bot/keyboards/refine.py`**

Add the new constant near the other `CALLBACK_*` constants:

```python
CALLBACK_SITE_PUSH_PREFIX = "site:push"
```

Add the new button block before the final `return`, and include it in the returned markup:

```python
    site_push_button = [
        InlineKeyboardButton(
            text=get_string("site_push_button", lang),
            callback_data=f"{CALLBACK_SITE_PUSH_PREFIX}:{platform}:{variant_index}",
        )
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons, publish_button, image_button, site_push_button]
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_site.py tests/test_keyboards_refine.py tests/test_handlers_refine.py tests/test_localization.py -v`
Expected: PASS — including the pre-existing `test_handlers_refine.py` suite, which must be unaffected since it never asserts on the exact keyboard row count.

- [ ] **Step 8: Commit**

```bash
git add bot/keyboards/site.py bot/keyboards/refine.py bot/locales/ru.py bot/locales/en.py bot/locales/vi.py bot/locales/zh.py tests/test_keyboards_site.py tests/test_keyboards_refine.py
git commit -m "feat: add site menu keyboard, site push button, and their locale strings"
```

---

### Task 6: Site handlers (`/site`, pull, push)

**Files:**
- Create: `bot/handlers/site.py`
- Modify: `bot/main.py` (register the router — router wiring only; the API server startup is Task 7)
- Test: `tests/test_handlers_site.py`

**Interfaces:**
- Consumes: `bot.handlers.content._finish`, `bot.handlers.content._resolve_language` (existing cross-module private imports, same pattern as `bot/handlers/refine.py:11`); `bot.handlers.refine._check_whitelist_or_reply`, `bot.handlers.refine._check_limit_or_reply`; `bot.keyboards.site.build_site_menu_keyboard`, `PILOT_PAGE`, `PILOT_BLOCK`; `bot.services.media_cache.cache_photo`; `bot.storage.site_content.get_site_content`, `upsert_site_content`; `bot.storage.users.get_pending_media`, `set_pending_media`; `bot.storage.limits.increment_usage`.
- Produces: `router` (aiogram `Router`, name `"site"`), consumed by `bot/main.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handlers_site.py
from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.site import cmd_site, on_site_pull, on_site_push
from bot.keyboards.site import PILOT_BLOCK, PILOT_PAGE
from bot.locales.loader import get_string
from bot.services import content_generator
from bot.storage.limits import get_daily_count
from bot.storage.site_content import get_site_content, upsert_site_content
from bot.storage.users import get_pending_media, set_pending_media
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _ai_gateway_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_message(telegram_id: int = TELEGRAM_ID):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    return message


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = ""):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_cmd_site_shows_menu_with_mini_app_button(db_path, monkeypatch):
    monkeypatch.setenv("MINI_APP_URL", "https://olgashomrina.github.io/my-lending-test/")
    message = _make_message()

    await cmd_site(message, db_path)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("site_menu_intro", "ru")
    keyboard = kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


@pytest.mark.asyncio
async def test_cmd_site_shows_menu_without_mini_app_button_when_unset(db_path, monkeypatch):
    monkeypatch.delenv("MINI_APP_URL", raising=False)
    message = _make_message()

    await cmd_site(message, db_path)

    args, kwargs = message.answer.call_args
    keyboard = kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 1


@pytest.mark.asyncio
async def test_site_pull_with_content_feeds_finish_and_sets_pending_media(db_path, monkeypatch):
    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, "Текст с сайта", "site-file-id", "/media/services/card_1.jpg")
    mock_generate = AsyncMock(return_value=["Сгенерированный вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    state = _make_state()
    callback = _make_callback(data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    mock_generate.assert_awaited()
    assert mock_generate.await_args_list[0].args[0] == "Текст с сайта"
    assert get_pending_media(db_path, TELEGRAM_ID) == ("site-file-id", "photo")
    assert get_daily_count(db_path, TELEGRAM_ID) == 1
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_site_pull_with_no_content_shows_empty_message(db_path):
    state = _make_state()
    callback = _make_callback(data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("site_pull_empty", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_site_pull_blocked_when_not_whitelisted(db_path):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_site_pull_blocked_when_daily_limit_exceeded(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "0")
    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, "Текст с сайта", None, None)
    state = _make_state()
    callback = _make_callback(data=f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}")

    await on_site_pull(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_daily_limit_exceeded", "ru"))


@pytest.mark.asyncio
async def test_site_push_stores_text_and_downloads_photo(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_MEDIA_DIR", str(tmp_path / "media"))
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await state.update_data(language="ru")
    callback = _make_callback(data="site:push:telegram:1")
    callback.message.text = "Готовый текст карточки"
    bot = AsyncMock()

    await on_site_push(callback, state, db_path, bot)

    bot.download.assert_awaited_once()
    content = get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK)
    assert content.text == "Готовый текст карточки"
    assert content.photo_file_id == "photo-file-id"
    assert content.photo_static_path == f"/media/{PILOT_PAGE}/{PILOT_BLOCK}.jpg"
    callback.message.answer.assert_awaited_once_with(get_string("site_push_success", "ru"))


@pytest.mark.asyncio
async def test_site_push_without_pending_media_keeps_existing_photo(db_path):
    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, "Старый текст", "old-file-id", "/media/services/card_1.jpg")
    state = _make_state()
    await state.update_data(language="ru")
    callback = _make_callback(data="site:push:telegram:1")
    callback.message.text = "Новый текст без фото"
    bot = AsyncMock()

    await on_site_push(callback, state, db_path, bot)

    bot.download.assert_not_awaited()
    content = get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK)
    assert content.text == "Новый текст без фото"
    assert content.photo_file_id == "old-file-id"
    assert content.photo_static_path == "/media/services/card_1.jpg"


@pytest.mark.asyncio
async def test_site_push_photo_download_failure_shows_friendly_error(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_MEDIA_DIR", str(tmp_path / "media"))
    set_pending_media(db_path, TELEGRAM_ID, "photo-file-id", "photo")
    state = _make_state()
    await state.update_data(language="ru")
    callback = _make_callback(data="site:push:telegram:1")
    callback.message.text = "Текст"
    bot = AsyncMock()
    bot.download = AsyncMock(side_effect=OSError("disk full"))

    await on_site_push(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("site_push_photo_failed", "ru"))
    assert get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK) is None


@pytest.mark.asyncio
async def test_site_push_blocked_when_not_whitelisted(db_path):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data="site:push:telegram:1")
    callback.message.text = "Текст"
    bot = AsyncMock()

    await on_site_push(callback, state, db_path, bot)

    bot.download.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    assert get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_site.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.site'`

- [ ] **Step 3: Write `bot/handlers/site.py`**

```python
# bot/handlers/site.py
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _finish, _resolve_language
from bot.handlers.refine import _check_limit_or_reply, _check_whitelist_or_reply
from bot.keyboards.site import PILOT_BLOCK, PILOT_PAGE, build_site_menu_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.media_cache import cache_photo
from bot.storage.limits import increment_usage
from bot.storage.site_content import get_site_content, upsert_site_content
from bot.storage.users import get_pending_media, set_pending_media

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="site")


@router.message(Command("site"))
async def cmd_site(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)
    settings = load_settings()

    await message.answer(
        get_string("site_menu_intro", language),
        reply_markup=build_site_menu_keyboard(settings.mini_app_url, language),
    )


@router.callback_query(F.data.startswith("site:pull:"))
async def on_site_pull(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return
    if not await _check_limit_or_reply(callback, db_path, language):
        return

    _, _, page, block_id = callback.data.split(":")
    content = get_site_content(db_path, page, block_id)

    if content is None or not content.text:
        await callback.message.answer(get_string("site_pull_empty", language))
        await callback.answer()
        return

    if content.photo_file_id:
        set_pending_media(db_path, telegram_id, content.photo_file_id, "photo")

    increment_usage(db_path, telegram_id)
    await _finish(callback.message, language, content.text, state, telegram_id, db_path)
    await callback.answer()


@router.callback_query(F.data.startswith("site:push:"))
async def on_site_push(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    variant_text = callback.message.text or ""
    pending_media = get_pending_media(db_path, telegram_id)
    existing = get_site_content(db_path, PILOT_PAGE, PILOT_BLOCK)

    photo_file_id = existing.photo_file_id if existing else None
    photo_static_path = existing.photo_static_path if existing else None

    if pending_media is not None:
        file_id, media_type = pending_media
        if media_type == "photo":
            settings = load_settings()
            try:
                photo_static_path = await cache_photo(
                    bot, file_id, settings.site_media_dir, PILOT_PAGE, PILOT_BLOCK
                )
            except (TelegramAPIError, OSError):
                logger.warning(
                    "Failed to cache photo for site push",
                    extra={"user_id": telegram_id, "operation": "site_push"},
                )
                await callback.message.answer(get_string("site_push_photo_failed", language))
                await callback.answer()
                return
            photo_file_id = file_id

    upsert_site_content(db_path, PILOT_PAGE, PILOT_BLOCK, variant_text, photo_file_id, photo_static_path)

    await callback.message.answer(get_string("site_push_success", language))
    await callback.answer()
```

- [ ] **Step 4: Register the router in `bot/main.py`**

Add the import near the other handler imports:

```python
from bot.handlers.site import router as site_router
```

In `build_dispatcher`, add the router **before** `content_router` (its catch-all `@router.message(StateFilter(None))` in `bot/handlers/content.py` would otherwise swallow `/site` as plain text — the same reason `channel_router` is already included before it):

```python
    dispatcher.include_router(channel_router)
    dispatcher.include_router(site_router)
    dispatcher.include_router(settov_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_handlers_site.py tests/test_handlers_channel.py tests/test_handlers_refine.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/site.py bot/main.py tests/test_handlers_site.py
git commit -m "feat: add /site command, pull and push handlers for site sync pilot"
```

---

### Task 7: Wire the site API server into the bot process

**Files:**
- Modify: `bot/main.py`

**Interfaces:**
- Consumes: `bot.services.site_api.build_site_api_app` (Task 4), `settings.site_api_host`, `settings.site_api_port`, `settings.site_media_dir` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_site_api_wiring.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_main_site_api_wiring.py -v`
Expected: FAIL with `AttributeError: <module 'bot.main'> does not have the attribute 'web'` (aiohttp not imported/used yet in `bot/main.py`)

- [ ] **Step 3: Update `bot/main.py`**

Add the import at the top (alongside the other imports):

```python
from aiohttp import web

from bot.services.site_api import build_site_api_app
```

Replace the body of `run()` (currently lines 49-72) with:

```python
async def run() -> None:
    settings = load_settings()
    logger = setup_logging(level=settings.log_level)
    init_db(settings.db_path)

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher(settings.daily_limit, settings.monthly_limit)

    site_api_app = build_site_api_app(settings.db_path, settings.site_media_dir)
    runner = web.AppRunner(site_api_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.site_api_host, settings.site_api_port)
    await site.start()

    logger.info("Бот запускается (long polling)")
    try:
        await dispatcher.start_polling(bot, db_path=settings.db_path)
    except Exception:
        # Process-level crash, distinct from per-request errors (which never
        # reach here — bot/handlers/errors.py catches those). Nothing left
        # to do for this request/process but log loudly, tell the owner,
        # and let it propagate so main() exits non-zero for systemd.
        logger.critical("Процесс бота аварийно завершается", exc_info=True)
        try:
            await notify_owner(bot, settings.owner_chat_id, _OWNER_CRASH_NOTICE)
        except Exception:
            logger.critical("Не удалось уведомить владельца о падении бота", exc_info=True)
        raise
    finally:
        await runner.cleanup()
        await bot.session.close()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_main_site_api_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (every test in `tests/`, no regressions)

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_main_site_api_wiring.py
git commit -m "feat: start the site content API alongside bot long polling"
```

---

### Task 8: `bot_site/` deliverable — one-time site-side script

**Files:**
- Create: `bot_site/site-content-loader.js`
- Create: `bot_site/README.md`

**Interfaces:** none (plain client-side JS, consumed by the separately-maintained `my-lending-test` repo, not by this codebase).

- [ ] **Step 1: Write the loader script**

```javascript
// bot_site/site-content-loader.js
//
// Разовый скрипт для services.html. Он ничего не меняет во внешнем виде
// страницы — только подставляет актуальные текст/фото карточки услуги,
// которые владелица заливает через Telegram-бота.
//
// Как подключить (один раз, вручную, в репозитории my-lending-test):
// 1. Добавьте id="pilot-card-text" на элемент с описанием карточки услуги
//    (например "Принятие тела") и id="pilot-card-photo" на её <img>.
// 2. Перед закрывающим </body> на services.html добавьте:
//    <script src="site-content-loader.js" data-api-base="https://147-45-175-189.sslip.io"></script>

(function () {
  var scriptTag = document.currentScript;
  var apiBase = scriptTag.getAttribute("data-api-base");
  if (!apiBase) {
    return;
  }

  fetch(apiBase + "/content/services/card_1")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("site content API returned " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      var textElement = document.getElementById("pilot-card-text");
      if (textElement && data.text) {
        textElement.textContent = data.text;
      }

      var photoElement = document.getElementById("pilot-card-photo");
      if (photoElement && data.photo_path) {
        photoElement.src = apiBase + data.photo_path;
      }
    })
    .catch(function () {
      // API недоступен или сервер лежит — страница остаётся со своим
      // исходным (зашитым в HTML) текстом/фото, как и раньше. Сайт не
      // должен зависеть от бота для базовой работоспособности.
    });
})();
```

- [ ] **Step 2: Write the instructions**

```markdown
# bot_site/README.md

# Разовая правка сайта для пилота

Этот файл нужно один раз вставить в **отдельный** репозиторий сайта
(`my-lending-test`), не в этот проект — этот бот и сайт остаются разными
проектами (см. `docs/superpowers/specs/2026-07-24-site-sync-pilot-design.md`).

## Что сделать в `services.html`

1. Найдите карточку услуги «Принятие тела» (первая карточка в разделе
   «Раскрытие женственности и сексуальности»).
2. На элементе с текстом описания карточки добавьте `id="pilot-card-text"`.
3. На картинке этой карточки (`<img>`) добавьте `id="pilot-card-photo"`.
4. Скопируйте файл `site-content-loader.js` в корень репозитория сайта
   (рядом с `services.html`).
5. Перед `</body>` в `services.html` добавьте:

   ```html
   <script src="site-content-loader.js" data-api-base="https://147-45-175-189.sslip.io"></script>
   ```

6. Закоммитьте и запушьте в репозиторий сайта — GitHub Pages пересоберёт
   страницу автоматически за 30-60 секунд.

## Как проверить

1. Откройте `https://olgashomrina.github.io/my-lending-test/services.html`
   в браузере.
2. В боте нажмите «Залить на сайт» после любого сгенерированного текста
   (с фото, чтобы проверить обе части).
3. Обновите страницу сайта — текст/фото карточки должны замениться на то,
   что вы залили из бота.

Если ничего не поменялось — откройте консоль разработчика в браузере
(F12 → Console/Network) и проверьте, что запрос к
`https://147-45-175-189.sslip.io/content/services/card_1` возвращает
`200 OK`, а не ошибку сети/CORS.
```

- [ ] **Step 3: Commit**

```bash
git add bot_site/site-content-loader.js bot_site/README.md
git commit -m "docs: add one-time site-side integration script and instructions"
```

---

### Task 9: Deploy docs — HTTPS for the site API (nginx + certbot + sslip.io)

**Files:**
- Modify: `deploy/README-deploy.md`

**Interfaces:** none (documentation + server commands, no code).

> **Note before running any command in this task on the real server:** these commands modify the production server (install packages, open a reverse proxy, request a public TLS certificate). Confirm with the owner before executing them there, same as any other production-infra change.

- [ ] **Step 1: Add a new section to `deploy/README-deploy.md`**

Append (after the existing systemd section):

```markdown
## Фаза 17: HTTPS для API сайта (пилот bot_site)

Бот теперь отдаёт содержимое карточки сайта через встроенный веб-сервер
(порт задаётся `SITE_API_PORT`, по умолчанию 8080). Сайт на GitHub Pages
работает по HTTPS и не сможет обратиться к обычному `http://IP:порт`
(браузеры блокируют это как "mixed content") — поэтому перед этим сервером
нужен `nginx` с бесплатным сертификатом Let's Encrypt.

Своего домена нет — используем бесплатный адрес вида
`147-45-175-189.sslip.io` (вместо `147-45-175-189` подставьте реальный IP
сервера через дефис) — он автоматически резолвится на сервер по IP.

Выполните на сервере (через SSH):

```bash
sudo apt install -y nginx certbot python3-certbot-nginx

sudo tee /etc/nginx/sites-available/content-bot-site-api > /dev/null <<'NGINX'
server {
    listen 80;
    server_name 147-45-175-189.sslip.io;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
}
NGINX

sudo ln -s /etc/nginx/sites-available/content-bot-site-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d 147-45-175-189.sslip.io
```

`certbot` спросит email (для уведомлений об истечении сертификата) и
согласие с условиями — сертификат обновляется автоматически, ничего больше
делать не нужно.

Проверка: `curl https://147-45-175-189.sslip.io/content/services/card_1`
должен ответить `{"error": "not_found"}` (или реальным содержимым, если
уже что-то залито через бота) без ошибок сертификата.

Значение `147-45-175-189.sslip.io` (со своим реальным IP) впишите в
`data-api-base` в `bot_site/site-content-loader.js` при подключении на
сайте (см. `bot_site/README.md`).
```

- [ ] **Step 2: Commit**

```bash
git add deploy/README-deploy.md
git commit -m "docs: add nginx/certbot/sslip.io HTTPS setup for site content API"
```

---

### Task 10: Full suite run and manual verification checklist

**Files:** none modified — verification only.

- [ ] **Step 1: Run the complete automated test suite**

Run: `pytest -v`
Expected: PASS — every test file, including all ones added in Tasks 1-7, plus every pre-existing test (`test_handlers_refine.py`, `test_handlers_channel.py`, `test_handlers_start.py`, `test_localization.py`, etc.) unchanged and still green.

- [ ] **Step 2: Manual verification checklist (requires the real production server and a real Telegram account — not automatable)**

Write this checklist into the chat/handoff doc for the owner, do not skip it:

1. Deploy this branch to production (existing CI/CD from Phase 16 handles this on push).
2. Complete Task 9's nginx/certbot setup on the server if not already done.
3. Complete Task 8's one-time edit in the separate `my-lending-test` repo (add the two `id`s + the `<script>` tag to `services.html`, push it).
4. In the bot: generate any post, attach a photo, press "Залить на сайт" — expect the "Готово! Карточка на сайте обновлена." confirmation.
5. Open `https://olgashomrina.github.io/my-lending-test/services.html` in a normal browser (not the Telegram Mini App) and confirm the "Принятие тела" card now shows the text/photo just pushed.
6. In the bot, use `/site` → "Забрать карточку «Услуги»" — expect the bot to reply with freshly AI-generated variants derived from that same text (this reuses the existing content-generation pipeline, per `bot/handlers/content.py::_finish`).
7. In the bot, use `/site` → "МОЙ САЙТ" — expect Telegram to open the live site in-app (Mini App), not a system browser.
8. Confirm quota: repeat step 6 until `DAILY_LIMIT` is exhausted, expect the existing daily-limit error message rather than an unlimited free pull.

- [ ] **Step 3: Report results to the owner**

Summarize pass/fail for each checklist item above in plain Russian, and stop here — no further phases are in scope for this pilot until the owner reviews the live result and decides whether to extend to more pages/cards.
