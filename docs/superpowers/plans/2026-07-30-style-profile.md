# Style Profile & Quota Billing Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После пятого образца бот разбирает стиль пользователя, присылает резюме и кнопки продолжения, а дневная квота перестаёт списываться за сообщения, которые не вызывают AI.

**Architecture:** `RateLimitMiddleware` списывает единицу квоты с каждого входящего сообщения — из-за этого пять образцов стиля съедают пять единиц, и пятый образец блокируется сообщением о лимите вместо сохранения. Middleware удаляется, а проверка и списание переезжают в три обработчика сообщений, которые реально доходят до платного вызова. Параллельно появляется профиль стиля: одна таблица SQLite, один вызов AI на набор образцов, и подстановка резюме в промпт генерации.

**Tech Stack:** Python 3.14, aiogram 3.29, SQLite (stdlib `sqlite3`), pytest + pytest-asyncio (`asyncio_mode = auto`).

Спека: `docs/superpowers/specs/2026-07-30-style-profile-design.md`.

## Global Constraints

- Все команды запускаются из корня репозитория; интерпретатор — `.venv`. Тесты: `python -m pytest`.
- Каждая новая строка интерфейса добавляется во **все четыре** локали: `bot/locales/ru.py`, `en.py`, `vi.py`, `zh.py`. `tests/test_localization.py::test_all_locales_have_identical_keys` падает, если ключи разошлись.
- Комментарии в коде — на английском, как во всём `bot/`. Пишутся только там, где объясняют **почему**, а не что.
- Новые параметры функций добавляются **последними** в сигнатуре: существующие вызовы передают часть аргументов позиционно.
- `REQUIRED_EXAMPLES = 5` — единственный источник истины после Task 7 живёт в `bot/handlers/style_reading.py`.
- Стоимость платных путей в единицах квоты не меняется: текст — 1, ссылка — 1, голос — 1, тема дайджеста — 1, описание картинки — 1.
- `record_cost` для разбора стиля **не** вызывается: `bot/services/cost_tracker.py` осознанно не тарифицирует текстовые вызовы (см. его docstring), итемизируются только картинки и расшифровка.
- В рабочем дереве могут параллельно работать другие сессии. Стейджить только файлы своей задачи, поимённо. Никогда `git add -A`.

---

### Task 1: Хранилище профиля стиля

**Files:**
- Modify: `bot/storage/db.py` (константа `SCHEMA`)
- Create: `bot/storage/style_profile.py`
- Test: `tests/test_storage_style_profile.py`

**Interfaces:**
- Consumes: `bot.storage.db.get_connection(db_path) -> sqlite3.Connection`
- Produces:
  - `set_style_profile(db_path: str, telegram_id: int, summary: str) -> None`
  - `get_style_profile(db_path: str, telegram_id: int) -> str | None`
  - `clear_style_profile(db_path: str, telegram_id: int) -> None`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_style_profile.py`:

```python
from __future__ import annotations

from bot.storage.style_profile import (
    clear_style_profile,
    get_style_profile,
    set_style_profile,
)

TELEGRAM_ID = 111
OTHER_ID = 222


def test_get_returns_none_when_nothing_saved(db_path):
    assert get_style_profile(db_path, TELEGRAM_ID) is None


def test_set_then_get_returns_the_summary(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "• короткие абзацы\n• на «ты»")

    assert get_style_profile(db_path, TELEGRAM_ID) == "• короткие абзацы\n• на «ты»"


def test_set_twice_replaces_the_previous_summary(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "первое резюме")
    set_style_profile(db_path, TELEGRAM_ID, "второе резюме")

    assert get_style_profile(db_path, TELEGRAM_ID) == "второе резюме"


def test_profiles_are_per_user(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "мой стиль")
    set_style_profile(db_path, OTHER_ID, "чужой стиль")

    assert get_style_profile(db_path, TELEGRAM_ID) == "мой стиль"
    assert get_style_profile(db_path, OTHER_ID) == "чужой стиль"


def test_clear_removes_only_that_users_profile(db_path):
    set_style_profile(db_path, TELEGRAM_ID, "мой стиль")
    set_style_profile(db_path, OTHER_ID, "чужой стиль")

    clear_style_profile(db_path, TELEGRAM_ID)

    assert get_style_profile(db_path, TELEGRAM_ID) is None
    assert get_style_profile(db_path, OTHER_ID) == "чужой стиль"


def test_clear_on_a_user_without_a_profile_is_a_no_op(db_path):
    clear_style_profile(db_path, TELEGRAM_ID)

    assert get_style_profile(db_path, TELEGRAM_ID) is None
```

Фикстура `db_path` уже есть в `tests/conftest.py` — она создаёт временную БД и зовёт `init_db`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage_style_profile.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'bot.storage.style_profile'`

- [ ] **Step 3: Add the table to the schema**

В `bot/storage/db.py`, в конец строки `SCHEMA` (после блока `CREATE TABLE IF NOT EXISTS image_prompts (...)`, перед закрывающими `"""`), добавить:

```sql
-- One row per user, keyed on telegram_id rather than an autoincrement id:
-- a user has exactly one current style profile, so INSERT OR REPLACE gives
-- overwrite semantics for free. Unlike the columns above, this needs no
-- ALTER migration for already-deployed databases — executescript() creates
-- a brand-new table on every start, old databases included.
CREATE TABLE IF NOT EXISTS style_profiles (
    telegram_id INTEGER PRIMARY KEY,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

- [ ] **Step 4: Write the storage module**

Создать `bot/storage/style_profile.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection


def set_style_profile(db_path: str, telegram_id: int, summary: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT OR REPLACE INTO style_profiles (telegram_id, summary, created_at) "
            "VALUES (?, ?, ?)",
            (telegram_id, summary, created_at),
        )
        connection.commit()
    finally:
        connection.close()


def get_style_profile(db_path: str, telegram_id: int) -> str | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT summary FROM style_profiles WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def clear_style_profile(db_path: str, telegram_id: int) -> None:
    # Called together with clear_style_examples: a profile that outlived the
    # samples it was read from would describe posts the bot no longer has,
    # and would also stop a fresh set of samples from being analysed at all.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM style_profiles WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_storage_style_profile.py tests/test_storage_db.py -v`
Expected: PASS (все 6 новых тестов + существующие тесты схемы)

- [ ] **Step 6: Commit**

```bash
git add bot/storage/style_profile.py bot/storage/db.py tests/test_storage_style_profile.py
git commit -m "feat: store a per-user style profile"
```

---

### Task 2: Разбор стиля и его подстановка в промпт

**Files:**
- Modify: `bot/services/content_generator.py`
- Test: `tests/test_content_generator.py`

**Interfaces:**
- Consumes: `bot.services.ai_gateway.generate_text(prompt, model=None, temperature=None) -> str`
- Produces:
  - `build_style_analysis_prompt(style_examples: list[str], language: str) -> str`
  - `async analyze_style(style_examples: list[str], language: str) -> str`
  - `build_prompt(..., style_profile: str | None = None)` — новый **последний** параметр
  - `generate_variants(..., style_profile: str | None = None)` — новый **последний** параметр

- [ ] **Step 1: Write the failing tests**

Добавить в конец `tests/test_content_generator.py`:

```python
def test_style_analysis_prompt_contains_every_example_and_the_language():
    prompt = content_generator.build_style_analysis_prompt(
        ["Первый пост", "Второй пост"], "ru"
    )

    assert "Первый пост" in prompt
    assert "Второй пост" in prompt
    assert "ru" in prompt


@pytest.mark.asyncio
async def test_analyze_style_strips_the_model_answer(monkeypatch):
    mock = AsyncMock(return_value="  • короткие абзацы\n• на «ты»  \n")
    monkeypatch.setattr(content_generator.ai_gateway, "generate_text", mock)

    result = await content_generator.analyze_style(["Пост"], "ru")

    assert result == "• короткие абзацы\n• на «ты»"
    mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_style_sends_the_analysis_prompt(monkeypatch):
    mock = AsyncMock(return_value="• тон")
    monkeypatch.setattr(content_generator.ai_gateway, "generate_text", mock)

    await content_generator.analyze_style(["Пост про ИИ"], "en")

    sent_prompt = mock.await_args.args[0]
    assert "Пост про ИИ" in sent_prompt
    assert sent_prompt == content_generator.build_style_analysis_prompt(
        ["Пост про ИИ"], "en"
    )


def test_prompt_includes_the_style_profile_when_given():
    prompt = content_generator.build_prompt(
        "Исходник",
        "telegram",
        "ru",
        style_profile="• короткие абзацы\n• на «ты»",
    )

    assert "• короткие абзацы" in prompt


def test_prompt_includes_both_profile_and_examples():
    prompt = content_generator.build_prompt(
        "Исходник",
        "telegram",
        "ru",
        style_examples=["Мой старый пост"],
        style_profile="• ирония",
    )

    assert "• ирония" in prompt
    assert "Мой старый пост" in prompt


def test_prompt_without_profile_or_examples_has_no_style_section():
    prompt = content_generator.build_prompt("Исходник", "telegram", "ru")

    assert "author's own voice" not in prompt
    assert "Match the writing voice" not in prompt


@pytest.mark.asyncio
async def test_generate_variants_forwards_the_style_profile(monkeypatch):
    mock = AsyncMock(return_value="вариант")
    monkeypatch.setattr(content_generator.ai_gateway, "generate_text", mock)

    await content_generator.generate_variants(
        "Исходник", "telegram", "ru", count=1, style_profile="• ирония"
    )

    assert "• ирония" in mock.await_args.args[0]
```

Проверить шапку файла: нужны `import pytest`, `from unittest.mock import AsyncMock`, `from bot.services import content_generator`. Если чего-то нет — добавить.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_content_generator.py -v -k "style_analysis or analyze_style or style_profile or no_style_section"`
Expected: FAIL, `AttributeError: module 'bot.services.content_generator' has no attribute 'build_style_analysis_prompt'`

- [ ] **Step 3: Implement the analysis prompt and call**

В `bot/services/content_generator.py`, после блока `_HASHTAG_INSTRUCTION`, добавить:

```python
# Style analysis (docs/superpowers/specs/2026-07-30-style-profile-design.md).
# Written in English like every other prompt here, but the answer itself is
# requested in the user's interface language: it is shown to them verbatim.
_STYLE_ANALYSIS_INSTRUCTION = (
    "You are a writing-style analyst. Below are several social media posts "
    "written by one author. Describe that author's own voice as 4-6 very "
    "short bullet points: typical sentence and paragraph length, tone, how "
    "they address the reader, emoji habits, punctuation habits, and recurring "
    "devices such as how they open and close a post. Describe only HOW they "
    "write, never what the posts are about.\n"
    "Write the bullet points in this language (ISO 639-1 code): {language}.\n"
    "Start every bullet with '• ' and return only the bullets themselves, "
    "without any preamble, title or explanation.\n\n"
    "Posts:\n{posts}"
)


def build_style_analysis_prompt(style_examples: list[str], language: str) -> str:
    return _STYLE_ANALYSIS_INSTRUCTION.format(
        language=language, posts="\n\n---\n\n".join(style_examples)
    )


async def analyze_style(style_examples: list[str], language: str) -> str:
    # Default temperature, unlike generate_variants: this is a description of
    # something that already exists, so stability beats variety.
    result = await ai_gateway.generate_text(
        build_style_analysis_prompt(style_examples, language)
    )
    return result.strip()
```

- [ ] **Step 4: Thread the profile through the prompt builders**

Заменить `_build_style_section` целиком:

```python
def _build_style_section(
    style_examples: list[str] | None, style_profile: str | None = None
) -> str:
    if not style_examples and not style_profile:
        return ""

    section = ""
    # The profile goes first, the raw examples after it: the profile is a
    # short instruction the model can follow directly, the examples are the
    # evidence behind it. Neither replaces the other.
    if style_profile:
        section += (
            "The author's own voice, analysed from their previous posts — "
            "write in it:\n"
            f"{style_profile}\n"
        )
    if style_examples:
        quoted = "\n".join(f"- {example}" for example in style_examples)
        section += (
            "Match the writing voice and style of the examples below — the same "
            "tone, phrasing habits and rhythm — while writing about the new "
            "source material, not about the examples themselves:\n"
            f"{quoted}\n"
        )
    return section
```

В `build_prompt` добавить **последний** параметр и передать его дальше:

```python
def build_prompt(
    source_text: str,
    platform: Platform,
    content_language: str,
    extra_instruction: str | None = None,
    style_examples: list[str] | None = None,
    with_hashtags: bool = False,
    style_profile: str | None = None,
) -> str:
    extra_line = f"{extra_instruction}\n" if extra_instruction else ""
    hashtag_line = f"{_HASHTAG_INSTRUCTION}\n" if with_hashtags else ""
    style_section = _build_style_section(style_examples, style_profile)
```

Остальное тело `build_prompt` не меняется.

В `generate_variants` — тот же новый последний параметр и передача в `build_prompt`:

```python
async def generate_variants(
    source_text: str,
    platform: Platform,
    content_language: str,
    count: int = 3,
    extra_instruction: str | None = None,
    style_examples: list[str] | None = None,
    with_hashtags: bool = False,
    style_profile: str | None = None,
) -> list[str]:
    prompt = build_prompt(
        source_text,
        platform,
        content_language,
        extra_instruction,
        style_examples,
        with_hashtags,
        style_profile,
    )
```

Дальше тело не меняется.

- [ ] **Step 5: Run the full generator suite**

Run: `python -m pytest tests/test_content_generator.py -v`
Expected: PASS, включая все ранее существовавшие тесты

- [ ] **Step 6: Commit**

```bash
git add bot/services/content_generator.py tests/test_content_generator.py
git commit -m "feat: read a style profile and feed it into the post prompt"
```

---

### Task 3: Гварды в отдельном модуле

Чисто механический перенос — поведение не меняется. Отдельной задачей, чтобы Task 4 не смешивал переезд с изменением логики.

**Files:**
- Create: `bot/handlers/guards.py`
- Modify: `bot/handlers/refine.py` (удалить три функции, импортировать их), `bot/handlers/authorpost.py`, `bot/handlers/start.py`, `bot/handlers/site.py`
- Test: `tests/test_handlers_guards.py`

**Interfaces:**
- Consumes: `bot.config.load_settings()`, `bot.storage.limits.check_limit_status`, `bot.storage.whitelist.is_whitelisted`
- Produces:
  - `async safe_answer(callback: CallbackQuery) -> None`
  - `async check_whitelist_or_reply(callback: CallbackQuery, db_path: str, language: str) -> bool`
  - `async check_limit_or_reply(callback: CallbackQuery, db_path: str, language: str) -> bool`
  - `async check_message_limit_or_reply(message: Message, db_path: str, language: str) -> bool`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_guards.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.guards import check_limit_or_reply, check_message_limit_or_reply
from bot.locales.loader import get_string
from bot.storage.limits import increment_usage

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _make_message():
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    return message


def _make_callback():
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_message_guard_passes_when_under_the_limit(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "5")
    message = _make_message()

    assert await check_message_limit_or_reply(message, db_path, "ru") is True
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_guard_reports_the_daily_limit(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    message = _make_message()

    assert await check_message_limit_or_reply(message, db_path, "ru") is False
    message.answer.assert_awaited_once_with(
        get_string("error_daily_limit_exceeded", "ru")
    )


@pytest.mark.asyncio
async def test_message_guard_reports_the_monthly_limit(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "50")
    monkeypatch.setenv("MONTHLY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    message = _make_message()

    assert await check_message_limit_or_reply(message, db_path, "en") is False
    message.answer.assert_awaited_once_with(
        get_string("error_monthly_limit_exceeded", "en")
    )


@pytest.mark.asyncio
async def test_callback_guard_still_answers_the_callback_when_blocked(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    callback = _make_callback()

    assert await check_limit_or_reply(callback, db_path, "ru") is False
    callback.message.answer.assert_awaited_once_with(
        get_string("error_daily_limit_exceeded", "ru")
    )
    callback.answer.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_guards.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'bot.handlers.guards'`

- [ ] **Step 3: Create the guards module**

Создать `bot/handlers/guards.py`:

```python
from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.limits import LimitStatus, check_limit_status
from bot.storage.whitelist import is_whitelisted

logger = logging.getLogger(LOGGER_NAME)


async def safe_answer(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except TelegramBadRequest as exc:
        logger.warning(
            "Callback query answer failed (likely stale)",
            extra={"error_message": str(exc)},
        )


async def check_whitelist_or_reply(
    callback: CallbackQuery, db_path: str, language: str
) -> bool:
    # WHY this check exists at all: WhitelistMiddleware (bot/middlewares/
    # whitelist_middleware.py) is registered only on dispatcher.message.outer_
    # middleware (see bot/main.py) — it never runs for callback_query events.
    if is_whitelisted(db_path, callback.from_user.id):
        return True

    await callback.message.answer(get_string("error_not_whitelisted", language))
    await safe_answer(callback)
    return False


def _limit_error_key(db_path: str, telegram_id: int) -> str | None:
    """The locale key to answer with, or None when the user is under quota."""
    settings = load_settings()
    status = check_limit_status(
        db_path, telegram_id, settings.daily_limit, settings.monthly_limit
    )
    if status is LimitStatus.OK:
        return None
    return (
        "error_daily_limit_exceeded"
        if status is LimitStatus.DAILY_EXCEEDED
        else "error_monthly_limit_exceeded"
    )


async def check_limit_or_reply(
    callback: CallbackQuery, db_path: str, language: str
) -> bool:
    message_key = _limit_error_key(db_path, callback.from_user.id)
    if message_key is None:
        return True

    await callback.message.answer(get_string(message_key, language))
    await safe_answer(callback)
    return False


async def check_message_limit_or_reply(
    message: Message, db_path: str, language: str
) -> bool:
    # The Message twin of check_limit_or_reply: quota is charged per paid AI
    # call, and three of those calls are reached from plain messages rather
    # than from a button (bot/handlers/content.py, bot/handlers/start.py).
    message_key = _limit_error_key(db_path, message.from_user.id)
    if message_key is None:
        return True

    await message.answer(get_string(message_key, language))
    return False
```

- [ ] **Step 4: Remove the old copies and update every importer**

В `bot/handlers/refine.py`:
1. Удалить функции `_safe_answer`, `_check_whitelist_or_reply`, `_check_limit_or_reply` целиком.
2. Добавить импорт `from bot.handlers.guards import check_limit_or_reply, check_whitelist_or_reply, safe_answer`.
3. Заменить все вхождения в файле: `_safe_answer(` → `safe_answer(`, `_check_whitelist_or_reply(` → `check_whitelist_or_reply(`, `_check_limit_or_reply(` → `check_limit_or_reply(`.
4. Убрать из импортов то, что стало ненужным: `TelegramBadRequest`, `is_whitelisted`, `LimitStatus`, `check_limit_status` — но только если они больше нигде в файле не используются (проверить поиском по файлу; `load_settings` в refine.py используется и для другого).

В `bot/handlers/authorpost.py`, `bot/handlers/start.py`, `bot/handlers/site.py`: заменить импорт из `bot.handlers.refine` на импорт из `bot.handlers.guards` и переименовать вызовы теми же тремя заменами. В `start.py` строка импорта сейчас такая:

```python
from bot.handlers.refine import _check_limit_or_reply, _check_whitelist_or_reply, _safe_answer
```

становится:

```python
from bot.handlers.guards import check_limit_or_reply, check_whitelist_or_reply, safe_answer
```

В `authorpost.py` импорт многострочный (`from bot.handlers.refine import (...)`) — там же импортируется `_check_limit_or_reply`, `_check_whitelist_or_reply`, `_safe_answer`; перенести все три в новый импорт из `guards`, а сам блок `from bot.handlers.refine import (...)` удалить, если в нём ничего не осталось.

Обновить комментарии, которые ссылаются на старое расположение: `tests/test_handlers_start.py:265` и `tests/test_handlers_start.py:610` упоминают «`_check_limit_or_reply` (bot/handlers/refine.py)» — поправить на `check_limit_or_reply` (`bot/handlers/guards.py`). Это только текст комментариев, код тестов не меняется.

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS — переезд не должен менять ни одного существующего теста. Если что-то падает с `ImportError`, значит остался необновлённый импорт.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/guards.py bot/handlers/refine.py bot/handlers/authorpost.py bot/handlers/start.py bot/handlers/site.py tests/test_handlers_guards.py tests/test_handlers_start.py
git commit -m "refactor: move the whitelist and limit guards into their own module"
```

---

### Task 4: Списывать квоту только за вызовы AI

Ядро багфикса.

**Files:**
- Delete: `bot/middlewares/rate_limit_middleware.py`, `tests/test_middlewares_rate_limit.py`
- Modify: `bot/main.py`, `bot/handlers/content.py`, `bot/handlers/start.py`, `tests/test_main_site_api_wiring.py`
- Test: `tests/test_handlers_content_flow.py`, `tests/test_handlers_start.py`, `tests/test_handlers_authorpost.py`

**Interfaces:**
- Consumes: `check_message_limit_or_reply` из Task 3, `bot.storage.limits.increment_usage`
- Produces: `build_dispatcher() -> Dispatcher` (без параметров), `_finish(message, language, text, state, telegram_id, db_path, bill: bool)`

- [ ] **Step 1: Write the failing tests**

Добавить в `tests/test_handlers_authorpost.py` регрессионный тест на исходный баг (рядом с остальными тестами про образцы). Нужен импорт `from bot.storage.limits import get_daily_count, increment_usage` и `from bot.handlers.authorpost import on_authorpost_sample` — проверить, что они есть в шапке файла:

```python
@pytest.mark.asyncio
async def test_collecting_samples_costs_no_quota(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)

    for index in range(5):
        await on_authorpost_sample(_make_message(f"Образец {index}"), state, db_path)

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_fifth_sample_is_stored_even_with_the_daily_quota_used_up(db_path, monkeypatch):
    # The reported bug: RateLimitMiddleware charged a unit per message, so the
    # fifth sample hit the daily limit and was answered with "limit exceeded"
    # instead of being stored.
    monkeypatch.setenv("DAILY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)

    for index in range(5):
        await on_authorpost_sample(_make_message(f"Образец {index}"), state, db_path)

    assert len(get_style_examples(db_path, TELEGRAM_ID)) == 5
```

Импорты `AuthorPostStates` и `get_style_examples` тоже должны быть в шапке файла — добавить, если их нет.

Добавить в `tests/test_handlers_content_flow.py`:

```python
@pytest.mark.asyncio
async def test_text_post_costs_exactly_one_unit(db_path, monkeypatch):
    _mock_generate_variants(monkeypatch)
    message = _make_message(text="Исходный текст")

    await route_content(message, db_path, AsyncMock(), _make_state())

    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_failed_generation_costs_nothing(db_path, monkeypatch):
    monkeypatch.setattr(
        content_generator,
        "generate_variants",
        AsyncMock(side_effect=AIGatewayTimeoutError("boom")),
    )
    message = _make_message(text="Исходный текст")

    await route_content(message, db_path, AsyncMock(), _make_state())

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_attaching_a_photo_costs_nothing(db_path):
    message = _make_message(photo=[SimpleNamespace(file_id="photo-1")])

    await route_content(message, db_path, AsyncMock(), _make_state())

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_voice_post_costs_one_unit_in_total(db_path, monkeypatch):
    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="расшифровка")
    )
    _mock_generate_variants(monkeypatch)
    state = _make_state()
    message = _make_message(voice=_make_voice())

    await route_content(message, db_path, AsyncMock(), state)
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    callback.message = _make_message()
    await on_transcript_confirm(callback, state, db_path)

    # One unit for the transcription; confirming it must not charge again.
    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_text_is_refused_without_calling_ai_when_over_quota(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    generate = _mock_generate_variants(monkeypatch)
    message = _make_message(text="Исходный текст")

    await route_content(message, db_path, AsyncMock(), _make_state())

    generate.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        get_string("error_daily_limit_exceeded", "ru")
    )
```

В шапку `tests/test_handlers_content_flow.py` добавить недостающее: `from bot.storage.limits import get_daily_count, increment_usage`. Если в файле нет хелпера `_make_state()`, взять его из `tests/test_handlers_authorpost.py`:

```python
def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handlers_authorpost.py tests/test_handlers_content_flow.py -v -k "quota or costs or units"`
Expected: FAIL — тесты про образцы падают, потому что без middleware квота пока вообще не списывается и не проверяется в `route_content`; тесты про стоимость падают на `assert get_daily_count(...) == 1`, получая 0.

- [ ] **Step 3: Delete the middleware and unwire it**

```bash
git rm bot/middlewares/rate_limit_middleware.py tests/test_middlewares_rate_limit.py
```

В `bot/main.py`:
1. Удалить `from bot.middlewares.rate_limit_middleware import RateLimitMiddleware`.
2. Удалить строку `dispatcher.message.outer_middleware(RateLimitMiddleware(daily_limit, monthly_limit))`.
3. Поменять сигнатуру на `def build_dispatcher() -> Dispatcher:`.
4. Поправить комментарий над `WhitelistMiddleware` — он сейчас объясняет порядок относительно rate-limit middleware:

```python
    # Whitelist gating stays at the message level: an uninvited user must not
    # reach a handler at all. Quota is no longer charged here — it is checked
    # and charged at each paid AI call instead (bot/handlers/guards.py).
    dispatcher.message.outer_middleware(WhitelistMiddleware())
```

5. В `run()` заменить вызов на `dispatcher = build_dispatcher()`.

В `tests/test_main_site_api_wiring.py:101` заменить `build_dispatcher(daily_limit=10, monthly_limit=100)` на `build_dispatcher()`.

- [ ] **Step 4: Charge at the paid call sites in content.py**

В `bot/handlers/content.py` добавить импорты:

```python
from bot.handlers.guards import check_message_limit_or_reply
from bot.storage.limits import increment_usage
```

В `route_content`, сразу после ветки прикрепления медиа и до `input_type = detect_input_type(message)`:

```python
    # Quota is checked once here, for every branch below: text and link both
    # end in a generation, voice ends in a paid transcription. Everything that
    # returned above this line stays free, and so does every state-filtered
    # handler that never reaches route_content at all — style samples among
    # them, which is the bug this placement fixes.
    if not await check_message_limit_or_reply(message, db_path, language):
        return
```

Изменить сигнатуру `_finish` — новый параметр **последним**:

```python
async def _finish(
    message: Message,
    language: str,
    text: str,
    state: FSMContext,
    telegram_id: int,
    db_path: str,
    bill: bool,
) -> None:
```

Внутри `_finish`, сразу после `except AIGatewayError` блока (то есть после успешной генерации обоих наборов вариантов) и **до** первого `send_variants`:

```python
    # Charged after the calls succeeded, like bot/handlers/refine.py: a failed
    # generation costs the user nothing. `bill` is False on the voice path —
    # the transcription in _handle_voice already charged for that request, and
    # charging again here would make a voice post cost twice a text one.
    if bill:
        increment_usage(db_path, telegram_id)
```

Обновить три вызова `_finish`:
- в `route_content` (текстовая ветка): `await _finish(message, language, message.text, state, telegram_id, db_path, bill=True)`
- в `_handle_link`: `await _finish(message, language, extracted_text, state, telegram_id, db_path, bill=True)`
- в `on_transcript_confirm`: `await _finish(callback.message, language, transcript, state, callback.from_user.id, db_path, bill=False)`

В `_handle_voice`, сразу после существующего блока `record_cost(...)` и до `await _show_transcript_confirmation(...)`:

```python
    increment_usage(db_path, message.from_user.id)
```

- [ ] **Step 5: Charge at the paid call sites in start.py**

В `bot/handlers/start.py` заменить импорт гвардов на строку, включающую `check_message_limit_or_reply`:

```python
from bot.handlers.guards import (
    check_limit_or_reply,
    check_message_limit_or_reply,
    check_whitelist_or_reply,
    safe_answer,
)
```

В `on_digest_topic_input`, после блока `if not topic:` и до `set_digest_topic(...)`:

```python
    if not await check_message_limit_or_reply(message, db_path, language):
        return
```

и после `result = await digest.build_digest(topic)`:

```python
    increment_usage(db_path, telegram_id)
```

В `on_photo_gen_description`, после блока `if not description:` и до `ensure_image_budget(...)`:

```python
    if not await check_message_limit_or_reply(message, db_path, language):
        return
```

и рядом с существующим `increment_image_usage(db_path, telegram_id)` (после успешной отправки фото), строкой выше:

```python
    increment_usage(db_path, telegram_id)
```

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. Ожидаемые падения, которые надо починить по ходу: тесты, считавшие, что сообщение само по себе списывает единицу. Проверить в первую очередь `tests/test_handlers_start.py` (дайджест и генерация картинки) и `tests/test_handlers_content_flow.py`. Правило проверки: платный путь — ровно 1 единица, бесплатный — 0.

- [ ] **Step 7: Commit**

```bash
git add bot/main.py bot/handlers/content.py bot/handlers/start.py tests/test_main_site_api_wiring.py tests/test_handlers_content_flow.py tests/test_handlers_start.py tests/test_handlers_authorpost.py
git commit -m "fix: charge quota per AI call instead of per message"
```

---

### Task 5: Строки локалей

**Files:**
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`
- Test: `tests/test_localization.py` (запуск, без правок)

**Interfaces:**
- Produces: ключи `style_read_summary`, `style_button_own_topic`, `style_button_fresh_digest`, `style_own_topic_prompt`; изменённый текст `authorpost_samples_done_button`.

- [ ] **Step 1: Add the keys to ru.py**

Рядом с существующим `authorpost_samples_done_button` в `bot/locales/ru.py` заменить его значение и добавить четыре ключа:

```python
    "authorpost_samples_done_button": "✒ Пиши пост по выбранной теме",
    "style_read_summary": (
        "Считал твой стиль ✅\n\n"
        "Как ты пишешь:\n"
        "{summary}\n\n"
        "Буду писать так же."
    ),
    "style_button_own_topic": "✍ Авторский пост на свою тему",
    "style_button_fresh_digest": "📰 Пост из свежего дайджеста",
    "style_own_topic_prompt": (
        "Пришлите тему или текст — сделаю из этого пост в вашем стиле. "
        "Можно ссылкой или голосовым сообщением."
    ),
```

- [ ] **Step 2: Add the same keys to en.py**

```python
    "authorpost_samples_done_button": "✒ Write the post on the chosen topic",
    "style_read_summary": (
        "I've read your style ✅\n\n"
        "How you write:\n"
        "{summary}\n\n"
        "I'll write the same way."
    ),
    "style_button_own_topic": "✍ Authored post on my own topic",
    "style_button_fresh_digest": "📰 Post from a fresh digest",
    "style_own_topic_prompt": (
        "Send me a topic or a text — I'll turn it into a post in your voice. "
        "A link or a voice message works too."
    ),
```

- [ ] **Step 3: Add the same keys to vi.py**

```python
    "authorpost_samples_done_button": "✒ Viết bài theo chủ đề đã chọn",
    "style_read_summary": (
        "Đã nắm được văn phong của bạn ✅\n\n"
        "Bạn viết như thế nào:\n"
        "{summary}\n\n"
        "Tôi sẽ viết đúng như vậy."
    ),
    "style_button_own_topic": "✍ Bài viết theo chủ đề của tôi",
    "style_button_fresh_digest": "📰 Bài viết từ bản tin mới",
    "style_own_topic_prompt": (
        "Hãy gửi một chủ đề hoặc một đoạn văn bản — tôi sẽ viết thành bài "
        "theo văn phong của bạn. Bạn cũng có thể gửi liên kết hoặc tin nhắn thoại."
    ),
```

- [ ] **Step 4: Add the same keys to zh.py**

```python
    "authorpost_samples_done_button": "✒ 按已选主题写帖子",
    "style_read_summary": (
        "已读懂你的风格 ✅\n\n"
        "你的写作特点：\n"
        "{summary}\n\n"
        "我会照这个风格来写。"
    ),
    "style_button_own_topic": "✍ 按我自己的主题写帖子",
    "style_button_fresh_digest": "📰 用最新摘要写帖子",
    "style_own_topic_prompt": (
        "发给我一个主题或一段文字，我会按你的风格写成帖子。也可以发链接或语音消息。"
    ),
```

- [ ] **Step 5: Run the localization tests**

Run: `python -m pytest tests/test_localization.py -v`
Expected: PASS — в частности `test_all_locales_have_identical_keys`

- [ ] **Step 6: Commit**

```bash
git add bot/locales/ru.py bot/locales/en.py bot/locales/vi.py bot/locales/zh.py
git commit -m "feat: add the style-read strings in all four locales"
```

---

### Task 6: Клавиатура готового стиля

**Files:**
- Create: `bot/keyboards/style.py`
- Modify: `bot/keyboards/authorpost.py` (удалить `build_samples_done_keyboard`)
- Test: `tests/test_keyboards_style.py`, `tests/test_keyboards_authorpost.py`

**Interfaces:**
- Consumes: `CALLBACK_SAMPLES_DONE` из `bot.keyboards.authorpost`, `CALLBACK_NEWS_DIGEST` из `bot.keyboards.start`
- Produces: `CALLBACK_OWN_TOPIC = "authorpost:own_topic"`, `build_style_ready_keyboard(lang: str, has_source_text: bool) -> InlineKeyboardMarkup`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_keyboards_style.py`:

```python
from __future__ import annotations

from bot.keyboards.authorpost import CALLBACK_SAMPLES_DONE
from bot.keyboards.start import CALLBACK_NEWS_DIGEST
from bot.keyboards.style import CALLBACK_OWN_TOPIC, build_style_ready_keyboard
from bot.locales.loader import get_string


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_three_buttons_when_a_topic_is_already_chosen():
    markup = build_style_ready_keyboard("ru", has_source_text=True)

    assert _callbacks(markup) == [
        CALLBACK_SAMPLES_DONE,
        CALLBACK_OWN_TOPIC,
        CALLBACK_NEWS_DIGEST,
    ]


def test_two_buttons_when_no_topic_is_chosen():
    markup = build_style_ready_keyboard("ru", has_source_text=False)

    assert _callbacks(markup) == [CALLBACK_OWN_TOPIC, CALLBACK_NEWS_DIGEST]


def test_buttons_are_labelled_from_the_locale():
    markup = build_style_ready_keyboard("en", has_source_text=True)
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert labels == [
        get_string("authorpost_samples_done_button", "en"),
        get_string("style_button_own_topic", "en"),
        get_string("style_button_fresh_digest", "en"),
    ]


def test_every_button_sits_on_its_own_row():
    markup = build_style_ready_keyboard("ru", has_source_text=True)

    assert all(len(row) == 1 for row in markup.inline_keyboard)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_keyboards_style.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'bot.keyboards.style'`

- [ ] **Step 3: Create the keyboard module**

Создать `bot/keyboards/style.py`:

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.authorpost import CALLBACK_SAMPLES_DONE
from bot.keyboards.start import CALLBACK_NEWS_DIGEST
from bot.locales.loader import get_string

CALLBACK_OWN_TOPIC = "authorpost:own_topic"


# WHY its own module rather than bot/keyboards/authorpost.py: this keyboard
# mixes a button from authorpost with the digest button from start, and
# start.py already imports from authorpost.py — putting it there would close
# the import cycle. Nothing imports this module back, so the graph stays a DAG.
def build_style_ready_keyboard(lang: str, has_source_text: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # Only offered when a digest item was picked before the samples were sent
    # (the authored-post flow). Reached from /settov there is no topic yet, and
    # the button would lead straight to an "expired digest" reply.
    if has_source_text:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_samples_done_button", lang),
                    callback_data=CALLBACK_SAMPLES_DONE,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("style_button_own_topic", lang),
                callback_data=CALLBACK_OWN_TOPIC,
            )
        ]
    )
    # Reuses the main menu's own callback instead of a private one: two entry
    # points to the same digest must not drift apart.
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("style_button_fresh_digest", lang),
                callback_data=CALLBACK_NEWS_DIGEST,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 4: Delete the keyboard it replaces**

Удалить `build_samples_done_keyboard` из `bot/keyboards/authorpost.py` — с Task 7 её больше никто не вызывает. Удалить её тесты из `tests/test_keyboards_authorpost.py` (искать по имени функции). Константу `CALLBACK_SAMPLES_DONE` **оставить** — она используется новой клавиатурой и обработчиком.

На этом шаге `bot/handlers/authorpost.py` ещё импортирует `build_samples_done_keyboard`, поэтому suite упадёт на `ImportError`. Убрать этот импорт и его единственное использование в `on_authorpost_sample` временно, заменив вызов на отправку без клавиатуры:

```python
        await message.answer(
            get_string(
                "authorpost_samples_enough", language, count=count, required=REQUIRED_EXAMPLES
            )
        )
```

Task 7 заменит эту ветку целиком.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_keyboards_style.py tests/test_keyboards_authorpost.py tests/test_handlers_authorpost.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/keyboards/style.py bot/keyboards/authorpost.py bot/handlers/authorpost.py tests/test_keyboards_style.py tests/test_keyboards_authorpost.py
git commit -m "feat: add the style-ready keyboard"
```

---

### Task 7: Разбор стиля после пятого образца

**Files:**
- Create: `bot/handlers/style_reading.py`
- Modify: `bot/handlers/authorpost.py`, `bot/handlers/settov.py`
- Test: `tests/test_handlers_style_reading.py`, `tests/test_handlers_authorpost.py`, `tests/test_handlers_settov.py`

**Interfaces:**
- Consumes: `content_generator.analyze_style` (Task 2), `get/set/clear_style_profile` (Task 1), `build_style_ready_keyboard` (Task 6)
- Produces:
  - `REQUIRED_EXAMPLES = 5`
  - `async read_style_if_ready(message: Message, db_path: str, telegram_id: int, language: str, has_source_text: bool) -> bool`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_style_reading.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.style_reading import REQUIRED_EXAMPLES, read_style_if_ready
from bot.locales.loader import get_string
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.style_examples import add_style_example
from bot.storage.style_profile import get_style_profile, set_style_profile

TELEGRAM_ID = 111
SUMMARY = "• короткие абзацы\n• на «ты»"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _make_message():
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    return message


def _seed_examples(db_path, count):
    for index in range(count):
        add_style_example(db_path, TELEGRAM_ID, f"Образец {index}")


def _mock_analyze(monkeypatch, summary=SUMMARY):
    mock = AsyncMock(return_value=summary)
    monkeypatch.setattr(content_generator, "analyze_style", mock)
    return mock


@pytest.mark.asyncio
async def test_below_the_threshold_nothing_happens(db_path, monkeypatch):
    analyze = _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES - 1)
    message = _make_message()

    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", False)

    assert handled is False
    analyze.assert_not_awaited()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_at_the_threshold_reads_and_saves_the_profile(db_path, monkeypatch):
    analyze = _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)
    message = _make_message()

    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", False)

    assert handled is True
    analyze.assert_awaited_once()
    assert get_style_profile(db_path, TELEGRAM_ID) == SUMMARY
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("style_read_summary", "ru", summary=SUMMARY)
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_an_extra_sample_does_not_re_analyse(db_path, monkeypatch):
    analyze = _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)
    await read_style_if_ready(_make_message(), db_path, TELEGRAM_ID, "ru", False)
    analyze.reset_mock()

    add_style_example(db_path, TELEGRAM_ID, "Шестой образец")
    message = _make_message()
    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", False)

    assert handled is True
    analyze.assert_not_awaited()
    args, _ = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_enough",
        "ru",
        count=REQUIRED_EXAMPLES + 1,
        required=REQUIRED_EXAMPLES,
    )


@pytest.mark.asyncio
async def test_an_ai_failure_keeps_the_flow_alive(db_path, monkeypatch):
    monkeypatch.setattr(
        content_generator,
        "analyze_style",
        AsyncMock(side_effect=AIGatewayTimeoutError("boom")),
    )
    _seed_examples(db_path, REQUIRED_EXAMPLES)
    message = _make_message()

    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", True)

    assert handled is True
    assert get_style_profile(db_path, TELEGRAM_ID) is None
    args, kwargs = message.answer.call_args
    assert args[0] == get_string(
        "authorpost_samples_enough",
        "ru",
        count=REQUIRED_EXAMPLES,
        required=REQUIRED_EXAMPLES,
    )
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_reading_the_style_costs_no_quota(db_path, monkeypatch):
    from bot.storage.limits import get_daily_count

    _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)

    await read_style_if_ready(_make_message(), db_path, TELEGRAM_ID, "ru", False)

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_an_existing_profile_is_never_overwritten_by_a_new_sample(db_path, monkeypatch):
    set_style_profile(db_path, TELEGRAM_ID, "старое резюме")
    analyze = _mock_analyze(monkeypatch, "новое резюме")
    _seed_examples(db_path, REQUIRED_EXAMPLES)

    await read_style_if_ready(_make_message(), db_path, TELEGRAM_ID, "ru", False)

    analyze.assert_not_awaited()
    assert get_style_profile(db_path, TELEGRAM_ID) == "старое резюме"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_style_reading.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'bot.handlers.style_reading'`

- [ ] **Step 3: Write the module**

Создать `bot/handlers/style_reading.py`:

```python
from __future__ import annotations

import logging

from aiogram.types import Message

from bot.keyboards.style import build_style_ready_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayError
from bot.storage.style_examples import get_style_examples
from bot.storage.style_profile import get_style_profile, set_style_profile

logger = logging.getLogger(LOGGER_NAME)

# Below this many stored style examples the bot refuses to write: fewer
# samples do not carry a recognisable voice, they just bias the model toward
# whichever single post it saw.
REQUIRED_EXAMPLES = 5


async def read_style_if_ready(
    message: Message,
    db_path: str,
    telegram_id: int,
    language: str,
    has_source_text: bool,
) -> bool:
    """Analyse the stored samples once they are enough, and reply.

    Shared by the two places that collect samples — /settov and the authored
    post flow. Returns True when it has answered the user, so the caller knows
    to skip its own progress message.

    Never touches the quota: reading a style is a one-off setup step, not a
    piece of delivered content, and charging for it would strand the user with
    a configured voice and no posts left.
    """
    examples = get_style_examples(db_path, telegram_id)
    if len(examples) < REQUIRED_EXAMPLES:
        return False

    keyboard = build_style_ready_keyboard(language, has_source_text)
    enough_message = get_string(
        "authorpost_samples_enough",
        language,
        count=len(examples),
        required=REQUIRED_EXAMPLES,
    )

    # Already read for this set of samples. Extra samples are still stored and
    # still quoted into the prompt, but re-analysing on each one would spend an
    # AI call per message for a profile that barely moves.
    if get_style_profile(db_path, telegram_id) is not None:
        await message.answer(enough_message, reply_markup=keyboard)
        return True

    try:
        summary = await content_generator.analyze_style(examples, language)
    except AIGatewayError as exc:
        logger.warning(
            "AI Gateway error during style analysis",
            extra={
                "user_id": telegram_id,
                "operation": "analyze_style",
                "error_class": type(exc).__name__,
            },
        )
        # No profile stored, so the next sample retries the analysis. The user
        # keeps the same buttons either way — a failed read must not cost them
        # the flow.
        await message.answer(enough_message, reply_markup=keyboard)
        return True

    set_style_profile(db_path, telegram_id, summary)
    logger.info(
        "Style profile read",
        extra={
            "user_id": telegram_id,
            "operation": "analyze_style",
            "example_count": len(examples),
        },
    )
    await message.answer(
        get_string("style_read_summary", language, summary=summary),
        reply_markup=keyboard,
    )
    return True
```

- [ ] **Step 4: Run the module's tests**

Run: `python -m pytest tests/test_handlers_style_reading.py -v`
Expected: PASS (6 тестов)

- [ ] **Step 5: Wire it into the authored-post flow**

В `bot/handlers/authorpost.py`:

1. Удалить локальное определение `REQUIRED_EXAMPLES` и импортировать его вместе с функцией:

```python
from bot.handlers.style_reading import REQUIRED_EXAMPLES, read_style_if_ready
```

2. Заменить хвост `on_authorpost_sample` (всё, что после `add_style_example(...)`) на:

```python
    add_style_example(db_path, telegram_id, message.text)

    data = await state.get_data()
    if await read_style_if_ready(
        message, db_path, telegram_id, language, bool(data.get("source_text"))
    ):
        return

    # The counter reports everything in storage, not just this session's
    # messages: "не менее 5" means "the bot holds 5 samples of your voice",
    # so a user who already had 2 saved is done after 3 more.
    await message.answer(
        get_string(
            "authorpost_samples_progress",
            language,
            count=_stored_example_count(db_path, telegram_id),
            required=REQUIRED_EXAMPLES,
        )
    )
```

3. В `on_authorpost_new_samples` добавить очистку профиля рядом с `clear_style_examples`:

```python
    clear_style_examples(db_path, telegram_id)
    clear_style_profile(db_path, telegram_id)
```

с импортом `from bot.storage.style_profile import clear_style_profile`.

4. В `on_authorpost_platform` подставить профиль в генерацию — рядом с `style_examples = get_style_examples(...)`:

```python
    style_examples = get_style_examples(db_path, telegram_id)
    style_profile = get_style_profile(db_path, telegram_id)
```

и добавить `style_profile=style_profile` в вызов `content_generator.generate_variants(...)`. Импорт: `from bot.storage.style_profile import clear_style_profile, get_style_profile`.

- [ ] **Step 6: Wire it into /settov**

В `bot/handlers/settov.py` заменить хвост `on_settov_example` после `add_style_example(...)`:

```python
    add_style_example(db_path, telegram_id, message.text)
    logger.info(
        "Style example saved",
        extra={"user_id": telegram_id, "operation": "handler:settov"},
    )

    # has_source_text=False: /settov has no digest item picked, so the
    # "write the post on the chosen topic" button would be a dead end.
    if await read_style_if_ready(message, db_path, telegram_id, language, False):
        return

    await message.answer(
        get_string("settov_example_saved", language),
        reply_markup=build_settov_done_keyboard(language),
    )
```

с импортом `from bot.handlers.style_reading import read_style_if_ready`.

- [ ] **Step 7: Use the profile in the two other generation paths**

В `bot/handlers/content.py`, в `_finish`, рядом с `style_examples = get_style_examples(db_path, telegram_id)`:

```python
    style_profile = get_style_profile(db_path, telegram_id)
```

и добавить `style_profile=style_profile` в оба вызова `content_generator.generate_variants(...)`. Импорт: `from bot.storage.style_profile import get_style_profile`.

То же самое в `bot/handlers/refine.py`, в `_generate_and_send`: прочитать профиль рядом со `style_examples` и передать `style_profile=style_profile` в `generate_variants`.

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. Ожидаемо потребуют правки существующие тесты, проверявшие старый ответ на пятый образец: `tests/test_handlers_authorpost.py::test_sample_at_threshold_offers_done_button` и тесты `/settov`, отправляющие 5+ примеров (`test_sending_more_than_cap_examples_still_saves_up_to_cap`). В них надо замокать `content_generator.analyze_style` (`AsyncMock(return_value="• тон")`) и ожидать новый текст ответа.

- [ ] **Step 9: Commit**

```bash
git add bot/handlers/style_reading.py bot/handlers/authorpost.py bot/handlers/settov.py bot/handlers/content.py bot/handlers/refine.py tests/test_handlers_style_reading.py tests/test_handlers_authorpost.py tests/test_handlers_settov.py
git commit -m "feat: read the user's style after the fifth sample"
```

---

### Task 8: Кнопки продолжения

**Files:**
- Modify: `bot/handlers/authorpost.py`, `bot/handlers/start.py`
- Test: `tests/test_handlers_authorpost.py`, `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: `CALLBACK_OWN_TOPIC` (Task 6), `CALLBACK_SAMPLES_DONE`, `CALLBACK_NEWS_DIGEST`
- Produces: `on_authorpost_own_topic(callback, state, db_path)`; `on_authorpost_samples_done` без фильтра по состоянию; сброс состояния в `on_menu_news_digest`

- [ ] **Step 1: Write the failing tests**

Добавить в `tests/test_handlers_authorpost.py`:

```python
@pytest.mark.asyncio
async def test_own_topic_clears_state_and_asks_for_a_topic(db_path):
    state = _make_state()
    await state.set_state(AuthorPostStates.collecting_examples)
    callback = _make_callback(CALLBACK_OWN_TOPIC)

    await on_authorpost_own_topic(callback, state, db_path)

    assert await state.get_state() is None
    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("style_own_topic_prompt", "ru")


@pytest.mark.asyncio
async def test_own_topic_refuses_user_outside_whitelist(db_path):
    state = _make_state()
    callback = _make_callback(CALLBACK_OWN_TOPIC, telegram_id=999)

    await on_authorpost_own_topic(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_not_whitelisted", "ru")


@pytest.mark.asyncio
async def test_samples_done_works_from_the_settov_state(db_path):
    # The keyboard is shown from /settov too, where the state belongs to a
    # different StatesGroup — a state-filtered handler would never fire.
    from bot.handlers.settov import SettovStates

    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)
    callback = _make_callback(CALLBACK_SAMPLES_DONE)

    await on_authorpost_samples_done(callback, state, db_path)

    assert await state.get_state() is None
    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_platform", "ru")
```

Добавить импорты в шапку: `on_authorpost_own_topic`, `on_authorpost_samples_done` из `bot.handlers.authorpost`, `CALLBACK_OWN_TOPIC` из `bot.keyboards.style`, `CALLBACK_SAMPLES_DONE` из `bot.keyboards.authorpost`.

Добавить в `tests/test_handlers_start.py`, рядом с существующими тестами `on_menu_news_digest` (около строки 275). Хелперы `_make_state(telegram_id)`, `_make_callback(telegram_id, data)` и способ мокать `digest_service.build_digest` взяты из этого же файла:

```python
@pytest.mark.asyncio
async def test_news_digest_clears_a_leftover_collecting_state(db_path, monkeypatch):
    # Reached from the style-ready keyboard (bot/keyboards/style.py), where a
    # sample-collection state is still set: leaving it set would turn the
    # user's next plain message into another style sample.
    from bot.handlers.authorpost import AuthorPostStates

    telegram_id = 2014
    add_user(db_path, telegram_id)
    set_digest_topic(db_path, telegram_id, "ИИ")
    monkeypatch.setattr(
        digest_service,
        "build_digest",
        AsyncMock(
            return_value=digest_service.DigestResult(
                topic="ИИ", news=[], papers=[], methods_summary=None
            )
        ),
    )
    state = _make_state(telegram_id)
    await state.set_state(AuthorPostStates.collecting_examples)
    callback = _make_callback(telegram_id, CALLBACK_NEWS_DIGEST)

    await on_menu_news_digest(callback, state, db_path)

    assert await state.get_state() is None
```

Проверить, что `CALLBACK_NEWS_DIGEST`, `add_user`, `set_digest_topic`, `digest_service` и `AsyncMock` уже импортированы в шапке файла — они используются соседними тестами.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handlers_authorpost.py tests/test_handlers_start.py -v -k "own_topic or settov_state or leftover"`
Expected: FAIL, `ImportError: cannot import name 'on_authorpost_own_topic'`

- [ ] **Step 3: Add the own-topic handler**

В `bot/handlers/authorpost.py` добавить импорт `from bot.keyboards.style import CALLBACK_OWN_TOPIC` и обработчик:

```python
@router.callback_query(F.data == CALLBACK_OWN_TOPIC)
async def on_authorpost_own_topic(
    callback: CallbackQuery, state: FSMContext, db_path: str
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    # Back to None before anything else: while a sample-collection state is
    # set, route_content (StateFilter(None)) never fires, so the topic the
    # user is about to type would be filed as one more style sample.
    await state.set_state(None)
    await callback.message.answer(get_string("style_own_topic_prompt", language))
    await safe_answer(callback)
```

- [ ] **Step 4: Drop the state filter from the samples-done handler**

В `bot/handlers/authorpost.py` изменить декоратор `on_authorpost_samples_done`:

```python
@router.callback_query(F.data == CALLBACK_SAMPLES_DONE)
```

и заменить комментарий внутри на:

```python
    # No state filter on the decorator: the same keyboard is sent from
    # /settov, whose state belongs to a different StatesGroup, and a filtered
    # handler would silently not fire there. Resetting to None is what matters
    # here — while a state is set, route_content (StateFilter(None)) never
    # fires and the bot ignores ordinary messages.
    await state.set_state(None)
```

- [ ] **Step 5: Reset the state on the digest button**

В `bot/handlers/start.py`, в `on_menu_news_digest`, сразу после проверки вайтлиста:

```python
    # Also reached from the style-ready keyboard (bot/keyboards/style.py),
    # where a sample-collection state is still set: leaving it would file the
    # user's next plain message as another style sample.
    await state.set_state(None)
```

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add bot/handlers/authorpost.py bot/handlers/start.py tests/test_handlers_authorpost.py tests/test_handlers_start.py
git commit -m "feat: continue from a read style into either post flow"
```

---

### Task 9: Ручная проверка и документация

**Files:**
- Modify: `docs/manual-checklist.md`

- [ ] **Step 1: Run the full suite one more time**

Run: `python -m pytest -q`
Expected: PASS, ноль падений

- [ ] **Step 2: Add the manual checks**

Дописать в `docs/manual-checklist.md`, в конец, следуя оформлению уже имеющихся разделов:

```markdown
## Считанный стиль (2026-07-30)

- [ ] `/settov` → пять образцов подряд: на пятом приходит «Считал твой стиль ✅»
      с резюме и двумя кнопками
- [ ] Дайджест → «Авторский пост» → пункт → «Далее» → пять образцов: на пятом
      приходит резюме и **три** кнопки, первая — «Пиши пост по выбранной теме»
- [ ] Шестой образец подряд не запускает разбор заново (ответ — «Принято 6 из 5»)
- [ ] «Загрузить новые образцы» → пять новых образцов → разбор запускается снова
- [ ] Кнопка «Авторский пост на свою тему»: бот просит тему, следующее
      сообщение уходит в генерацию, а не в образцы
- [ ] Кнопка «Пост из свежего дайджеста» отдаёт дайджест, и следующее обычное
      сообщение тоже уходит в генерацию, а не в образцы
- [ ] Сгенерированный после разбора пост заметно ближе к своему слогу, чем до
- [ ] Пять образцов подряд не сдвигают счётчик `/costs` и не тратят дневной лимит
- [ ] При исчерпанном дневном лимите образцы всё равно принимаются, а обычный
      текстовый пост отвечает сообщением о лимите
```

- [ ] **Step 3: Commit**

```bash
git add docs/manual-checklist.md
git commit -m "docs: manual checks for the style read and the billing fix"
```

---

## Порядок и зависимости

1 и 2 независимы. 3 обязана предшествовать 4. 5 обязана предшествовать 6. 6 предшествует 7. 7 предшествует 8. 9 — последняя.

Багфикс отчуждаем от фичи: если нужно отдать пользователю починку лимита раньше, Tasks 3–4 самодостаточны и деплоятся отдельно.
