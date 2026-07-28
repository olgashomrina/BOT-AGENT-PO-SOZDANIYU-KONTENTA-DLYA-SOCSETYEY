# Тематический дайджест — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing stub button "Собрать дайджест свежих новостей" into a real feature: on tap, it either instantly rebuilds a digest for the user's saved topic or asks the user to type one via a `ForceReply` input box; the typed topic is saved as the new default and also drives a daily automatic digest sent to every user who has one configured.

**Architecture:** One new pure-function service module (`bot/services/digest.py`) fetches from three free/official sources (Google News RSS, Semantic Scholar API, plus an AI-Gateway synthesis step for "new methods") with per-source failure isolation. A new `digest_topic` column on `users` (same ALTER-TABLE-migration pattern used 3 times already) stores the saved topic. The existing `bot/handlers/start.py`/`bot/keyboards/start.py` gain the button-driven UX (no new slash commands). A new `bot/services/digest_scheduler.py` wraps APScheduler's `AsyncIOScheduler`, registered in `bot/main.py` next to the existing Dispatcher/aiohttp wiring — no new deployable unit, no new systemd service.

**Tech Stack:** Python, aiogram 3.29 (existing), `httpx` (existing, already used by `ai_gateway.py`), new: `feedparser` (RSS parsing), `apscheduler` (in-process daily scheduling).

Reference docs: `docs/superpowers/specs/2026-07-28-topic-digest-design.md` (design spec, approved) — read it first if anything below is ambiguous, it explains the *why* behind these choices (source selection, why pytrends/Google Trends was rejected, why Wordstat is deferred).

## Global Constraints

- Every new user-facing string must exist in all 4 locale files (`bot/locales/ru.py`, `en.py`, `vi.py`, `zh.py`) — enforced by `tests/test_localization.py::test_all_locales_have_identical_keys`.
- Every new `callback_query` handler must explicitly call `_check_whitelist_or_reply` (imported from `bot.handlers.refine`) — `WhitelistMiddleware` only runs on `message` events, never `callback_query` (see `bot/handlers/refine.py:52-62`).
- Any `callback_query` handler that triggers an AI Gateway call must also explicitly call `_check_limit_or_reply` (imported from `bot.handlers.refine`) and, on success, `increment_usage(db_path, telegram_id)` (from `bot.storage.limits`) — `RateLimitMiddleware` only runs on `message` events (see `bot/handlers/refine.py:65-86`, `bot/middlewares/rate_limit_middleware.py`).
- New `message`-triggered handlers need **no** manual whitelist or quota check — both middlewares already run on every `message` event automatically, and `RateLimitMiddleware` increments usage itself before the handler runs (`bot/middlewares/rate_limit_middleware.py:45`).
- Telegram's `ForceReply.input_field_placeholder` has a hard 1–64 character limit — keep `digest_topic_input_placeholder` short in every language.
- The daily automatic digest (APScheduler job) deliberately does **not** check or consume the daily/monthly quota — it is not a per-request user action, same reasoning as `owner_notifier`'s crash notifications being unmetered. Do not add quota logic there; this is a documented decision, not a gap.
- Google News RSS `<link>` values are Google redirect URLs, not the original publisher URL — accepted as-is (still a working clickable link), not something to "fix" by following redirects.
- New dependencies, pinned exactly like everything else in `requirements.txt`: `feedparser==6.0.11`, `apscheduler==3.10.4`.
- Scheduler fires at a fixed time for all users, hardcoded to the `Europe/Moscow` timezone via `apscheduler.triggers.cron.CronTrigger(timezone=...)` — not the server's local timezone, so it's 09:00 MSK regardless of where the server actually runs.
- Total digest output is bounded to at most 4 news items + 3 paper items = 7 links, matching the spec's "5–7 links" target.

---

### Task 1: Storage layer — `digest_topic` column

**Files:**
- Modify: `bot/storage/db.py`
- Modify: `bot/storage/users.py`
- Test: `tests/test_storage_db.py`
- Test: `tests/test_storage_users.py`

**Interfaces:**
- Consumes: `bot.storage.db.get_connection` (existing).
- Produces: `set_digest_topic(db_path: str, telegram_id: int, topic: str) -> None`, `get_digest_topic(db_path: str, telegram_id: int) -> str | None`, `get_users_with_digest_topic(db_path: str) -> list[tuple[int, str]]` — all consumed by Task 5 (handlers) and Task 6 (scheduler).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage_users.py` (add to the existing import block at the top, then append the test functions at the end of the file):

```python
from bot.storage.users import (
    get_digest_topic,
    get_users_with_digest_topic,
    set_digest_topic,
)


def test_unknown_user_has_no_digest_topic(db_path):
    assert get_digest_topic(db_path, 111) is None


def test_set_digest_topic_is_readable(db_path):
    set_digest_topic(db_path, 111, "психология")

    assert get_digest_topic(db_path, 111) == "психология"


def test_digest_topic_can_be_replaced(db_path):
    set_digest_topic(db_path, 111, "психология")
    set_digest_topic(db_path, 111, "бухгалтерский учёт")

    assert get_digest_topic(db_path, 111) == "бухгалтерский учёт"


def test_digest_topic_is_scoped_per_user(db_path):
    set_digest_topic(db_path, 111, "психология")

    assert get_digest_topic(db_path, 222) is None


def test_get_users_with_digest_topic_returns_empty_list_when_none_set(db_path):
    assert get_users_with_digest_topic(db_path) == []


def test_get_users_with_digest_topic_returns_only_users_with_topic_set(db_path):
    set_digest_topic(db_path, 111, "психология")
    set_digest_topic(db_path, 222, "дизайн интерьеров")

    result = get_users_with_digest_topic(db_path)

    assert set(result) == {(111, "психология"), (222, "дизайн интерьеров")}
```

Append to `tests/test_storage_db.py` (find the existing migration tests for `channel_id`/`pending_media`/`onboarding_shown` and add a parallel one — read the file first to match its exact fixture style, then append):

```python
def test_init_db_migrates_existing_database_missing_digest_topic_column(tmp_path):
    import sqlite3

    from bot.storage.db import init_db

    db_path = str(tmp_path / "legacy.db")
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, interface_language TEXT, "
        "content_language TEXT, channel_id INTEGER, pending_media_file_id TEXT, "
        "pending_media_type TEXT, onboarding_shown INTEGER)"
    )
    connection.commit()
    connection.close()

    init_db(db_path)

    connection = sqlite3.connect(db_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    connection.close()
    assert "digest_topic" in columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage_users.py tests/test_storage_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_digest_topic'` (users) and `AssertionError: 'digest_topic' in columns` (db)

- [ ] **Step 3: Update `bot/storage/db.py`**

Add `digest_topic TEXT` to the `users` table in `SCHEMA` (in the `CREATE TABLE IF NOT EXISTS users (...)` block, after `onboarding_shown INTEGER`):

```python
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    interface_language TEXT,
    content_language TEXT,
    channel_id INTEGER,
    pending_media_file_id TEXT,
    pending_media_type TEXT,
    onboarding_shown INTEGER,
    digest_topic TEXT
);
```

Add a new migration function and call it from `init_db`:

```python
def _ensure_digest_topic_column(connection: sqlite3.Connection) -> None:
    # This feature (Plan.md-adjacent digest work, docs/superpowers/specs/
    # 2026-07-28-topic-digest-design.md) shipped after Phases 0-16 were
    # already deployed in production. CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "digest_topic" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN digest_topic TEXT")
```

```python
def init_db(db_path: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA)
        _ensure_channel_id_column(connection)
        _ensure_pending_media_columns(connection)
        _ensure_onboarding_shown_column(connection)
        _ensure_digest_topic_column(connection)
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Update `bot/storage/users.py`**

Append these three functions at the end of the file:

```python
def set_digest_topic(db_path: str, telegram_id: int, topic: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET digest_topic = ? WHERE telegram_id = ?",
            (topic, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_digest_topic(db_path: str, telegram_id: int) -> str | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT digest_topic FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def get_users_with_digest_topic(db_path: str) -> list[tuple[int, str]]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT telegram_id, digest_topic FROM users "
            "WHERE digest_topic IS NOT NULL AND digest_topic != ''"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]
    finally:
        connection.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_storage_users.py tests/test_storage_db.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/storage/db.py bot/storage/users.py tests/test_storage_users.py tests/test_storage_db.py
git commit -m "feat: add digest_topic column and storage functions"
```

---

### Task 2: Config — daily send hour

**Files:**
- Modify: `bot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.digest_send_hour: int` — consumed by Task 6 (scheduler wiring in `bot/main.py`).

- [ ] **Step 1: Write the failing test**

Read `tests/test_config.py` first to match its exact fixture/env-var style, then append:

```python
def test_digest_send_hour_defaults_to_9(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")

    settings = load_settings()

    assert settings.digest_send_hour == 9


def test_digest_send_hour_reads_from_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    monkeypatch.setenv("DIGEST_SEND_HOUR", "14")

    settings = load_settings()

    assert settings.digest_send_hour == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v -k digest_send_hour`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'digest_send_hour'`

- [ ] **Step 3: Update `bot/config.py`**

Add near the other `DEFAULT_*` constants:

```python
DEFAULT_DIGEST_SEND_HOUR = 9
```

Add a field to `Settings`:

```python
@dataclass(frozen=True)
class Settings:
    # ... existing fields unchanged ...
    site_media_dir: str
    digest_send_hour: int
```

In `load_settings`, add parsing (near the other `int(os.environ.get(...))` blocks — group it with `daily_limit`/`monthly_limit` parsing for consistency):

```python
    try:
        daily_limit = int(os.environ.get("DAILY_LIMIT", DEFAULT_DAILY_LIMIT))
        monthly_limit = int(os.environ.get("MONTHLY_LIMIT", DEFAULT_MONTHLY_LIMIT))
        digest_send_hour = int(os.environ.get("DIGEST_SEND_HOUR", DEFAULT_DIGEST_SEND_HOUR))
    except ValueError as exc:
        raise ConfigError(
            "DAILY_LIMIT, MONTHLY_LIMIT и DIGEST_SEND_HOUR должны быть целыми числами."
        ) from exc
```

(This replaces the existing `try/except` block that currently only parses `daily_limit`/`monthly_limit` — merge `digest_send_hour` into it rather than adding a second `try` block.)

Add the field to the final `return Settings(...)` call:

```python
    return Settings(
        # ... existing arguments unchanged ...
        site_media_dir=site_media_dir,
        digest_send_hour=digest_send_hour,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/config.py tests/test_config.py
git commit -m "feat: add DIGEST_SEND_HOUR config setting"
```

---

### Task 3: Locale strings

**Files:**
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`

**Interfaces:** none (pure data) — consumed via `bot.locales.loader.get_string` by Tasks 4, 5, 6.

- [ ] **Step 1: Update `bot/locales/ru.py`**

Remove the now-unused stub key `menu_news_digest_hint` (delete these lines):

```python
    "menu_news_digest_hint": (
        "Дайджест новостей пока в разработке — скоро я научусь собирать "
        "сводку ссылок и кратких вырезок свежих новостей по заданной теме."
    ),
```

Add these 12 new keys (anywhere convenient, e.g. right after `menu_news_digest_button`):

```python
    "menu_digest_write_topic_button": "Напиши интересующую тему",
    "menu_digest_change_topic_button": "Написать тему",
    "digest_prompt_no_topic": (
        "Чтобы собрать дайджест, сначала укажите тему, которая вам интересна."
    ),
    "digest_change_topic_prompt": "Хотите собрать дайджест по другой теме?",
    "digest_topic_input_prompt": "Напишите тему, по которой собрать дайджест:",
    "digest_topic_input_placeholder": "Например: психология",
    "digest_topic_saved": "Тема сохранена: «{topic}». Собираю дайджест...",
    "digest_title": "📋 Дайджест по теме «{topic}» за {date}",
    "digest_section_news": "📰 В новостях",
    "digest_section_papers": "🔬 Научные статьи",
    "digest_section_methods": "💡 Новые методики",
    "digest_empty_result": (
        "По теме «{topic}» сегодня ничего не нашлось. Попробуйте другую "
        "тему или загляните попозже."
    ),
```

- [ ] **Step 2: Update `bot/locales/en.py`**

Remove the `menu_news_digest_hint` key (same as above, English text). Add:

```python
    "menu_digest_write_topic_button": "Write the topic you're interested in",
    "menu_digest_change_topic_button": "Change topic",
    "digest_prompt_no_topic": (
        "To collect a digest, first tell me a topic you're interested in."
    ),
    "digest_change_topic_prompt": "Want to collect a digest on a different topic?",
    "digest_topic_input_prompt": "Write the topic to collect a digest for:",
    "digest_topic_input_placeholder": "For example: psychology",
    "digest_topic_saved": "Topic saved: \"{topic}\". Collecting the digest...",
    "digest_title": "📋 Digest on \"{topic}\" for {date}",
    "digest_section_news": "📰 In the news",
    "digest_section_papers": "🔬 Scientific papers",
    "digest_section_methods": "💡 New methods",
    "digest_empty_result": (
        "Nothing found on \"{topic}\" today. Try another topic or check "
        "back later."
    ),
```

- [ ] **Step 3: Update `bot/locales/vi.py`**

Remove the `menu_news_digest_hint` key (Vietnamese text). Add:

```python
    "menu_digest_write_topic_button": "Viết chủ đề bạn quan tâm",
    "menu_digest_change_topic_button": "Đổi chủ đề",
    "digest_prompt_no_topic": (
        "Để tổng hợp bản tin, trước tiên hãy cho tôi biết chủ đề bạn quan tâm."
    ),
    "digest_change_topic_prompt": "Bạn có muốn tổng hợp bản tin theo chủ đề khác không?",
    "digest_topic_input_prompt": "Viết chủ đề cần tổng hợp bản tin:",
    "digest_topic_input_placeholder": "Ví dụ: tâm lý học",
    "digest_topic_saved": "Đã lưu chủ đề: «{topic}». Đang tổng hợp bản tin...",
    "digest_title": "📋 Bản tin theo chủ đề «{topic}» ngày {date}",
    "digest_section_news": "📰 Trong tin tức",
    "digest_section_papers": "🔬 Bài báo khoa học",
    "digest_section_methods": "💡 Phương pháp mới",
    "digest_empty_result": (
        "Không tìm thấy gì về «{topic}» hôm nay. Hãy thử chủ đề khác hoặc "
        "quay lại sau."
    ),
```

- [ ] **Step 4: Update `bot/locales/zh.py`**

Remove the `menu_news_digest_hint` key (Chinese text). Add:

```python
    "menu_digest_write_topic_button": "写下您感兴趣的主题",
    "menu_digest_change_topic_button": "更换主题",
    "digest_prompt_no_topic": "要收集摘要，请先告诉我您感兴趣的主题。",
    "digest_change_topic_prompt": "要收集其他主题的摘要吗？",
    "digest_topic_input_prompt": "请写下要收集摘要的主题：",
    "digest_topic_input_placeholder": "例如：心理学",
    "digest_topic_saved": "主题已保存：「{topic}」。正在收集摘要……",
    "digest_title": "📋 关于「{topic}」的摘要（{date}）",
    "digest_section_news": "📰 新闻",
    "digest_section_papers": "🔬 科学文章",
    "digest_section_methods": "💡 新方法",
    "digest_empty_result": "今天没有找到关于「{topic}」的内容。请尝试其他主题或稍后再来看看。",
```

- [ ] **Step 5: Run the localization parity test**

Run: `pytest tests/test_localization.py -v`
Expected: PASS (all 4 locale files have identical key sets: −1 removed + 12 added = net +11 keys each)

- [ ] **Step 6: Run existing start/keyboard tests to confirm nothing broke yet**

Run: `pytest tests/test_handlers_start.py tests/test_keyboards_start.py -v`
Expected: `test_menu_news_digest_sends_hint_text` now FAILS (it asserts the removed `menu_news_digest_hint` key) — this is expected and will be fixed in Task 5, not this one. All other tests PASS.

- [ ] **Step 7: Commit**

```bash
git add bot/locales/ru.py bot/locales/en.py bot/locales/vi.py bot/locales/zh.py
git commit -m "feat: add digest locale strings, remove obsolete stub hint"
```

---

### Task 4: `bot/services/digest.py` — source fetching, synthesis, formatting

**Files:**
- Create: `bot/services/digest.py`
- Test: `tests/test_services_digest.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `bot.services.ai_gateway.generate_text`, `bot.services.ai_gateway.AIGatewayError`, `bot.locales.loader.get_string`.
- Produces: `DigestItem` (dataclass: `title: str`, `url: str`), `DigestResult` (dataclass: `topic: str`, `news: list[DigestItem]`, `papers: list[DigestItem]`, `methods_summary: str | None`), `fetch_viral_news(topic: str) -> list[DigestItem]`, `fetch_scientific_papers(topic: str) -> list[DigestItem]`, `synthesize_new_methods(news: list[DigestItem], papers: list[DigestItem], topic: str) -> str | None`, `build_digest(topic: str) -> DigestResult`, `format_digest_message(result: DigestResult, language: str) -> str` — all consumed by Task 5 (handlers) and Task 6 (scheduler).

- [ ] **Step 1: Add new dependencies to `requirements.txt`**

```
feedparser==6.0.11
```

(Append as a new line; `apscheduler` is added in Task 6, where it's first used.)

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_services_digest.py
from __future__ import annotations

import httpx
import pytest
import respx

from bot.services import digest
from bot.services.ai_gateway import AIGatewayTimeoutError

NEWS_URL = "https://news.google.com/rss/search"
PAPERS_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Google News</title>
<item>
<title>Новость про психологию №1</title>
<link>https://news.example.com/article-1</link>
<pubDate>Tue, 28 Jul 2026 08:00:00 GMT</pubDate>
</item>
<item>
<title>Новость про психологию №2</title>
<link>https://news.example.com/article-2</link>
<pubDate>Tue, 28 Jul 2026 07:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""


def _papers_payload(items: list[dict]) -> dict:
    return {"total": len(items), "offset": 0, "data": items}


# --- fetch_viral_news ---


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_parses_rss_entries():
    respx.get(NEWS_URL).mock(
        return_value=httpx.Response(200, content=RSS_SAMPLE.encode("utf-8"))
    )

    items = await digest.fetch_viral_news("психология")

    assert items == [
        digest.DigestItem(title="Новость про психологию №1", url="https://news.example.com/article-1"),
        digest.DigestItem(title="Новость про психологию №2", url="https://news.example.com/article-2"),
    ]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_caps_at_four_items():
    many_items = "".join(
        f"<item><title>Новость {i}</title><link>https://news.example.com/{i}</link></item>"
        for i in range(10)
    )
    rss = f"<?xml version=\"1.0\"?><rss version=\"2.0\"><channel>{many_items}</channel></rss>"
    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=rss.encode("utf-8")))

    items = await digest.fetch_viral_news("тема")

    assert len(items) == 4


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_returns_empty_list_for_empty_feed():
    empty_rss = "<?xml version=\"1.0\"?><rss version=\"2.0\"><channel></channel></rss>"
    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=empty_rss.encode("utf-8")))

    items = await digest.fetch_viral_news("тема")

    assert items == []


@respx.mock
@pytest.mark.asyncio
async def test_fetch_viral_news_raises_on_http_error():
    respx.get(NEWS_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(httpx.HTTPStatusError):
        await digest.fetch_viral_news("тема")


# --- fetch_scientific_papers ---


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_prefers_recent_sorted_by_citations():
    respx.get(PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_papers_payload(
                [
                    {"title": "Новый метод КПТ", "url": "https://s2.test/abc", "year": 2026, "citationCount": 5},
                    {"title": "Ещё одна статья 2026", "url": "https://s2.test/ghi", "year": 2026, "citationCount": 50},
                    {"title": "Старое исследование", "url": "https://s2.test/def", "year": 2020, "citationCount": 500},
                ]
            ),
        )
    )

    items = await digest.fetch_scientific_papers("психология")

    assert items == [
        digest.DigestItem(title="Ещё одна статья 2026", url="https://s2.test/ghi"),
        digest.DigestItem(title="Новый метод КПТ", url="https://s2.test/abc"),
    ]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_falls_back_to_all_when_none_recent():
    respx.get(PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_papers_payload(
                [{"title": "Старое исследование", "url": "https://s2.test/def", "year": 2020, "citationCount": 500}]
            ),
        )
    )

    items = await digest.fetch_scientific_papers("тема")

    assert items == [digest.DigestItem(title="Старое исследование", url="https://s2.test/def")]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_caps_at_three_items():
    payload = _papers_payload(
        [
            {"title": f"Статья {i}", "url": f"https://s2.test/{i}", "year": 2026, "citationCount": i}
            for i in range(10)
        ]
    )
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=payload))

    items = await digest.fetch_scientific_papers("тема")

    assert len(items) == 3


@respx.mock
@pytest.mark.asyncio
async def test_fetch_scientific_papers_returns_empty_list_for_no_results():
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=_papers_payload([])))

    items = await digest.fetch_scientific_papers("тема")

    assert items == []


# --- synthesize_new_methods ---


@pytest.mark.asyncio
async def test_synthesize_new_methods_returns_none_when_both_sources_empty():
    result = await digest.synthesize_new_methods([], [], "тема")

    assert result is None


@pytest.mark.asyncio
async def test_synthesize_new_methods_returns_none_when_ai_says_no(monkeypatch):
    from bot.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "generate_text", __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value="нет"))
    news = [digest.DigestItem(title="Новость", url="https://news.example.com/1")]

    result = await digest.synthesize_new_methods(news, [], "тема")

    assert result is None


@pytest.mark.asyncio
async def test_synthesize_new_methods_returns_ai_summary(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    monkeypatch.setattr(ai_gateway, "generate_text", AsyncMock(return_value="Используется новый формат коротких сессий."))
    news = [digest.DigestItem(title="Новость", url="https://news.example.com/1")]

    result = await digest.synthesize_new_methods(news, [], "тема")

    assert result == "Используется новый формат коротких сессий."


# --- build_digest: per-source failure isolation ---


@respx.mock
@pytest.mark.asyncio
async def test_build_digest_survives_news_source_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    respx.get(NEWS_URL).mock(return_value=httpx.Response(500))
    respx.get(PAPERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_papers_payload(
                [{"title": "Статья", "url": "https://s2.test/1", "year": 2026, "citationCount": 1}]
            ),
        )
    )
    monkeypatch.setattr(ai_gateway, "generate_text", AsyncMock(return_value="нет"))

    result = await digest.build_digest("тема")

    assert result.news == []
    assert len(result.papers) == 1


@respx.mock
@pytest.mark.asyncio
async def test_build_digest_survives_ai_synthesis_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=RSS_SAMPLE.encode("utf-8")))
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=_papers_payload([])))
    monkeypatch.setattr(ai_gateway, "generate_text", AsyncMock(side_effect=AIGatewayTimeoutError("timed out")))

    result = await digest.build_digest("тема")

    assert len(result.news) == 2
    assert result.methods_summary is None


@respx.mock
@pytest.mark.asyncio
async def test_build_digest_all_sources_empty(monkeypatch):
    from unittest.mock import AsyncMock

    from bot.services import ai_gateway

    empty_rss = "<?xml version=\"1.0\"?><rss version=\"2.0\"><channel></channel></rss>"
    respx.get(NEWS_URL).mock(return_value=httpx.Response(200, content=empty_rss.encode("utf-8")))
    respx.get(PAPERS_URL).mock(return_value=httpx.Response(200, json=_papers_payload([])))
    mock_generate = AsyncMock()
    monkeypatch.setattr(ai_gateway, "generate_text", mock_generate)

    result = await digest.build_digest("тема")

    assert result.news == []
    assert result.papers == []
    assert result.methods_summary is None
    mock_generate.assert_not_awaited()


# --- format_digest_message ---


def test_format_digest_message_includes_all_non_empty_sections():
    result = digest.DigestResult(
        topic="психология",
        news=[digest.DigestItem(title="Новость", url="https://news.example.com/1")],
        papers=[digest.DigestItem(title="Статья", url="https://s2.test/1")],
        methods_summary="Новый формат коротких сессий.",
    )

    text = digest.format_digest_message(result, "ru")

    assert "психология" in text
    assert "Новость" in text and "https://news.example.com/1" in text
    assert "Статья" in text and "https://s2.test/1" in text
    assert "Новый формат коротких сессий." in text


def test_format_digest_message_omits_empty_sections():
    result = digest.DigestResult(topic="тема", news=[], papers=[], methods_summary="Только методики.")

    text = digest.format_digest_message(result, "ru")

    from bot.locales.loader import get_string

    assert get_string("digest_section_news", "ru") not in text
    assert get_string("digest_section_papers", "ru") not in text
    assert "Только методики." in text


def test_format_digest_message_returns_empty_result_text_when_nothing_found():
    result = digest.DigestResult(topic="тема", news=[], papers=[], methods_summary=None)

    text = digest.format_digest_message(result, "ru")

    from bot.locales.loader import get_string

    assert text == get_string("digest_empty_result", "ru", topic="тема")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_services_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.services.digest'`

- [ ] **Step 4: Write `bot/services/digest.py`**

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import ai_gateway
from bot.services.ai_gateway import AIGatewayError

logger = logging.getLogger(LOGGER_NAME)

_HTTP_TIMEOUT_SECONDS = 15.0
_NEWS_RSS_URL = "https://news.google.com/rss/search"
_SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_MAX_NEWS_ITEMS = 4
_MAX_PAPER_ITEMS = 3

_METHODS_PROMPT_TEMPLATE = (
    "Вот список свежих новостей и научных статей по теме «{topic}»:\n\n"
    "Новости:\n{news_lines}\n\n"
    "Статьи:\n{paper_lines}\n\n"
    "На основе этого списка кратко (1-2 предложения) опиши на русском "
    "языке, какая новая методика, приём или подход упоминается. Если "
    "ничего похожего на новую методику не видно, ответь одним словом: "
    "\"нет\"."
)

_NO_METHODS_ANSWERS = {"нет", "нет.", "нет данных", "no", "no."}


@dataclass
class DigestItem:
    title: str
    url: str


@dataclass
class DigestResult:
    topic: str
    news: list[DigestItem]
    papers: list[DigestItem]
    methods_summary: str | None


async def fetch_viral_news(topic: str) -> list[DigestItem]:
    params = {"q": topic, "hl": "ru", "gl": "RU", "ceid": "RU:ru"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(_NEWS_RSS_URL, params=params)
        response.raise_for_status()

    parsed = feedparser.parse(response.content)
    items: list[DigestItem] = []
    for entry in parsed.entries[:_MAX_NEWS_ITEMS]:
        title = getattr(entry, "title", None)
        link = getattr(entry, "link", None)
        if title and link:
            items.append(DigestItem(title=title, url=link))
    return items


async def fetch_scientific_papers(topic: str) -> list[DigestItem]:
    params = {"query": topic, "fields": "title,url,citationCount,year", "limit": 20}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(_SEMANTIC_SCHOLAR_URL, params=params)
        response.raise_for_status()

    payload = response.json()
    papers = payload.get("data") or []

    current_year = datetime.now(timezone.utc).year
    recent = [p for p in papers if isinstance(p.get("year"), int) and p["year"] >= current_year - 1]
    candidates = recent if recent else papers
    candidates = sorted(candidates, key=lambda p: p.get("citationCount") or 0, reverse=True)

    items: list[DigestItem] = []
    for paper in candidates[:_MAX_PAPER_ITEMS]:
        title = paper.get("title")
        url = paper.get("url")
        if title and url:
            items.append(DigestItem(title=title, url=url))
    return items


def _format_items_for_prompt(items: list[DigestItem]) -> str:
    if not items:
        return "(пусто)"
    return "\n".join(f"- {item.title}" for item in items)


async def synthesize_new_methods(
    news: list[DigestItem], papers: list[DigestItem], topic: str
) -> str | None:
    if not news and not papers:
        return None

    prompt = _METHODS_PROMPT_TEMPLATE.format(
        topic=topic,
        news_lines=_format_items_for_prompt(news),
        paper_lines=_format_items_for_prompt(papers),
    )
    summary = await ai_gateway.generate_text(prompt)
    if summary.strip().lower().rstrip(".") in _NO_METHODS_ANSWERS:
        return None
    return summary


async def build_digest(topic: str) -> DigestResult:
    news_result, papers_result = await asyncio.gather(
        fetch_viral_news(topic), fetch_scientific_papers(topic), return_exceptions=True
    )

    if isinstance(news_result, BaseException):
        logger.warning(
            "Digest news source failed",
            extra={"operation": "digest_news", "error_class": type(news_result).__name__},
        )
        news: list[DigestItem] = []
    else:
        news = news_result

    if isinstance(papers_result, BaseException):
        logger.warning(
            "Digest papers source failed",
            extra={"operation": "digest_papers", "error_class": type(papers_result).__name__},
        )
        papers: list[DigestItem] = []
    else:
        papers = papers_result

    try:
        methods_summary = await synthesize_new_methods(news, papers, topic)
    except AIGatewayError as exc:
        logger.warning(
            "Digest methods synthesis failed",
            extra={"operation": "digest_methods", "error_class": type(exc).__name__},
        )
        methods_summary = None

    return DigestResult(topic=topic, news=news, papers=papers, methods_summary=methods_summary)


def _format_item_lines(items: list[DigestItem]) -> str:
    return "\n".join(f"{index}. {item.title} — {item.url}" for index, item in enumerate(items, start=1))


def format_digest_message(result: DigestResult, language: str) -> str:
    if not result.news and not result.papers and not result.methods_summary:
        return get_string("digest_empty_result", language, topic=result.topic)

    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    parts = [get_string("digest_title", language, topic=result.topic, date=today)]

    if result.news:
        parts.append(
            f"{get_string('digest_section_news', language)}\n{_format_item_lines(result.news)}"
        )
    if result.papers:
        parts.append(
            f"{get_string('digest_section_papers', language)}\n{_format_item_lines(result.papers)}"
        )
    if result.methods_summary:
        parts.append(f"{get_string('digest_section_methods', language)}\n{result.methods_summary}")

    return "\n\n".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services_digest.py -v`
Expected: PASS

- [ ] **Step 6: Install the new dependency locally and re-run**

Run: `pip install -r requirements.txt`
Run: `pytest tests/test_services_digest.py -v`
Expected: PASS (confirms `feedparser` installs cleanly)

- [ ] **Step 7: Commit**

```bash
git add bot/services/digest.py tests/test_services_digest.py requirements.txt
git commit -m "feat: add digest service (news RSS, Semantic Scholar, AI methods synthesis)"
```

---

### Task 5: Keyboard + handlers — button-driven UX

**Files:**
- Modify: `bot/keyboards/start.py`
- Modify: `bot/handlers/start.py`
- Modify: `tests/test_keyboards_start.py`
- Modify: `tests/test_handlers_start.py`

**Interfaces:**
- Consumes: `bot.services.digest.build_digest`, `bot.services.digest.format_digest_message`, `bot.storage.users.get_digest_topic`, `bot.storage.users.set_digest_topic`, `bot.handlers.refine._check_whitelist_or_reply`, `bot.handlers.refine._check_limit_or_reply`, `bot.storage.limits.increment_usage`.
- Produces: `CALLBACK_DIGEST_SET_TOPIC = "menu:digest_set_topic"`, `build_digest_topic_keyboard(lang: str, has_saved_topic: bool) -> InlineKeyboardMarkup`, `DigestStates` (`StatesGroup`) — consumed only within this task/file.

**Note on the two now-stale tests:** `test_menu_news_digest_sends_hint_text` and its whitelist-blocked counterpart in `tests/test_handlers_start.py` assert the old stub behavior (`menu_news_digest_hint`, now removed). This task replaces both with tests for the new behavior.

- [ ] **Step 1: Write the failing tests**

In `tests/test_keyboards_start.py`, add to the imports and append:

```python
from bot.keyboards.start import CALLBACK_DIGEST_SET_TOPIC, build_digest_topic_keyboard


def test_digest_topic_keyboard_shows_write_label_when_no_saved_topic():
    keyboard = build_digest_topic_keyboard("ru", has_saved_topic=False)

    assert keyboard.inline_keyboard[0][0].text == get_string("menu_digest_write_topic_button", "ru")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_DIGEST_SET_TOPIC


def test_digest_topic_keyboard_shows_change_label_when_topic_saved():
    keyboard = build_digest_topic_keyboard("en", has_saved_topic=True)

    assert keyboard.inline_keyboard[0][0].text == get_string("menu_digest_change_topic_button", "en")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_DIGEST_SET_TOPIC
```

In `tests/test_handlers_start.py`, first **replace** these two existing tests (they assert the removed stub key):

```python
@pytest.mark.asyncio
async def test_menu_news_digest_sends_hint_text(db_path):
    add_user(db_path, 2007)
    callback = _make_callback(2007, CALLBACK_NEWS_DIGEST)

    await on_menu_news_digest(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("menu_news_digest_hint", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_news_digest_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2008, CALLBACK_NEWS_DIGEST)

    await on_menu_news_digest(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
```

with (note: `AsyncMock` is already imported at the top of this file via `from unittest.mock import ANY, AsyncMock, call` — do not add a second import for it):

```python
from bot.handlers.start import DigestStates, on_digest_topic_input, on_menu_digest_set_topic
from bot.keyboards.start import CALLBACK_DIGEST_SET_TOPIC
from bot.services import digest as digest_service
from bot.storage.users import get_digest_topic, set_digest_topic


@pytest.mark.asyncio
async def test_menu_news_digest_prompts_for_topic_when_none_saved(db_path):
    add_user(db_path, 2007)
    callback = _make_callback(2007, CALLBACK_NEWS_DIGEST)

    await on_menu_news_digest(callback, db_path)

    callback.message.answer.assert_awaited_once_with(
        get_string("digest_prompt_no_topic", "ru"), reply_markup=ANY
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_news_digest_blocked_when_not_whitelisted(db_path):
    callback = _make_callback(2008, CALLBACK_NEWS_DIGEST)

    await on_menu_news_digest(callback, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))


@pytest.mark.asyncio
async def test_menu_news_digest_builds_digest_immediately_when_topic_saved(db_path, monkeypatch):
    # _check_limit_or_reply (bot/handlers/refine.py) calls load_settings()
    # internally, same as test_menu_create_post_shows_submenu_keyboard above —
    # required env vars must be set or ConfigError raises before the handler
    # body even runs.
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")
    add_user(db_path, 2009)
    set_digest_topic(db_path, 2009, "психология")
    callback = _make_callback(2009, CALLBACK_NEWS_DIGEST)

    fake_result = digest_service.DigestResult(topic="психология", news=[], papers=[], methods_summary=None)
    mock_build = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(digest_service, "build_digest", mock_build)

    await on_menu_news_digest(callback, db_path)

    mock_build.assert_awaited_once_with("психология")
    assert callback.message.answer.await_count == 2
    first_call_text = callback.message.answer.await_args_list[0].args[0]
    assert first_call_text == digest_service.format_digest_message(fake_result, "ru")
    second_call_args, second_call_kwargs = callback.message.answer.await_args_list[1]
    assert second_call_args[0] == get_string("digest_change_topic_prompt", "ru")
    assert "reply_markup" in second_call_kwargs
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_digest_set_topic_sends_force_reply_and_sets_state(db_path):
    from aiogram.types import ForceReply

    add_user(db_path, 2010)
    state = _make_state(2010)
    callback = _make_callback(2010, CALLBACK_DIGEST_SET_TOPIC)

    await on_menu_digest_set_topic(callback, state, db_path)

    callback.message.answer.assert_awaited_once()
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("digest_topic_input_prompt", "ru")
    assert isinstance(kwargs["reply_markup"], ForceReply)
    assert await state.get_state() == DigestStates.waiting_for_topic.state
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_menu_digest_set_topic_blocked_when_not_whitelisted(db_path):
    state = _make_state(2011)
    callback = _make_callback(2011, CALLBACK_DIGEST_SET_TOPIC)

    await on_menu_digest_set_topic(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_digest_topic_input_saves_topic_and_sends_digest(db_path, monkeypatch):
    state = _make_state(2012)
    await state.update_data(language="ru")
    await state.set_state(DigestStates.waiting_for_topic)

    fake_result = digest_service.DigestResult(topic="дизайн интерьеров", news=[], papers=[], methods_summary=None)
    mock_build = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(digest_service, "build_digest", mock_build)

    message = _make_description_message(2012, "дизайн интерьеров")

    await on_digest_topic_input(message, state, db_path)

    assert get_digest_topic(db_path, 2012) == "дизайн интерьеров"
    mock_build.assert_awaited_once_with("дизайн интерьеров")
    assert await state.get_state() is None
    assert message.answer.await_count == 2
    first_call_text = message.answer.await_args_list[0].args[0]
    assert first_call_text == get_string("digest_topic_saved", "ru", topic="дизайн интерьеров")


@pytest.mark.asyncio
async def test_digest_topic_input_reprompts_on_empty_text(db_path, monkeypatch):
    from aiogram.types import ForceReply

    state = _make_state(2013)
    await state.update_data(language="ru")
    await state.set_state(DigestStates.waiting_for_topic)
    mock_build = AsyncMock()
    monkeypatch.setattr(digest_service, "build_digest", mock_build)

    message = _make_description_message(2013, None)

    await on_digest_topic_input(message, state, db_path)

    mock_build.assert_not_awaited()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("digest_topic_input_prompt", "ru")
    assert isinstance(kwargs["reply_markup"], ForceReply)
    assert await state.get_state() == DigestStates.waiting_for_topic.state


@pytest.mark.asyncio
async def test_start_clears_fsm_state_stuck_in_digest_topic_input(db_path):
    state = _make_state(2014)
    await state.update_data(language="ru")
    await state.set_state(DigestStates.waiting_for_topic)
    message = _make_message(2014, "ru")

    await cmd_start(message, state, db_path)

    assert await state.get_state() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_keyboards_start.py tests/test_handlers_start.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_digest_topic_keyboard'` (and similar for the handler-side imports)

- [ ] **Step 3: Update `bot/keyboards/start.py`**

Add the new callback constant near the others:

```python
CALLBACK_DIGEST_SET_TOPIC = "menu:digest_set_topic"
```

Append the new keyboard builder at the end of the file:

```python
def build_digest_topic_keyboard(lang: str, has_saved_topic: bool) -> InlineKeyboardMarkup:
    label_key = (
        "menu_digest_change_topic_button" if has_saved_topic else "menu_digest_write_topic_button"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string(label_key, lang),
                    callback_data=CALLBACK_DIGEST_SET_TOPIC,
                )
            ]
        ]
    )
```

- [ ] **Step 4: Update `bot/handlers/start.py`**

Add these imports (merge into the existing import block — do not duplicate an existing `from X import` line, extend it):

```python
from aiogram.types import ForceReply

from bot.keyboards.start import (
    CALLBACK_DIGEST_SET_TOPIC,
    build_digest_topic_keyboard,
)
from bot.handlers.refine import _check_limit_or_reply
from bot.services import digest
from bot.storage.limits import increment_usage
from bot.storage.users import get_digest_topic, set_digest_topic
```

Add the new states class near `PhotoGenStates`:

```python
class DigestStates(StatesGroup):
    waiting_for_topic = State()
```

Replace the existing stub handler:

```python
@router.callback_query(F.data == CALLBACK_NEWS_DIGEST)
async def on_menu_news_digest(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await callback.message.answer(get_string("menu_news_digest_hint", language))
    await callback.answer()
```

with:

```python
@router.callback_query(F.data == CALLBACK_NEWS_DIGEST)
async def on_menu_news_digest(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    topic = get_digest_topic(db_path, telegram_id)
    if topic is None:
        await callback.message.answer(
            get_string("digest_prompt_no_topic", language),
            reply_markup=build_digest_topic_keyboard(language, has_saved_topic=False),
        )
        await callback.answer()
        return

    if not await _check_limit_or_reply(callback, db_path, language):
        return

    result = await digest.build_digest(topic)
    increment_usage(db_path, telegram_id)

    await callback.message.answer(digest.format_digest_message(result, language))
    await callback.message.answer(
        get_string("digest_change_topic_prompt", language),
        reply_markup=build_digest_topic_keyboard(language, has_saved_topic=True),
    )
    await callback.answer()


@router.callback_query(F.data == CALLBACK_DIGEST_SET_TOPIC)
async def on_menu_digest_set_topic(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await state.update_data(language=language)
    await state.set_state(DigestStates.waiting_for_topic)
    await callback.message.answer(
        get_string("digest_topic_input_prompt", language),
        reply_markup=ForceReply(
            input_field_placeholder=get_string("digest_topic_input_placeholder", language)
        ),
    )
    await callback.answer()


@router.message(DigestStates.waiting_for_topic)
async def on_digest_topic_input(message: Message, state: FSMContext, db_path: str) -> None:
    telegram_id = message.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, message.from_user.language_code
    )
    topic = (message.text or "").strip()

    if not topic:
        await message.answer(
            get_string("digest_topic_input_prompt", language),
            reply_markup=ForceReply(
                input_field_placeholder=get_string("digest_topic_input_placeholder", language)
            ),
        )
        return

    set_digest_topic(db_path, telegram_id, topic)
    await state.set_state(None)
    await message.answer(get_string("digest_topic_saved", language, topic=topic))

    result = await digest.build_digest(topic)
    await message.answer(digest.format_digest_message(result, language))
```

(`CALLBACK_NEWS_DIGEST` stays imported and used exactly as before — only the handler body changes.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_start.py tests/test_handlers_start.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: PASS — no other test file references the old stub behavior.

- [ ] **Step 7: Commit**

```bash
git add bot/keyboards/start.py bot/handlers/start.py tests/test_keyboards_start.py tests/test_handlers_start.py
git commit -m "feat: wire digest button to real topic-input and on-demand digest flow"
```

---

### Task 6: Daily scheduler

**Files:**
- Create: `bot/services/digest_scheduler.py`
- Modify: `bot/main.py`
- Test: `tests/test_services_digest_scheduler.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `bot.services.digest.build_digest`, `bot.services.digest.format_digest_message`, `bot.storage.users.get_users_with_digest_topic`, `bot.storage.users.get_interface_language`, `bot.storage.whitelist.is_whitelisted`, `bot.config.Settings.digest_send_hour`.
- Produces: `build_digest_scheduler(bot: Bot, db_path: str, hour: int) -> AsyncIOScheduler` — consumed by `bot/main.py`'s `run()`.

- [ ] **Step 1: Add `apscheduler` to `requirements.txt`**

```
apscheduler==3.10.4
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_services_digest_scheduler.py
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.cron import CronTrigger

from bot.services import digest as digest_service
from bot.services.digest_scheduler import _send_daily_digests, build_digest_scheduler
from bot.storage.users import set_digest_topic, set_interface_language
from bot.storage.whitelist import add_user


def test_build_digest_scheduler_registers_daily_cron_job(db_path):
    bot = AsyncMock()

    scheduler = build_digest_scheduler(bot, db_path, hour=9)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "daily_digest"
    assert isinstance(job.trigger, CronTrigger)
    assert str(job.trigger.timezone) == "Europe/Moscow"


@pytest.mark.asyncio
async def test_send_daily_digests_skips_non_whitelisted_users(db_path, monkeypatch):
    set_digest_topic(db_path, 111, "психология")  # never whitelisted
    mock_build = AsyncMock()
    monkeypatch.setattr(digest_service, "build_digest", mock_build)
    bot = AsyncMock()

    await _send_daily_digests(bot, db_path)

    mock_build.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_daily_digests_sends_to_whitelisted_users_with_topic(db_path, monkeypatch):
    add_user(db_path, 222)
    set_digest_topic(db_path, 222, "бухгалтерский учёт")
    set_interface_language(db_path, 222, "en")
    fake_result = digest_service.DigestResult(
        topic="бухгалтерский учёт", news=[], papers=[], methods_summary=None
    )
    mock_build = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(digest_service, "build_digest", mock_build)
    bot = AsyncMock()

    await _send_daily_digests(bot, db_path)

    mock_build.assert_awaited_once_with("бухгалтерский учёт")
    bot.send_message.assert_awaited_once_with(
        222, digest_service.format_digest_message(fake_result, "en")
    )


@pytest.mark.asyncio
async def test_send_daily_digests_continues_after_one_user_fails(db_path, monkeypatch):
    add_user(db_path, 333)
    add_user(db_path, 444)
    set_digest_topic(db_path, 333, "дизайн")
    set_digest_topic(db_path, 444, "строительство")

    async def _build(topic: str):
        if topic == "дизайн":
            raise RuntimeError("boom")
        return digest_service.DigestResult(topic=topic, news=[], papers=[], methods_summary=None)

    monkeypatch.setattr(digest_service, "build_digest", _build)
    bot = AsyncMock()

    await _send_daily_digests(bot, db_path)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 444
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_services_digest_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.services.digest_scheduler'`

- [ ] **Step 4: Write `bot/services/digest_scheduler.py`**

```python
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.locales.loader import DEFAULT_LANGUAGE
from bot.logging_config import LOGGER_NAME
from bot.services import digest
from bot.storage.users import get_interface_language, get_users_with_digest_topic
from bot.storage.whitelist import is_whitelisted

logger = logging.getLogger(LOGGER_NAME)


async def _send_daily_digests(bot: Bot, db_path: str) -> None:
    for telegram_id, topic in get_users_with_digest_topic(db_path):
        if not is_whitelisted(db_path, telegram_id):
            continue

        language = get_interface_language(db_path, telegram_id) or DEFAULT_LANGUAGE
        try:
            result = await digest.build_digest(topic)
            await bot.send_message(telegram_id, digest.format_digest_message(result, language))
        except Exception:
            logger.warning(
                "Daily digest failed for user",
                extra={"user_id": telegram_id, "operation": "daily_digest"},
                exc_info=True,
            )


def build_digest_scheduler(bot: Bot, db_path: str, hour: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _send_daily_digests,
        trigger=CronTrigger(hour=hour, minute=0, timezone="Europe/Moscow"),
        args=[bot, db_path],
        id="daily_digest",
    )
    return scheduler
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services_digest_scheduler.py -v`
Expected: PASS

- [ ] **Step 6: Wire the scheduler into `bot/main.py`**

Add the import:

```python
from bot.services.digest_scheduler import build_digest_scheduler
```

In `run()`, after `dispatcher = build_dispatcher(...)` and before `site_api_app = build_site_api_app(...)`, add:

```python
    digest_scheduler = build_digest_scheduler(bot, settings.db_path, settings.digest_send_hour)
    digest_scheduler.start()
```

In the `finally` block (currently `await runner.cleanup()` then `await bot.session.close()`), add the scheduler shutdown first:

```python
    finally:
        digest_scheduler.shutdown()
        await runner.cleanup()
        await bot.session.close()
```

- [ ] **Step 7: Update `tests/test_main_site_api_wiring.py` so its `run()` tests don't spin up a real scheduler**

Both tests in this file call the real `run()` and patch out `Bot`/`web.TCPSite`/`web.AppRunner`/`Dispatcher.start_polling` — without also patching `build_digest_scheduler`, `run()` would start a real (harmless but unnecessary) `AsyncIOScheduler` background thread during the test. Add one more patch to each test's `with patch(...)` block.

In `test_run_starts_site_api_server_alongside_polling`, change:

```python
    with patch("bot.main.Bot") as mock_bot_cls, patch(
        "bot.main.web.TCPSite"
    ) as mock_tcp_site_cls, patch("bot.main.web.AppRunner") as mock_runner_cls, patch(
        "aiogram.Dispatcher.start_polling", new_callable=AsyncMock
    ) as mock_start_polling:
```

to:

```python
    with patch("bot.main.Bot") as mock_bot_cls, patch(
        "bot.main.web.TCPSite"
    ) as mock_tcp_site_cls, patch("bot.main.web.AppRunner") as mock_runner_cls, patch(
        "aiogram.Dispatcher.start_polling", new_callable=AsyncMock
    ) as mock_start_polling, patch(
        "bot.main.build_digest_scheduler"
    ) as mock_scheduler_factory:
```

and add this assertion after `mock_runner.cleanup.assert_awaited_once()`:

```python
        mock_scheduler_factory.return_value.start.assert_called_once()
        mock_scheduler_factory.return_value.shutdown.assert_called_once()
```

Apply the identical change (same `with patch(...)` extension) to `test_run_configures_native_menu_button_before_polling` — no new assertions needed there, just the extra patch so the test doesn't start a real scheduler.

- [ ] **Step 8: Run the full suite**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 9: Install the new dependency locally and re-run**

Run: `pip install -r requirements.txt`
Run: `pytest -v`
Expected: PASS (confirms `apscheduler` installs cleanly)

- [ ] **Step 10: Commit**

```bash
git add bot/services/digest_scheduler.py bot/main.py tests/test_services_digest_scheduler.py requirements.txt
git commit -m "feat: add daily digest scheduler (APScheduler, in-process)"
```

---

### Task 7: Full suite run and manual verification checklist

**Files:** none modified — verification only.

- [ ] **Step 1: Run the complete automated test suite**

Run: `pytest -v`
Expected: PASS — every test file, including every test added/changed in Tasks 1-6, plus every pre-existing test file unchanged and still green.

- [ ] **Step 2: Manual verification checklist (requires the real production server and a real Telegram account — not automatable)**

Write this checklist into `buttons.md` (the project's existing journal for this button, per its "Журнал сессии" section) once deployed, and walk the owner through it:

1. Deploy this branch to production (existing CI/CD handles this on push to `feature/mvp1-bot`).
2. Open the bot, tap "Собрать дайджест свежих новостей" for the first time (no saved topic yet) — confirm a message appears inviting you to write a topic, with a "Напиши интересующую тему" button.
3. Tap that button — confirm a message appears with an already-open reply/edit field (Telegram's `ForceReply`) showing the placeholder "Например: психология".
4. Type "психология" and send — confirm: a "Тема сохранена" confirmation, then a digest message with news/papers/methods sections (whichever pillars returned results that day), then... — no additional message needed here since the "Написать тему" follow-up only appears on the *button* path, not this one (confirm this matches expectations, or flag for a follow-up UX tweak if the owner wants a "change topic" option shown here too).
5. Tap "Собрать дайджест свежих новостей" again — confirm the digest is now built and sent **immediately** using the saved "психология" topic (no re-prompt), followed by a "Написать тему" button to change it.
6. Tap "Написать тему" and enter a different topic (e.g. "бухгалтерский учёт") — confirm the new topic replaces the old one and a fresh digest is sent.
7. Wait for (or temporarily set `DIGEST_SEND_HOUR` close to the current server time to test sooner) the daily scheduled time — confirm the bot sends an unprompted digest message automatically, matching the currently saved topic.
8. Confirm a non-whitelisted test account cannot trigger any of the above (gets the standard "not whitelisted" message).

- [ ] **Step 3: Report results to the owner**

Summarize pass/fail for each checklist item in plain Russian. The Yandex Wordstat "search queries" pillar remains explicitly deferred (per the design spec) until Yandex approves API access — not a bug, a known follow-up.
