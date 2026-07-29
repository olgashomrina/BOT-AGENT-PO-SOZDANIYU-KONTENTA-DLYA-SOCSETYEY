# Per-message refine context — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make the refine buttons ("Ещё", "Короче") regenerate from the source of the post they are attached to, instead of from a single shared FSM value that the next generation overwrites.

**Architecture:** A new sqlite table stores one row per sent variant message, keyed by `(chat_id, message_id)`. `send_variants` writes a row for every variant it sends; the refine handlers read the row for the message their button sits under. The shared FSM keys `source_text` / `content_language` / `with_hashtags` stop being the refine handlers' source of truth.

**Tech Stack:** Python, aiogram 3, sqlite3, pytest.

## Why this is needed

Found by the final review of the authored-post feature.

`bot/handlers/refine.py::_generate_and_send` reads `source_text` from FSM data, which is per chat, not per message. Both `bot/handlers/content.py::_finish` and `bot/handlers/authorpost.py::on_authorpost_platform` overwrite it. Telegram keeps old messages and their inline buttons alive indefinitely, so:

- Generate post A → generate post B → tap "Ещё" under A ⇒ a "regeneration of A" that is actually about B. Pre-existing, predates the authored-post feature.
- Generate an authored post (hashtags) → send an ordinary link (no hashtags) → tap "Ещё" under the authored post ⇒ hashtags silently lost. Introduced by the authored-post feature.
- The reverse order puts hashtags on an ordinary post the user never asked to tag.

## Global Constraints

- Run tests with `python -m pytest` from the repository root.
- Every storage function opens its connection with `get_connection(db_path)` and closes it in a `finally` block.
- SQL uses parameter binding, never string interpolation.
- All user-visible text comes from `get_string(key, lang)`.
- Comments explain WHY, not what.
- A different effort is working in this same directory. Stage only the files each task names, by name. Never `git add -A` or `git add .`.

---

### Task 1: Refine-context storage

**Files:**
- Create: `bot/storage/refine_context.py`
- Modify: `bot/storage/db.py` (add table to `SCHEMA`)
- Test: `tests/test_storage_refine_context.py` (new)

**Interfaces produced:**
- `save_refine_context(db_path, chat_id, message_id, source_text, content_language, with_hashtags, platform) -> None`
- `get_refine_context(db_path, chat_id, message_id) -> dict | None` returning keys `source_text`, `content_language`, `with_hashtags` (bool), `platform`
- `MAX_CONTEXTS_PER_CHAT = 200`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from bot.storage.refine_context import (
    MAX_CONTEXTS_PER_CHAT,
    get_refine_context,
    save_refine_context,
)

CHAT_ID = 555


def test_saved_context_round_trips(db_path):
    save_refine_context(db_path, CHAT_ID, 10, "Исходник", "ru", True, "telegram")

    context = get_refine_context(db_path, CHAT_ID, 10)

    assert context == {
        "source_text": "Исходник",
        "content_language": "ru",
        "with_hashtags": True,
        "platform": "telegram",
    }


def test_missing_context_returns_none(db_path):
    assert get_refine_context(db_path, CHAT_ID, 999) is None


def test_with_hashtags_round_trips_as_bool_not_int(db_path):
    save_refine_context(db_path, CHAT_ID, 11, "Исходник", "ru", False, "vk")

    context = get_refine_context(db_path, CHAT_ID, 11)

    assert context["with_hashtags"] is False


def test_contexts_are_isolated_between_chats(db_path):
    save_refine_context(db_path, CHAT_ID, 12, "Мой", "ru", True, "telegram")
    save_refine_context(db_path, 777, 12, "Чужой", "en", False, "vk")

    assert get_refine_context(db_path, CHAT_ID, 12)["source_text"] == "Мой"
    assert get_refine_context(db_path, 777, 12)["source_text"] == "Чужой"


def test_saving_same_message_twice_overwrites(db_path):
    save_refine_context(db_path, CHAT_ID, 13, "Первый", "ru", True, "telegram")
    save_refine_context(db_path, CHAT_ID, 13, "Второй", "en", False, "vk")

    context = get_refine_context(db_path, CHAT_ID, 13)

    assert context["source_text"] == "Второй"
    assert context["content_language"] == "en"


def test_oldest_contexts_are_evicted_past_the_cap(db_path):
    for message_id in range(1, MAX_CONTEXTS_PER_CHAT + 2):
        save_refine_context(db_path, CHAT_ID, message_id, f"Пост {message_id}", "ru", False, "telegram")

    # The very first message's context is gone, the newest survives.
    assert get_refine_context(db_path, CHAT_ID, 1) is None
    assert get_refine_context(db_path, CHAT_ID, MAX_CONTEXTS_PER_CHAT + 1) is not None


def test_eviction_does_not_touch_other_chats(db_path):
    save_refine_context(db_path, 777, 1, "Чужой", "ru", False, "telegram")
    for message_id in range(1, MAX_CONTEXTS_PER_CHAT + 2):
        save_refine_context(db_path, CHAT_ID, message_id, f"Пост {message_id}", "ru", False, "telegram")

    assert get_refine_context(db_path, 777, 1) is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_storage_refine_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.refine_context'`

- [ ] **Step 3: Add the table to the schema**

In `bot/storage/db.py`, append this table to the `SCHEMA` string, after the `site_content` table and still inside the triple-quoted string:

```sql
CREATE TABLE IF NOT EXISTS refine_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    content_language TEXT NOT NULL,
    with_hashtags INTEGER NOT NULL,
    platform TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (chat_id, message_id)
);
```

No migration helper is needed: this is a brand-new table, and `CREATE TABLE IF NOT EXISTS` covers both fresh installs and already-deployed databases. The existing `_ensure_*_column` helpers exist only because those were new COLUMNS on tables that already shipped.

- [ ] **Step 4: Write the storage module**

Create `bot/storage/refine_context.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection

# Telegram keeps inline buttons alive on old messages indefinitely, so this
# table would otherwise grow without bound. The cap is per chat and generous
# enough that a user would have to generate hundreds of posts in one chat
# before the oldest buttons stop working — at which point regenerating from a
# months-old message is not a use case worth the storage.
MAX_CONTEXTS_PER_CHAT = 200


def save_refine_context(
    db_path: str,
    chat_id: int,
    message_id: int,
    source_text: str,
    content_language: str,
    with_hashtags: bool,
    platform: str,
) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        # UPSERT rather than plain INSERT: a message id is unique per chat, but
        # re-saving the same one must not raise — it simply means the same
        # variant message was recorded twice.
        connection.execute(
            "INSERT INTO refine_contexts "
            "(chat_id, message_id, source_text, content_language, with_hashtags, platform, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (chat_id, message_id) DO UPDATE SET "
            "source_text = excluded.source_text, "
            "content_language = excluded.content_language, "
            "with_hashtags = excluded.with_hashtags, "
            "platform = excluded.platform, "
            "created_at = excluded.created_at",
            (
                chat_id,
                message_id,
                source_text,
                content_language,
                int(with_hashtags),
                platform,
                created_at,
            ),
        )
        # Eviction keyed on id (insertion order), not created_at: sqlite's TEXT
        # timestamp cannot disambiguate two inserts inside the same clock tick,
        # but AUTOINCREMENT id always can. Same reasoning as
        # bot/storage/style_examples.py.
        connection.execute(
            "DELETE FROM refine_contexts WHERE chat_id = ? AND id NOT IN ("
            "SELECT id FROM refine_contexts WHERE chat_id = ? ORDER BY id DESC LIMIT ?)",
            (chat_id, chat_id, MAX_CONTEXTS_PER_CHAT),
        )
        connection.commit()
    finally:
        connection.close()


def get_refine_context(db_path: str, chat_id: int, message_id: int) -> dict | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT source_text, content_language, with_hashtags, platform "
            "FROM refine_contexts WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "source_text": row[0],
            "content_language": row[1],
            # sqlite has no bool type: the column round-trips as 0/1, and
            # callers pass this straight to the generator, which treats it as
            # a bool. Convert here so no caller has to remember.
            "with_hashtags": bool(row[2]),
            "platform": row[3],
        }
    finally:
        connection.close()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_storage_refine_context.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add bot/storage/refine_context.py bot/storage/db.py tests/test_storage_refine_context.py
git commit -m "feat: add per-message refine context storage"
```

---

### Task 2: Record context when variants are sent

**Files:**
- Modify: `bot/handlers/content.py` (`send_variants`, `_finish`)
- Test: `tests/test_handlers_content_flow.py`

**Interfaces consumed:** `save_refine_context` from Task 1.

**Interfaces produced:** `send_variants(message, language, platform, variants, db_path, source_text, content_language, with_hashtags)` — the four new parameters are all required keyword-or-positional; every caller must pass them.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_handlers_content_flow.py`:

```python
@pytest.mark.asyncio
async def test_send_variants_records_context_for_each_sent_message(db_path):
    message = _make_message()
    sent = [SimpleNamespace(message_id=101), SimpleNamespace(message_id=102)]
    message.answer = AsyncMock(side_effect=sent)
    message.chat = SimpleNamespace(id=CHAT_ID)

    await content_module.send_variants(
        message,
        "ru",
        "telegram",
        ["Первый", "Второй"],
        db_path=db_path,
        source_text="Исходник",
        content_language="ru",
        with_hashtags=True,
    )

    for message_id in (101, 102):
        context = get_refine_context(db_path, CHAT_ID, message_id)
        assert context["source_text"] == "Исходник"
        assert context["with_hashtags"] is True
        assert context["platform"] == "telegram"
```

Add `CHAT_ID = 222` near the file's other constants, and import `get_refine_context` and `SimpleNamespace` if not already imported.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_handlers_content_flow.py::test_send_variants_records_context_for_each_sent_message -v`
Expected: FAIL — `send_variants` does not accept `db_path`.

- [ ] **Step 3: Update `send_variants`**

Replace `send_variants` in `bot/handlers/content.py` with:

```python
async def send_variants(
    message: Message,
    language: str,
    platform: str,
    variants: list[str],
    db_path: str,
    source_text: str,
    content_language: str,
    with_hashtags: bool,
) -> None:
    for index, variant in enumerate(variants, start=1):
        # WHY the sent message is captured and recorded: the refine buttons
        # attached below regenerate from the source of THIS post. Telegram
        # keeps old messages and their buttons alive indefinitely, so a single
        # shared per-chat value would be overwritten by the next generation and
        # a later tap would regenerate the wrong thing entirely.
        sent = await message.answer(
            output_formatter.format_variant(variant),
            parse_mode=output_formatter.PARSE_MODE,
            reply_markup=build_refine_keyboard(platform, index, language),
        )
        save_refine_context(
            db_path,
            message.chat.id,
            sent.message_id,
            source_text,
            content_language,
            with_hashtags,
            platform,
        )
```

Add `from bot.storage.refine_context import save_refine_context` to the imports.

- [ ] **Step 4: Update `_finish`'s two calls**

In `_finish`, change both calls to pass the new arguments:

```python
    await send_variants(
        message,
        language,
        "telegram",
        telegram_variants,
        db_path=db_path,
        source_text=text,
        content_language=content_language,
        with_hashtags=False,
    )
    await send_variants(
        message,
        language,
        "vk",
        vk_variants,
        db_path=db_path,
        source_text=text,
        content_language=content_language,
        with_hashtags=False,
    )
```

- [ ] **Step 5: Fix the existing `send_variants` test**

`test_send_variants_sends_one_message_per_variant_with_refine_keyboard` now needs the new arguments. Add them, and set `message.chat = SimpleNamespace(id=CHAT_ID)` plus a `message.answer` side effect returning objects with `message_id`. Do NOT weaken any of its existing assertions — it must still pin the escaping and the per-index callback data.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_handlers_content_flow.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bot/handlers/content.py tests/test_handlers_content_flow.py
git commit -m "feat: record refine context for every sent variant"
```

---

### Task 3: Refine reads the context of its own message

**Files:**
- Modify: `bot/handlers/refine.py`
- Test: `tests/test_handlers_refine.py`

**Interfaces consumed:** `get_refine_context`, `save_refine_context` from Task 1.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_handlers_refine.py`:

```python
@pytest.mark.asyncio
async def test_refine_more_uses_the_context_of_its_own_message(db_path, monkeypatch):
    state = _make_state()
    # Two posts generated in sequence: the second overwrites any shared value.
    save_refine_context(db_path, CHAT_ID, 10, "Первый исходник", "ru", True, "telegram")
    save_refine_context(db_path, CHAT_ID, 20, "Второй исходник", "en", False, "vk")

    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    # The button under the FIRST post is tapped.
    callback = _make_callback(data="refine:more:telegram:1")
    callback.message.message_id = 10
    callback.message.chat = SimpleNamespace(id=CHAT_ID)

    await on_refine_more(callback, state, db_path)

    assert mock_generate.await_args.args[0] == "Первый исходник"
    assert mock_generate.await_args.kwargs["with_hashtags"] is True


@pytest.mark.asyncio
async def test_refine_without_stored_context_reports_missing_context(db_path, monkeypatch):
    state = _make_state()
    mock_generate = AsyncMock(return_value=["Новый вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    callback.message.message_id = 999
    callback.message.chat = SimpleNamespace(id=CHAT_ID)

    await on_refine_more(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("error_refine_missing_context", "ru")
    )


@pytest.mark.asyncio
async def test_refine_records_context_for_the_message_it_sends(db_path, monkeypatch):
    state = _make_state()
    save_refine_context(db_path, CHAT_ID, 10, "Первый исходник", "ru", True, "telegram")
    monkeypatch.setattr(
        content_generator, "generate_variants", AsyncMock(return_value=["Новый вариант"])
    )

    callback = _make_callback(data="refine:more:telegram:1")
    callback.message.message_id = 10
    callback.message.chat = SimpleNamespace(id=CHAT_ID)
    callback.message.answer = AsyncMock(return_value=SimpleNamespace(message_id=30))

    await on_refine_more(callback, state, db_path)

    # The freshly sent variant carries its own buttons, so it needs its own
    # context row — otherwise refining a refinement would report "missing".
    assert get_refine_context(db_path, CHAT_ID, 30)["source_text"] == "Первый исходник"
```

Add `CHAT_ID = 333` near the file's other constants and import what is needed.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_handlers_refine.py -k "own_message or missing_context or records_context" -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite `_generate_and_send`'s context lookup**

In `bot/handlers/refine.py::_generate_and_send`, replace the block that reads `source_text` and `content_language` from FSM data, and the `style_examples` / `with_hashtags` lines added earlier, with a lookup keyed on the message the button sits under:

```python
    # WHY the context is keyed on this message rather than read from FSM: FSM
    # data is per chat, so the next generation overwrites it. Telegram keeps
    # old buttons alive indefinitely, so a tap on an older post would otherwise
    # regenerate from whatever was generated most recently — a different topic,
    # and with hashtags added or dropped to match that other post.
    context = get_refine_context(db_path, callback.message.chat.id, callback.message.message_id)
    if context is None:
        await callback.message.answer(get_string("error_refine_missing_context", language))
        await _safe_answer(callback)
        return

    source_text = context["source_text"]
    content_language = context["content_language"]
    with_hashtags = context["with_hashtags"]
    style_examples = get_style_examples(db_path, telegram_id)
```

Then, after the variant message is sent, record its own context:

```python
    sent = await callback.message.answer(
        output_formatter.format_variant(variant),
        parse_mode=output_formatter.PARSE_MODE,
        reply_markup=build_refine_keyboard(platform, 1, language),
    )
    save_refine_context(
        db_path,
        callback.message.chat.id,
        sent.message_id,
        source_text,
        content_language,
        with_hashtags,
        platform,
    )
```

Add `from bot.storage.refine_context import get_refine_context, save_refine_context` to the imports.

The whitelist and limit checks must keep their current position — before any of this, and before any AI call.

- [ ] **Step 4: Fix the existing refine tests**

The existing tests seed context through `_seed_finished_session`, which writes FSM data. Update that helper to ALSO write a refine-context row for the message id the tests use, so the existing tests keep exercising what they exercised. Do not weaken any existing assertion.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_handlers_refine.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/refine.py tests/test_handlers_refine.py
git commit -m "fix: refine from the source of the post the button belongs to"
```

---

### Task 4: Authored-post flow, digest generation token, and cleanup

**Files:**
- Modify: `bot/handlers/authorpost.py`, `bot/keyboards/authorpost.py`, `bot/handlers/start.py`, `bot/handlers/content.py`
- Test: `tests/test_handlers_authorpost.py`, `tests/test_keyboards_authorpost.py`, `tests/test_handlers_start.py`
- Docs: `docs/manual-checklist.md`

Two changes in one task because they touch the same handler.

**Change A — the authored-post flow passes its own context through.**
`on_authorpost_platform` calls `send_variants`; pass `db_path`, the chosen digest item as `source_text`, the resolved `content_language`, and `with_hashtags=True`.

**Change B — a stale digest button must not silently pick from a newer digest.**
Today the numbered buttons carry only an index. Collect digest A, then collect digest B, then tap "2" on A's old message ⇒ item 2 of B is used, silently. Fix: give each delivered digest a generation number, carry it in the callback data as `authorpost:item:<generation>:<index>`, and reject a tap whose generation does not match the current one with the existing "digest expired" message.

- `bot/handlers/start.py`: when stashing `digest_items`, also stash `digest_generation` — an integer incremented from whatever is currently in FSM data (absent ⇒ 1). Do this in BOTH delivery paths (`on_menu_news_digest` and `on_digest_topic_input`).
- `bot/keyboards/authorpost.py`: `build_item_choice_keyboard(item_count: int, generation: int)`; each button's callback data becomes `f"{CALLBACK_ITEM_PREFIX}:{generation}:{index}"`.
- `bot/handlers/authorpost.py`: `on_authorpost_start` reads the generation out of FSM and passes it to the keyboard builder. `on_authorpost_item` parses BOTH numbers with the existing guarded `int()` parse, and reports the expired-digest message if the generation does not match FSM's current one, or if the index is out of range.

Required new tests:

- a stale generation reports "digest expired" and does NOT write `source_text`
- the current generation still works
- `build_item_choice_keyboard` emits the generation in every button's callback data
- both digest delivery paths increment the generation
- `on_authorpost_platform` records a refine context with `with_hashtags=True` for each sent variant

Also add to `docs/manual-checklist.md`, in the authored-post section:

```markdown
- [ ] Собрать дайджест, затем собрать ещё один по другой теме, вернуться к первому сообщению и нажать номер → «дайджест устарел», а не пост по чужой теме
- [ ] Сгенерировать авторский пост, затем обычный пост (прислать ссылку), затем нажать «Ещё» под авторским → новый вариант по теме дайджеста и с хэштегами, а не по ссылке
```

- [ ] **Step 1:** Write the failing tests listed above.
- [ ] **Step 2:** Run them and confirm they fail for the right reason.
- [ ] **Step 3:** Implement Change A and Change B.
- [ ] **Step 4:** Run `python -m pytest tests/test_handlers_authorpost.py tests/test_keyboards_authorpost.py tests/test_handlers_start.py -v` — expect PASS.
- [ ] **Step 5:** Run `python -m pytest` — expect all pass.
- [ ] **Step 6:** Update the manual checklist.
- [ ] **Step 7: Commit**

```bash
git add bot/handlers/authorpost.py bot/keyboards/authorpost.py bot/handlers/start.py bot/handlers/content.py tests/test_handlers_authorpost.py tests/test_keyboards_authorpost.py tests/test_handlers_start.py docs/manual-checklist.md
git commit -m "fix: scope digest item buttons to the digest that produced them"
```
