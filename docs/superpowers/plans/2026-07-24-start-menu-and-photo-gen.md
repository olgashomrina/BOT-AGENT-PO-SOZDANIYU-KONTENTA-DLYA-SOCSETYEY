# Постоянное меню бота + отдельная генерация фото — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a persistent bottom "Старт" button that always re-shows the main menu regardless of chat history, a two-level inline menu (Я умею / Создать пост сейчас → МОЙ САЙТ / Генерация текста / Генерация фото), and a new standalone "generate an image from a description" flow that feeds into the bot's existing publish pipeline.

**Architecture:** Pure additive extension of `bot/handlers/start.py` and a new `bot/keyboards/start.py` — no new storage tables, no new services, no changes to `bot/main.py`'s router order (`start_router` already runs before `content_router`). The standalone photo flow reuses the exact same `content_generator.generate_image_prompt` / `ai_gateway.generate_image` / `set_pending_media` machinery `on_refine_image` (`bot/handlers/refine.py`) already uses — it only changes where the image *prompt* comes from (a fresh user description instead of an already-generated post's text).

**Tech Stack:** Python, aiogram 3.29 (existing) — `ReplyKeyboardMarkup`/`KeyboardButton` (not used anywhere in this codebase yet, but a normal part of aiogram's `aiogram.types`) for the persistent button, `InlineKeyboardMarkup` (already used everywhere) for the menus.

## Global Constraints

- Every new user-facing string must exist in all 4 locale files (`bot/locales/ru.py`, `en.py`, `vi.py`, `zh.py`) — enforced by `tests/test_localization.py::test_all_locales_have_identical_keys`.
- Reuse existing AI-error handling exactly: `_AI_ERROR_KEYS` (from `bot/handlers/content.py`), `content_generator.generate_image_prompt`, `ai_gateway.generate_image`, `set_pending_media` (from `bot/storage/users.py`) — do not duplicate this logic.
- Every new `callback_query` handler must explicitly call `_check_whitelist_or_reply` (imported from `bot/handlers/refine.py`, the established cross-module pattern already used by `bot/handlers/site.py`) — `WhitelistMiddleware` only runs on `message` events, never on `callback_query` (see the WHY comment at `bot/handlers/refine.py:39-45`).
- New `message`-triggered handlers (the persistent-button text handler, the photo-description handler) need **no** manual whitelist or quota check — `WhitelistMiddleware` and `RateLimitMiddleware` already run on every `message` event automatically, unlike `callback_query` events.
- No changes to `bot/main.py` are needed or in scope — `start_router` is already registered before `content_router` in `build_dispatcher`, so the new state-bound and command-bound handlers in `start.py` need no reordering.
- VK auto-publish is explicitly out of scope for this plan (separate future project, needs VK OAuth app registration first).

---

### Task 1: Locale strings

**Files:**
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`

**Interfaces:** none (pure data) — consumed via `bot.locales.loader.get_string` by Tasks 2-5.

- [ ] **Step 1: Update `bot/locales/ru.py`**

Replace the existing `start_greeting` value with:

```python
    "start_greeting": (
        "Привет! Я бот-помощник для создания контента в соцсетях и для "
        "вашего личного сайта — пишу в вашем уникальном авторском стиле, "
        "на русском, английском, китайском и вьетнамском.\n\n"
        "Пришлите мне ссылку на статью, голосовое сообщение, текст или "
        "опишите, какую картинку хотите — и я подготовлю готовые варианты "
        "поста для Telegram и VK.\n\n"
        "Чтобы сменить язык интерфейса, используйте команду /language."
    ),
```

Replace the existing `onboarding_capabilities` value with:

```python
    "onboarding_capabilities": (
        "Что я умею:\n\n"
        "— Принимаю ссылку на статью, голосовое сообщение или просто "
        "текст — и готовлю несколько вариантов поста отдельно для "
        "Telegram и для VK, напишу текст Вашим индивидуальным авторским "
        "стилем.\n"
        "— Пишу на русском, английском, китайском и вьетнамском.\n"
        "— Могу сгенерировать картинку по вашему описанию — отдельно или "
        "как дополнение к посту.\n"
        "— Умею публиковать пост прямо в ваш Telegram-канал одной кнопкой "
        "(команда /channel).\n"
        "— Забираю и обновляю карточку услуг на вашем личном сайте прямо "
        "из чата (команда /site).\n\n"
        "Команды: /start — начать заново, /language — сменить язык "
        "интерфейса, /channel — настроить канал, /site — работа с "
        "сайтом, /clear_media — убрать прикреплённое медиа, /settov — "
        "научить бота вашему стилю, /help — показать это сообщение "
        "снова."
    ),
```

Add these 9 new keys (anywhere convenient, e.g. right after `onboarding_quick_start`):

```python
    "start_button_label": "Старт",
    "menu_intro": "Что делаем дальше?",
    "menu_capabilities_button": "Я умею",
    "menu_cta_button": "Создать пост сейчас",
    "menu_text_generation_button": "Генерация текста",
    "menu_text_generation_hint": (
        "Пришлите ссылку на статью, голосовое сообщение или текст — "
        "подготовлю варианты постов для Telegram и VK."
    ),
    "menu_photo_generation_button": "Генерация фото",
    "photo_gen_prompt": (
        "Опишите, какую картинку вы хотите — я сгенерирую её через ИИ."
    ),
    "photo_gen_ready": (
        "Картинка готова! Теперь пришлите текст, ссылку на статью или "
        "голосовое — подготовлю пост с этой картинкой."
    ),
```

- [ ] **Step 2: Update `bot/locales/en.py`**

Replace `start_greeting`:

```python
    "start_greeting": (
        "Hi! I'm a bot assistant for creating social media content and "
        "for your personal website — I write in your own unique style, "
        "in Russian, English, Chinese, and Vietnamese.\n\n"
        "Send me a link to an article, a voice message, text, or "
        "describe the image you want — and I'll prepare ready-to-use "
        "post variants for Telegram and VK.\n\n"
        "To change the interface language, use the /language command."
    ),
```

Replace `onboarding_capabilities`:

```python
    "onboarding_capabilities": (
        "What I can do:\n\n"
        "— Accept a link to an article, a voice message, or plain "
        "text — and prepare several post variants, separately for "
        "Telegram and for VK, written in your own individual style.\n"
        "— Write in Russian, English, Chinese, and Vietnamese.\n"
        "— Generate an image from your description — on its own or as "
        "an addition to a post.\n"
        "— Publish a post straight to your Telegram channel with one "
        "button (the /channel command).\n"
        "— Pull and update the services card on your personal website "
        "right from the chat (the /site command).\n\n"
        "Commands: /start — start over, /language — change interface "
        "language, /channel — set up a channel, /site — work with the "
        "website, /clear_media — remove the attached media, /settov — "
        "teach the bot your writing style, /help — show this message "
        "again."
    ),
```

Add the 9 new keys:

```python
    "start_button_label": "Start",
    "menu_intro": "What shall we do next?",
    "menu_capabilities_button": "What I can do",
    "menu_cta_button": "Create a post now",
    "menu_text_generation_button": "Text generation",
    "menu_text_generation_hint": (
        "Send me a link to an article, a voice message, or text — "
        "I'll prepare post variants for Telegram and VK."
    ),
    "menu_photo_generation_button": "Photo generation",
    "photo_gen_prompt": "Describe the image you want — I'll generate it using AI.",
    "photo_gen_ready": (
        "The image is ready! Now send me text, a link to an article, "
        "or a voice message — I'll prepare a post with this image."
    ),
```

- [ ] **Step 3: Update `bot/locales/vi.py`**

Replace `start_greeting`:

```python
    "start_greeting": (
        "Xin chào! Tôi là bot trợ lý tạo nội dung cho mạng xã hội và cho "
        "trang web cá nhân của bạn — tôi viết theo phong cách riêng độc "
        "đáo của bạn, bằng tiếng Nga, tiếng Anh, tiếng Trung và tiếng "
        "Việt.\n\n"
        "Hãy gửi cho tôi đường liên kết đến bài viết, tin nhắn thoại, "
        "văn bản, hoặc mô tả hình ảnh bạn muốn — tôi sẽ chuẩn bị các "
        "phương án bài đăng sẵn sàng sử dụng cho Telegram và VK.\n\n"
        "Để đổi ngôn ngữ giao diện, hãy dùng lệnh /language."
    ),
```

Replace `onboarding_capabilities`:

```python
    "onboarding_capabilities": (
        "Tôi có thể làm gì:\n\n"
        "— Nhận đường liên kết bài viết, tin nhắn thoại, hoặc văn bản "
        "thường — và chuẩn bị nhiều phương án bài đăng, riêng cho "
        "Telegram và riêng cho VK, viết theo phong cách riêng của "
        "bạn.\n"
        "— Viết bằng tiếng Nga, tiếng Anh, tiếng Trung và tiếng Việt.\n"
        "— Có thể tạo hình ảnh theo mô tả của bạn — riêng lẻ hoặc bổ "
        "sung cho bài đăng.\n"
        "— Đăng bài trực tiếp vào kênh Telegram của bạn chỉ bằng một "
        "nút bấm (lệnh /channel).\n"
        "— Lấy và cập nhật thẻ dịch vụ trên trang web cá nhân của bạn "
        "ngay trong chat (lệnh /site).\n\n"
        "Các lệnh: /start — bắt đầu lại, /language — đổi ngôn ngữ giao "
        "diện, /channel — thiết lập kênh, /site — làm việc với trang "
        "web, /clear_media — bỏ tệp đính kèm, /settov — dạy bot phong "
        "cách viết của bạn, /help — hiển thị lại tin nhắn này."
    ),
```

Add the 9 new keys:

```python
    "start_button_label": "Bắt đầu",
    "menu_intro": "Tiếp theo chúng ta làm gì?",
    "menu_capabilities_button": "Tôi có thể làm gì",
    "menu_cta_button": "Tạo bài đăng ngay",
    "menu_text_generation_button": "Tạo văn bản",
    "menu_text_generation_hint": (
        "Hãy gửi cho tôi đường liên kết bài viết, tin nhắn thoại, hoặc "
        "văn bản — tôi sẽ chuẩn bị các phương án bài đăng cho Telegram "
        "và VK."
    ),
    "menu_photo_generation_button": "Tạo ảnh",
    "photo_gen_prompt": "Hãy mô tả hình ảnh bạn muốn — tôi sẽ tạo nó bằng AI.",
    "photo_gen_ready": (
        "Hình ảnh đã sẵn sàng! Bây giờ hãy gửi văn bản, đường liên kết "
        "bài viết, hoặc tin nhắn thoại — tôi sẽ chuẩn bị bài đăng kèm "
        "hình ảnh này."
    ),
```

- [ ] **Step 4: Update `bot/locales/zh.py`**

Replace `start_greeting`:

```python
    "start_greeting": (
        "你好！我是帮你创作社交媒体内容和个人网站内容的机器人助手——我会用您"
        "独特的个人风格写作，支持俄语、英语、中文和越南语。\n\n"
        "给我发送一个文章链接、一条语音消息、文字，或描述您想要的图片——我会"
        "为 Telegram 和 VK 准备好可直接使用的帖子方案。\n\n"
        "如需更改界面语言，请使用 /language 命令。"
    ),
```

Replace `onboarding_capabilities`:

```python
    "onboarding_capabilities": (
        "我能做什么：\n\n"
        "——接收文章链接、语音消息或直接发送的文字——并分别为 Telegram 和 "
        "VK 准备好几个帖子方案，用您独特的个人风格写作。\n"
        "——支持俄语、英语、中文和越南语写作。\n"
        "——可以根据您的描述生成图片——单独使用，或作为帖子的补充。\n"
        "——一键将帖子直接发布到您的 Telegram 频道（/channel 命令）。\n"
        "——直接在聊天中获取并更新您个人网站上的服务卡片（/site 命令）。\n\n"
        "命令列表：/start — 重新开始，/language — 切换界面语言，"
        "/channel — 设置频道，/site — 网站相关操作，/clear_media — 移除"
        "已附加的媒体，/settov — 让机器人学习您的写作风格，/help — 再次"
        "显示此消息。"
    ),
```

Add the 9 new keys:

```python
    "start_button_label": "开始",
    "menu_intro": "接下来做什么？",
    "menu_capabilities_button": "我能做什么",
    "menu_cta_button": "立即创建帖子",
    "menu_text_generation_button": "生成文字",
    "menu_text_generation_hint": (
        "给我发送文章链接、语音消息或文字——我会为 Telegram 和 VK 准备好"
        "帖子方案。"
    ),
    "menu_photo_generation_button": "生成图片",
    "photo_gen_prompt": "请描述您想要的图片——我会用 AI 生成它。",
    "photo_gen_ready": (
        "图片已生成！现在请发送文字、文章链接或语音消息——我会为您准备带有"
        "这张图片的帖子。"
    ),
```

- [ ] **Step 5: Run the localization parity test**

Run: `pytest tests/test_localization.py -v`
Expected: PASS (all 4 locale files have identical key sets again — 61 keys each: 52 existing + 9 new)

- [ ] **Step 6: Run existing start/help tests to confirm nothing broke yet**

Run: `pytest tests/test_handlers_start.py -v`
Expected: PASS unchanged — these tests call `get_string(key, lang)` dynamically for their assertions, never a hardcoded copy of the string content, so updating `start_greeting`/`onboarding_capabilities` text does not affect them. (Task 3 is the task that will actually change their message-count/reply_markup expectations, not this one.)

- [ ] **Step 7: Commit**

```bash
git add bot/locales/ru.py bot/locales/en.py bot/locales/vi.py bot/locales/zh.py
git commit -m "feat: update greeting/capabilities copy and add start-menu locale strings"
```

---

### Task 2: Keyboards module

**Files:**
- Create: `bot/keyboards/start.py`
- Test: `tests/test_keyboards_start.py`

**Interfaces:**
- Consumes: `bot.locales.loader.get_string` (Task 1's new keys); `bot.keyboards.site`'s established pattern for a conditional `WebAppInfo` button (same idea, not imported — this module builds its own).
- Produces: `build_persistent_start_keyboard(lang: str) -> ReplyKeyboardMarkup`, `build_start_menu_keyboard(lang: str) -> InlineKeyboardMarkup`, `build_create_post_keyboard(mini_app_url: str, lang: str) -> InlineKeyboardMarkup`, and callback-data constants `CALLBACK_CAPABILITIES = "menu:capabilities"`, `CALLBACK_CREATE_POST = "menu:create_post"`, `CALLBACK_TEXT_HINT = "menu:text_hint"`, `CALLBACK_PHOTO_GEN = "menu:photo_gen"` — all consumed by Tasks 3-5.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_keyboards_start.py
from __future__ import annotations

from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_PHOTO_GEN,
    CALLBACK_TEXT_HINT,
    build_create_post_keyboard,
    build_persistent_start_keyboard,
    build_start_menu_keyboard,
)
from bot.locales.loader import get_string


def test_persistent_start_keyboard_has_one_resizable_button():
    keyboard = build_persistent_start_keyboard("ru")

    assert keyboard.resize_keyboard is True
    assert len(keyboard.keyboard) == 1
    assert len(keyboard.keyboard[0]) == 1
    assert keyboard.keyboard[0][0].text == get_string("start_button_label", "ru")


def test_start_menu_keyboard_has_capabilities_and_cta_buttons():
    keyboard = build_start_menu_keyboard("en")

    assert keyboard.inline_keyboard[0][0].text == get_string("menu_capabilities_button", "en")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_CAPABILITIES
    assert keyboard.inline_keyboard[1][0].text == get_string("menu_cta_button", "en")
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_CREATE_POST


def test_create_post_keyboard_includes_site_button_when_url_set():
    keyboard = build_create_post_keyboard("https://olgashomrina.github.io/my-lending-test/", "ru")

    first_row = keyboard.inline_keyboard[0]
    assert first_row[0].text == get_string("open_site_button", "ru")
    assert first_row[0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


def test_create_post_keyboard_omits_site_button_when_url_missing():
    keyboard = build_create_post_keyboard("", "ru")

    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_TEXT_HINT
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_PHOTO_GEN


def test_create_post_keyboard_text_and_photo_buttons():
    keyboard = build_create_post_keyboard("https://example.com/", "vi")

    text_button = keyboard.inline_keyboard[-2][0]
    photo_button = keyboard.inline_keyboard[-1][0]
    assert text_button.text == get_string("menu_text_generation_button", "vi")
    assert text_button.callback_data == CALLBACK_TEXT_HINT
    assert photo_button.text == get_string("menu_photo_generation_button", "vi")
    assert photo_button.callback_data == CALLBACK_PHOTO_GEN
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_keyboards_start.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.keyboards.start'`

- [ ] **Step 3: Write `bot/keyboards/start.py`**

```python
# bot/keyboards/start.py
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot.locales.loader import get_string

CALLBACK_CAPABILITIES = "menu:capabilities"
CALLBACK_CREATE_POST = "menu:create_post"
CALLBACK_TEXT_HINT = "menu:text_hint"
CALLBACK_PHOTO_GEN = "menu:photo_gen"


def build_persistent_start_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_string("start_button_label", lang))]],
        resize_keyboard=True,
    )


def build_start_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("menu_capabilities_button", lang),
                    callback_data=CALLBACK_CAPABILITIES,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("menu_cta_button", lang),
                    callback_data=CALLBACK_CREATE_POST,
                )
            ],
        ]
    )


def build_create_post_keyboard(mini_app_url: str, lang: str) -> InlineKeyboardMarkup:
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
                text=get_string("menu_text_generation_button", lang),
                callback_data=CALLBACK_TEXT_HINT,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("menu_photo_generation_button", lang),
                callback_data=CALLBACK_PHOTO_GEN,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_start.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/keyboards/start.py tests/test_keyboards_start.py
git commit -m "feat: add persistent start keyboard and two-level menu keyboards"
```

---

### Task 3: Wire the persistent keyboard and menu into `/start`

**Files:**
- Modify: `bot/handlers/start.py`
- Modify: `tests/test_handlers_start.py` (existing assertions change — see below)

**Interfaces:**
- Consumes: `bot.keyboards.start.build_persistent_start_keyboard`, `build_start_menu_keyboard` (Task 2).
- Produces: `_START_BUTTON_LABELS` (module-level frozenset, internal), `cmd_start` now also registered for the persistent-button text — no new public interface consumed by later tasks (Tasks 4-5 add their own handlers to the same file/router).

**Why the existing tests must change (read before starting):** `cmd_start` currently sends 1 message for a returning user (just `start_greeting`) and 4 for a new user (`start_greeting` + 3 onboarding messages). After this task it sends 2 messages for a returning user (`start_greeting` **with** `reply_markup=<persistent keyboard>`, then `menu_intro` **with** `reply_markup=<inline menu>`) and 5 for a new user (those same 2, then the unchanged 3-message onboarding sequence). The existing assertions in `tests/test_handlers_start.py` check exact `call(text)` shapes with no `reply_markup` and exact counts — both now need updating, not just new tests added.

- [ ] **Step 1: Write the failing tests (full replacement of `tests/test_handlers_start.py`)**

```python
# tests/test_handlers_start.py
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, call

import pytest

from bot.handlers.start import cmd_help, cmd_start
from bot.locales.loader import get_string
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
)


def _make_message(telegram_id: int, language_code: str | None, text: str | None = "/start"):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    message.text = text
    return message


def _greeting_calls(language: str):
    return [
        call(get_string("start_greeting", language), reply_markup=ANY),
        call(get_string("menu_intro", language), reply_markup=ANY),
    ]


def _onboarding_calls(language: str):
    return [
        call(get_string("onboarding_capabilities", language)),
        call(get_string("onboarding_settov", language)),
        call(get_string("onboarding_quick_start", language)),
    ]


@pytest.mark.asyncio
async def test_new_user_gets_language_from_supported_language_code(db_path):
    message = _make_message(111, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 111) == "vi"
    message.answer.assert_has_calls([*_greeting_calls("vi"), *_onboarding_calls("vi")])


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_for_unsupported_language_code(db_path):
    message = _make_message(222, "fr")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 222) == "ru"
    message.answer.assert_has_calls([*_greeting_calls("ru"), *_onboarding_calls("ru")])


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_when_language_code_missing(db_path):
    message = _make_message(333, None)

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 333) == "ru"


@pytest.mark.asyncio
async def test_new_user_sees_greeting_menu_and_all_three_onboarding_messages(db_path):
    message = _make_message(777, "ru")

    await cmd_start(message, db_path)

    assert message.answer.await_count == 5
    message.answer.assert_has_calls([*_greeting_calls("ru"), *_onboarding_calls("ru")])


@pytest.mark.asyncio
async def test_new_user_start_persists_onboarding_shown_flag(db_path):
    message = _make_message(888, "ru")

    await cmd_start(message, db_path)

    assert get_onboarding_shown(db_path, 888) is True


@pytest.mark.asyncio
async def test_second_start_from_same_new_user_does_not_repeat_onboarding(db_path):
    message = _make_message(999, "ru")

    await cmd_start(message, db_path)
    message.answer.reset_mock()
    await cmd_start(message, db_path)

    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("ru"))


@pytest.mark.asyncio
async def test_returning_user_start_shows_greeting_and_menu_only(db_path):
    set_interface_language(db_path, 444, "en")
    set_onboarding_shown(db_path, 444, True)
    message = _make_message(444, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 444) == "en"
    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("en"))


@pytest.mark.asyncio
async def test_persistent_start_button_text_triggers_same_flow_as_command(db_path):
    set_interface_language(db_path, 1010, "ru")
    set_onboarding_shown(db_path, 1010, True)
    message = _make_message(1010, "ru", text=get_string("start_button_label", "ru"))

    await cmd_start(message, db_path)

    assert message.answer.await_count == 2
    message.answer.assert_has_calls(_greeting_calls("ru"))


@pytest.mark.asyncio
async def test_help_shows_onboarding_for_new_user(db_path):
    message = _make_message(555, "ru")

    await cmd_help(message, db_path)

    assert message.answer.await_count == 3
    message.answer.assert_has_calls(_onboarding_calls("ru"))


@pytest.mark.asyncio
async def test_help_shows_onboarding_again_for_user_who_already_saw_it(db_path):
    set_interface_language(db_path, 666, "zh")
    set_onboarding_shown(db_path, 666, True)
    message = _make_message(666, "en")

    await cmd_help(message, db_path)

    assert message.answer.await_count == 3
    message.answer.assert_has_calls(_onboarding_calls("zh"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_start.py -v`
Expected: FAIL — the new/changed assertions (await_count, `reply_markup=ANY`, the new persistent-button test) don't match current `cmd_start` behavior yet.

- [ ] **Step 3: Update `bot/handlers/start.py`**

Replace the file's imports and `cmd_start` with:

```python
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.keyboards.start import build_persistent_start_keyboard, build_start_menu_keyboard
from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
)

router = Router(name="start")

_START_BUTTON_LABELS = frozenset(
    get_string("start_button_label", lang) for lang in SUPPORTED_LANGUAGES
)


async def _send_onboarding(message: Message, language: str) -> None:
    await message.answer(get_string("onboarding_capabilities", language))
    await message.answer(get_string("onboarding_settov", language))
    await message.answer(get_string("onboarding_quick_start", language))


@router.message(CommandStart())
@router.message(F.text.in_(_START_BUTTON_LABELS))
async def cmd_start(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        set_interface_language(db_path, telegram_id, language)

    await message.answer(
        get_string("start_greeting", language),
        reply_markup=build_persistent_start_keyboard(language),
    )
    await message.answer(
        get_string("menu_intro", language),
        reply_markup=build_start_menu_keyboard(language),
    )

    if not get_onboarding_shown(db_path, telegram_id):
        await _send_onboarding(message, language)
        set_onboarding_shown(db_path, telegram_id, True)


@router.message(Command("help"))
async def cmd_help(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    await _send_onboarding(message, language)
```

(Tasks 4 and 5 append more imports and handlers below `cmd_help` in this same file — do not remove `cmd_help` or reorder the file beyond what's shown here.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_start.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full suite to confirm no other regressions**

Run: `pytest -v`
Expected: PASS — no other test file references `cmd_start`'s message shape.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/start.py tests/test_handlers_start.py
git commit -m "feat: attach persistent start keyboard and inline menu to /start"
```

---

### Task 4: "Создать пост сейчас" submenu callbacks

**Files:**
- Modify: `bot/handlers/start.py`
- Modify: `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: `bot.handlers.content._resolve_language` (existing cross-module import, same pattern as `bot/handlers/refine.py:11`), `bot.handlers.refine._check_whitelist_or_reply`, `bot.keyboards.start.build_create_post_keyboard`, `bot.config.load_settings`.
- Produces: three new callback handlers on the existing `start` router — no new interface consumed by Task 5 (Task 5 adds its own callback + state independently).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handlers_start.py`:

```python
from bot.handlers.start import on_menu_capabilities, on_menu_create_post, on_menu_text_hint
from bot.keyboards.start import CALLBACK_CAPABILITIES, CALLBACK_CREATE_POST, CALLBACK_TEXT_HINT
from bot.storage.whitelist import add_user


def _make_callback(telegram_id: int, data: str, language_code: str = "ru"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_menu_capabilities_sends_onboarding_capabilities_text(db_path):
    add_user(db_path, 2001)
    callback = _make_callback(2001, CALLBACK_CAPABILITIES)

    await on_menu_capabilities(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("onboarding_capabilities", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_capabilities_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2002, CALLBACK_CAPABILITIES)

    await on_menu_capabilities(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_menu_create_post_shows_submenu_keyboard(db_path, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    add_user(db_path, 2003)
    callback = _make_callback(2003, CALLBACK_CREATE_POST)

    await on_menu_create_post(callback, db_path)

    callback.message.answer.assert_awaited_once()
    _, kwargs = callback.message.answer.call_args
    assert "reply_markup" in kwargs
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_create_post_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2004, CALLBACK_CREATE_POST)

    await on_menu_create_post(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_menu_text_hint_sends_hint_text(db_path):
    add_user(db_path, 2005)
    callback = _make_callback(2005, CALLBACK_TEXT_HINT)

    await on_menu_text_hint(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("menu_text_generation_hint", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_text_hint_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2006, CALLBACK_TEXT_HINT)

    await on_menu_text_hint(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_start.py -v`
Expected: FAIL with `ImportError: cannot import name 'on_menu_capabilities'` (and similar for the other two)

- [ ] **Step 3: Append to `bot/handlers/start.py`**

Add these imports (merge into the existing import block at the top of the file):

```python
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.handlers.refine import _check_whitelist_or_reply
from bot.keyboards.start import build_create_post_keyboard
```

(Note: `Message` was already imported in Task 3's version of the file — just add `CallbackQuery` to that same `aiogram.types` import line rather than duplicating it.)

Append these three handlers at the end of the file (after `cmd_help`):

```python
@router.callback_query(F.data == CALLBACK_CAPABILITIES)
async def on_menu_capabilities(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await callback.message.answer(get_string("onboarding_capabilities", language))
    await callback.answer()


@router.callback_query(F.data == CALLBACK_CREATE_POST)
async def on_menu_create_post(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    settings = load_settings()
    await callback.message.answer(
        get_string("menu_cta_button", language),
        reply_markup=build_create_post_keyboard(settings.mini_app_url, language),
    )
    await callback.answer()


@router.callback_query(F.data == CALLBACK_TEXT_HINT)
async def on_menu_text_hint(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await callback.message.answer(get_string("menu_text_generation_hint", language))
    await callback.answer()
```

Also add the two callback-data imports needed at the top of the file (merge into the `bot.keyboards.start` import):

```python
from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_TEXT_HINT,
    build_create_post_keyboard,
    build_persistent_start_keyboard,
    build_start_menu_keyboard,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_start.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/start.py tests/test_handlers_start.py
git commit -m "feat: add 'Создать пост сейчас' submenu callbacks"
```

---

### Task 5: Standalone photo generation from a description

**Files:**
- Modify: `bot/handlers/start.py`
- Modify: `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: `bot.handlers.content._AI_ERROR_KEYS`, `bot.services.content_generator.generate_image_prompt`, `bot.services.ai_gateway.generate_image`, `bot.storage.users.set_pending_media`, `bot.keyboards.start.CALLBACK_PHOTO_GEN`.
- Produces: `PhotoGenStates` (`StatesGroup`), consumed only within this task/file.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handlers_start.py`:

```python
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.start import PhotoGenStates, on_menu_photo_gen, on_photo_gen_description
from bot.keyboards.start import CALLBACK_PHOTO_GEN
from bot.services import ai_gateway, content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.users import get_pending_media


def _make_state(telegram_id: int) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_description_message(telegram_id: int, text: str, language_code: str = "ru"):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    message.text = text
    message.chat = SimpleNamespace(id=telegram_id)
    return message


def _fake_sent_photo_message(file_id: str = "telegram-cdn-file-id"):
    return SimpleNamespace(photo=[SimpleNamespace(file_id=file_id)])


@pytest.mark.asyncio
async def test_menu_photo_gen_prompts_for_description_and_sets_state(db_path):
    add_user(db_path, 3001)
    state = _make_state(3001)
    callback = _make_callback(3001, CALLBACK_PHOTO_GEN)

    await on_menu_photo_gen(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("photo_gen_prompt", "ru"))
    assert await state.get_state() == PhotoGenStates.waiting_for_description.state
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_photo_gen_blocked_when_not_whitelisted(db_path):
    state = _make_state(3002)
    callback = _make_callback(3002, CALLBACK_PHOTO_GEN)

    await on_menu_photo_gen(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_photo_gen_description_generates_and_attaches_image(db_path, monkeypatch):
    add_user(db_path, 3003)
    state = _make_state(3003)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock(return_value="a vivid english prompt")
    mock_generate_image = AsyncMock(return_value="https://vendor.example/generated.png")
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)
    monkeypatch.setattr(ai_gateway, "generate_image", mock_generate_image)

    message = _make_description_message(3003, "закат над морем, тёплые тона")
    bot = AsyncMock()
    bot.send_photo = AsyncMock(return_value=_fake_sent_photo_message("telegram-cdn-file-id"))

    await on_photo_gen_description(message, state, db_path, bot)

    mock_prompt.assert_awaited_once_with("закат над морем, тёплые тона")
    mock_generate_image.assert_awaited_once_with("a vivid english prompt")
    bot.send_photo.assert_awaited_once()
    args, kwargs = bot.send_photo.call_args
    assert args[0] == 3003
    assert kwargs["photo"] == "https://vendor.example/generated.png"
    assert get_pending_media(db_path, 3003) == ("telegram-cdn-file-id", "photo")
    assert await state.get_state() is None
    message.answer.assert_awaited_once_with(get_string("photo_gen_ready", "ru"))


@pytest.mark.asyncio
async def test_photo_gen_description_empty_text_reprompts_without_calling_ai(db_path, monkeypatch):
    state = _make_state(3004)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock()
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)

    message = _make_description_message(3004, None)
    bot = AsyncMock()

    await on_photo_gen_description(message, state, db_path, bot)

    mock_prompt.assert_not_awaited()
    message.answer.assert_awaited_once_with(get_string("photo_gen_prompt", "ru"))
    assert await state.get_state() == PhotoGenStates.waiting_for_description.state


@pytest.mark.asyncio
async def test_photo_gen_description_ai_error_replies_friendly_message(db_path, monkeypatch):
    state = _make_state(3005)
    await state.update_data(language="ru")
    await state.set_state(PhotoGenStates.waiting_for_description)

    mock_prompt = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(content_generator, "generate_image_prompt", mock_prompt)

    message = _make_description_message(3005, "закат")
    bot = AsyncMock()

    await on_photo_gen_description(message, state, db_path, bot)

    message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    assert get_pending_media(db_path, 3005) is None
    assert await state.get_state() == PhotoGenStates.waiting_for_description.state
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_start.py -v`
Expected: FAIL with `ImportError: cannot import name 'PhotoGenStates'`

- [ ] **Step 3: Append to `bot/handlers/start.py`**

Add these imports (merge into the existing import block):

```python
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.handlers.content import _AI_ERROR_KEYS
from bot.keyboards.start import CALLBACK_PHOTO_GEN
from bot.logging_config import LOGGER_NAME
from bot.services import ai_gateway, content_generator
from bot.services.ai_gateway import AIGatewayError
from bot.storage.users import set_pending_media
```

(`_resolve_language` and `_AI_ERROR_KEYS` both come from `bot.handlers.content` — merge into the single existing import line from Task 4 rather than adding a second one: `from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language`. Same for `bot.keyboards.start` — merge `CALLBACK_PHOTO_GEN` into Task 4's existing import from that module. Same for `Bot` — merge into Task 3's existing `from aiogram import F, Router` line to become `from aiogram import Bot, F, Router`, rather than adding a second `from aiogram import ...` line.)

Add the module-level logger and states class (near the top, after `router = Router(name="start")`):

```python
logger = logging.getLogger(LOGGER_NAME)


class PhotoGenStates(StatesGroup):
    waiting_for_description = State()
```

Append these two handlers at the end of the file:

```python
@router.callback_query(F.data == CALLBACK_PHOTO_GEN)
async def on_menu_photo_gen(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await state.update_data(language=language)
    await state.set_state(PhotoGenStates.waiting_for_description)
    await callback.message.answer(get_string("photo_gen_prompt", language))
    await callback.answer()


@router.message(PhotoGenStates.waiting_for_description)
async def on_photo_gen_description(
    message: Message, state: FSMContext, db_path: str, bot: Bot
) -> None:
    telegram_id = message.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, message.from_user.language_code
    )
    description = message.text or ""

    if not description:
        await message.answer(get_string("photo_gen_prompt", language))
        return

    try:
        image_prompt = await content_generator.generate_image_prompt(description)
        image_url = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during standalone image generation",
            extra={"user_id": telegram_id, "operation": "photo_gen", "error_class": type(exc).__name__},
        )
        await message.answer(get_string(error_key, language))
        return

    try:
        sent_message = await bot.send_photo(
            message.chat.id,
            photo=image_url,
            caption=get_string("image_preview_caption", language),
        )
    except TelegramAPIError:
        logger.warning(
            "Failed to deliver standalone generated image to user",
            extra={"user_id": telegram_id, "operation": "photo_gen"},
        )
        await message.answer(get_string("image_delivery_failed", language))
        return

    file_id = sent_message.photo[-1].file_id
    set_pending_media(db_path, telegram_id, file_id, "photo")
    await state.set_state(None)
    await message.answer(get_string("photo_gen_ready", language))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_start.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/start.py tests/test_handlers_start.py
git commit -m "feat: add standalone photo generation from a description"
```

---

### Task 6: Full suite run and manual verification checklist

**Files:** none modified — verification only.

- [ ] **Step 1: Run the complete automated test suite**

Run: `pytest -v`
Expected: PASS — every test file, including every test added/changed in Tasks 1-5, plus every other pre-existing test file unchanged and still green.

- [ ] **Step 2: Manual verification checklist (requires the real production server and a real Telegram account — not automatable)**

Write this checklist into the chat/handoff for the owner, do not skip it:

1. Deploy this branch to production (existing CI/CD handles this on push to `feature/mvp1-bot`).
2. Open a chat with the bot that already has message history (not a brand-new chat) — confirm the native Telegram "START" button does NOT appear (this is the exact problem being fixed).
3. Send `/start` once — confirm: greeting message appears with the persistent "Старт" button now visible at the bottom of the screen; a second message "Что делаем дальше?" appears with two buttons, "Я умею" and "Создать пост сейчас".
4. Close the chat, reopen it, and tap the persistent "Старт" button (do not type `/start`) — confirm the same greeting + menu appears again.
5. Tap "Я умею" — confirm the capabilities text appears (mentions the site, photo generation, author style, 4 languages).
6. Tap "Создать пост сейчас" — confirm three buttons appear: "МОЙ САЙТ", "Генерация текста", "Генерация фото".
7. Tap "МОЙ САЙТ" — confirm the site opens as a Telegram Mini App (not a system browser).
8. Tap "Генерация текста" — confirm the hint message appears, then send an actual link/voice/text and confirm normal post generation still works exactly as before.
9. Tap "Генерация фото" — describe an image — confirm the bot generates and sends a photo, then prompts to send text/link/voice next.
10. Send text after step 9 — confirm the bot generates post variants, and pressing "Опубликовать в канал" publishes the post **with the photo from step 9 attached** (this is the existing `pending_media`/`on_refine_publish` mechanism working end-to-end with the new entry point).

- [ ] **Step 3: Report results to the owner**

Summarize pass/fail for each checklist item in plain Russian. VK auto-publish remains explicitly out of scope until a separate follow-up project (needs VK OAuth app registration first).
