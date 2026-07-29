# Кружки с ИИ-двойником, этап 1 «двойник» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пользователь присылает боту свои кружки, бот собирает из них библиотеку доноров, расшифровывает их в образцы устного стиля и создаёт клон голоса; всё это можно посмотреть и удалить одной кнопкой.

**Architecture:** Данные ложатся в две новые таблицы SQLite (`avatar_donors`, `voice_profiles`) плюс колонка `kind` в существующей `style_examples`. Работа с ffmpeg вынесена в `bot/services/ffmpeg_tools.py`, работа с ElevenLabs — в `bot/services/voice_gateway.py` по образцу `bot/services/ai_gateway.py`. Хендлеры не знают, какой провайдер под капотом.

**Tech Stack:** Python 3.11, aiogram 3, SQLite, httpx, pytest + `AsyncMock` + `respx`, ffmpeg/ffprobe.

**Спека:** `docs/superpowers/specs/2026-07-28-video-circle-double-design.md`

## Global Constraints

- Этап 1 **не делает ни одного платного рендера.** Единственный внешний платный вызов — клонирование голоса. Липсинка здесь нет.
- Все строки для пользователя идут через `get_string()` и обязаны существовать во всех четырёх локалях: `ru`, `en`, `vi`, `zh` (`bot/locales/`).
- Миграции — идемпотентные функции `_ensure_*`, вызываемые из `init_db()` в `bot/storage/db.py`. Существующая база в проде обновляется без потери данных.
- Модули хранилища — по одному на таблицу, соединение открывается и закрывается в каждой функции (`get_connection` из `bot/storage/db.py`), как в `bot/storage/style_examples.py`.
- Шлюзы: типизированные ошибки, структурное логирование через `LOGGER_NAME`, никакого aiogram внутри.
- `ELEVENLABS_API_KEY` — **необязательная** переменная со значением по умолчанию `""`. Обязательной её делать нельзя: уже развёрнутый в проде бот не должен упасть при старте после выката.
- Для тестов внешние вызовы подменяются: HTTP — через `respx`, запуск процессов — через модульную косвенность (`_run`), как `_sleep` в `bot/services/ai_gateway.py:25`.
- ffmpeg и ffprobe — новая системная зависимость деплоя.

**Отклонение от спеки, сделанное осознанно.** Спека называет один файл `bot/services/video_note.py`. В этапе 1 нужны только общие операции с медиа (замер длительности, извлечение и склейка звука), а специфичное для формата кружка (`plan_donor_fit`, приведение к video note) появится в этапе 2. Поэтому общие операции живут в `bot/services/ffmpeg_tools.py`, а `video_note.py` создаётся этапом 2. Ответственности не смешиваются.

---

### Task 1: Схема БД для двойника

**Files:**
- Modify: `bot/storage/db.py`
- Test: `tests/test_storage_db_double_schema.py`

**Interfaces:**
- Consumes: `init_db(db_path)`, `get_connection(db_path)` — существующие.
- Produces: таблицы `avatar_donors`, `voice_profiles`; колонка `style_examples.kind TEXT NOT NULL DEFAULT 'written'`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_db_double_schema.py`:

```python
from __future__ import annotations

import sqlite3

from bot.storage.db import init_db


def _columns(path: str, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def test_avatar_donors_table_created(db_path):
    assert _columns(db_path, "avatar_donors") == {
        "id",
        "telegram_id",
        "file_id",
        "duration_sec",
        "transcript",
        "created_at",
        "last_used_at",
        "is_active",
    }


def test_voice_profiles_table_created(db_path):
    assert _columns(db_path, "voice_profiles") == {
        "telegram_id",
        "provider",
        "external_voice_id",
        "consent_at",
        "created_at",
    }


def test_style_examples_gains_kind_column(db_path):
    assert "kind" in _columns(db_path, "style_examples")


def test_kind_column_is_added_to_legacy_database(tmp_path):
    # Воспроизводим базу, развёрнутую до этой фичи: style_examples без kind.
    path = str(tmp_path / "legacy.db")
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE style_examples ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, "
        "example_text TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO style_examples (telegram_id, example_text, created_at) "
        "VALUES (?, ?, ?)",
        (1, "Старый пост", "2026-07-01T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    init_db(path)

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT kind FROM style_examples").fetchall()
    finally:
        connection.close()
    assert rows == [("written",)]


def test_init_db_is_idempotent(db_path):
    init_db(db_path)

    assert "kind" in _columns(db_path, "style_examples")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage_db_double_schema.py -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: avatar_donors`

- [ ] **Step 3: Write minimal implementation**

В `bot/storage/db.py` дописать в конец константы `SCHEMA` (перед закрывающими `"""`):

```python
CREATE TABLE IF NOT EXISTS avatar_donors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    file_id TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,
    transcript TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    telegram_id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    external_voice_id TEXT NOT NULL,
    consent_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

Там же в `SCHEMA` в определении `style_examples` добавить строку после `created_at TEXT NOT NULL,`:

```python
    kind TEXT NOT NULL DEFAULT 'written'
```

(запятая переносится на `created_at TEXT NOT NULL,` — колонка `kind` становится последней).

Добавить функцию миграции рядом с остальными `_ensure_*`:

```python
def _ensure_style_example_kind_column(connection: sqlite3.Connection) -> None:
    # Этап 1 фичи «двойник» добавляет вид образца стиля: письменные посты
    # и расшифровки кружков нельзя смешивать в одном промпте. CREATE TABLE
    # IF NOT EXISTS покрывает только чистые установки — уже развёрнутой базе
    # нужна явная миграция, иначе бот упадёт на первом запросе после выката.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(style_examples)")}
    if "kind" not in columns:
        connection.execute(
            "ALTER TABLE style_examples ADD COLUMN kind TEXT NOT NULL DEFAULT 'written'"
        )
```

И вызвать её в `init_db()` последней в цепочке `_ensure_*`:

```python
        _ensure_style_example_kind_column(connection)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage_db_double_schema.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Run the whole suite — миграция трогает общую таблицу**

Run: `pytest -q`
Expected: PASS, регрессий нет

- [ ] **Step 6: Commit**

```bash
git add bot/storage/db.py tests/test_storage_db_double_schema.py
git commit -m "feat: add avatar_donors and voice_profiles tables, style_examples.kind"
```

---

### Task 2: Раздельный учёт письменного и устного стиля

Самая опасная задача плана: без раздельного вытеснения расшифровки кружков вытеснят письменные образцы и **сломают уже работающий сценарий авторского поста**.

**Files:**
- Modify: `bot/storage/style_examples.py`
- Test: `tests/test_storage_style_examples.py` (дописать)

**Interfaces:**
- Consumes: колонка `kind` из Task 1.
- Produces:
  - `KIND_WRITTEN = "written"`, `KIND_SPOKEN = "spoken"`
  - `add_style_example(db_path: str, telegram_id: int, text: str, kind: str = KIND_WRITTEN) -> None`
  - `get_style_examples(db_path: str, telegram_id: int, limit: int = MAX_EXAMPLES_PER_USER, kind: str = KIND_WRITTEN) -> list[str]`
  - `clear_style_examples(db_path: str, telegram_id: int, kind: str | None = None) -> None` — `None` означает «все виды»

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_storage_style_examples.py`:

```python
from bot.storage.style_examples import KIND_SPOKEN, KIND_WRITTEN


def test_spoken_examples_do_not_appear_among_written(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка кружка", kind=KIND_SPOKEN)

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Письменный пост"]
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == [
        "Расшифровка кружка"
    ]


def test_spoken_examples_never_evict_written_ones(db_path):
    # Регрессия: общий на пользователя лимит вытеснил бы все письменные
    # образцы и сломал сценарий авторского поста, который требует их не менее 5.
    for index in range(MAX_EXAMPLES_PER_USER):
        add_style_example(db_path, TELEGRAM_ID, f"Пост {index}")
    for index in range(MAX_EXAMPLES_PER_USER + 5):
        add_style_example(db_path, TELEGRAM_ID, f"Кружок {index}", kind=KIND_SPOKEN)

    written = get_style_examples(db_path, TELEGRAM_ID, limit=100)

    assert len(written) == MAX_EXAMPLES_PER_USER


def test_spoken_examples_are_evicted_within_their_own_kind(db_path):
    for index in range(MAX_EXAMPLES_PER_USER + 3):
        add_style_example(db_path, TELEGRAM_ID, f"Кружок {index}", kind=KIND_SPOKEN)

    spoken = get_style_examples(db_path, TELEGRAM_ID, limit=100, kind=KIND_SPOKEN)

    assert len(spoken) == MAX_EXAMPLES_PER_USER


def test_clear_style_examples_can_target_a_single_kind(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка кружка", kind=KIND_SPOKEN)

    clear_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN)

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Письменный пост"]
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == []


def test_clear_style_examples_without_kind_still_clears_everything(db_path):
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка кружка", kind=KIND_SPOKEN)

    clear_style_examples(db_path, TELEGRAM_ID)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage_style_examples.py -v`
Expected: FAIL — `ImportError: cannot import name 'KIND_SPOKEN'`

- [ ] **Step 3: Write minimal implementation**

Заменить содержимое `bot/storage/style_examples.py` ниже строки с `MAX_EXAMPLES_PER_USER = 10` на:

```python
# Письменные посты и расшифровки кружков нельзя смешивать в одном промпте:
# по письменным образцам устный сценарий звучит как зачитанная статья.
# Вытеснение тоже раздельное — иначе расшифровки съедят письменные образцы
# и сломают сценарий авторского поста, требующий не менее 5 письменных.
KIND_WRITTEN = "written"
KIND_SPOKEN = "spoken"


def add_style_example(
    db_path: str, telegram_id: int, text: str, kind: str = KIND_WRITTEN
) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO style_examples (telegram_id, example_text, created_at, kind) "
            "VALUES (?, ?, ?, ?)",
            (telegram_id, text, created_at, kind),
        )
        # Eviction keyed on id (insertion order), not created_at: sqlite's
        # TEXT timestamp column can't disambiguate two inserts within the
        # same wall-clock resolution, but AUTOINCREMENT id always does.
        connection.execute(
            "DELETE FROM style_examples WHERE telegram_id = ? AND kind = ? AND id NOT IN ("
            "SELECT id FROM style_examples WHERE telegram_id = ? AND kind = ? "
            "ORDER BY id DESC LIMIT ?)",
            (telegram_id, kind, telegram_id, kind, MAX_EXAMPLES_PER_USER),
        )
        connection.commit()
    finally:
        connection.close()


def get_style_examples(
    db_path: str,
    telegram_id: int,
    limit: int = MAX_EXAMPLES_PER_USER,
    kind: str = KIND_WRITTEN,
) -> list[str]:
    # Most-recent-first (id DESC): the newest examples are the most likely
    # to still reflect the user's current voice, and this is also the order
    # they get quoted into the generation prompt (content_generator.py).
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT example_text FROM style_examples WHERE telegram_id = ? AND kind = ? "
            "ORDER BY id DESC LIMIT ?",
            (telegram_id, kind, limit),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        connection.close()


def clear_style_examples(
    db_path: str, telegram_id: int, kind: str | None = None
) -> None:
    # kind=None стирает все виды — это поведение кнопки «удалить двойника».
    # Ветка «загрузить новые образцы» в авторском посте зовёт с kind=KIND_WRITTEN,
    # иначе пользователь получил бы голос, смешанный из двух эпох его текстов.
    connection = get_connection(db_path)
    try:
        if kind is None:
            connection.execute(
                "DELETE FROM style_examples WHERE telegram_id = ?", (telegram_id,)
            )
        else:
            connection.execute(
                "DELETE FROM style_examples WHERE telegram_id = ? AND kind = ?",
                (telegram_id, kind),
            )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage_style_examples.py -v`
Expected: PASS, все тесты файла включая старые

- [ ] **Step 5: Проверить, что авторский пост и /settov не сломались**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/storage/style_examples.py tests/test_storage_style_examples.py
git commit -m "feat: separate written and spoken style examples with per-kind eviction"
```

---

### Task 3: Хранилище доноров

**Files:**
- Create: `bot/storage/avatar_donors.py`
- Test: `tests/test_storage_avatar_donors.py`

**Interfaces:**
- Consumes: таблицу `avatar_donors` из Task 1.
- Produces:
  - `MIN_DONOR_SECONDS = 20`, `RECOMMENDED_DONOR_SECONDS = 35`, `MIN_DONOR_COUNT = 3`
  - `Donor` — frozen dataclass с полями `id: int, file_id: str, duration_sec: int, transcript: str | None`
  - `add_donor(db_path: str, telegram_id: int, file_id: str, duration_sec: int, transcript: str | None) -> int`
  - `get_donors(db_path: str, telegram_id: int) -> list[Donor]`
  - `count_donors(db_path: str, telegram_id: int) -> int`
  - `clear_donors(db_path: str, telegram_id: int) -> None`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_avatar_donors.py`:

```python
from __future__ import annotations

from bot.storage.avatar_donors import (
    MIN_DONOR_COUNT,
    MIN_DONOR_SECONDS,
    RECOMMENDED_DONOR_SECONDS,
    add_donor,
    clear_donors,
    count_donors,
    get_donors,
)

TELEGRAM_ID = 111
OTHER_TELEGRAM_ID = 222


def test_no_donors_for_unknown_user(db_path):
    assert get_donors(db_path, TELEGRAM_ID) == []
    assert count_donors(db_path, TELEGRAM_ID) == 0


def test_add_donor_returns_id_and_round_trips(db_path):
    donor_id = add_donor(db_path, TELEGRAM_ID, "file-1", 42, "Привет, это я")

    donors = get_donors(db_path, TELEGRAM_ID)

    assert donor_id > 0
    assert len(donors) == 1
    assert donors[0].id == donor_id
    assert donors[0].file_id == "file-1"
    assert donors[0].duration_sec == 42
    assert donors[0].transcript == "Привет, это я"


def test_donor_without_transcript_is_allowed(db_path):
    add_donor(db_path, TELEGRAM_ID, "file-1", 42, None)

    assert get_donors(db_path, TELEGRAM_ID)[0].transcript is None


def test_count_donors_counts_only_own(db_path):
    add_donor(db_path, TELEGRAM_ID, "file-1", 42, None)
    add_donor(db_path, TELEGRAM_ID, "file-2", 44, None)
    add_donor(db_path, OTHER_TELEGRAM_ID, "file-3", 40, None)

    assert count_donors(db_path, TELEGRAM_ID) == 2
    assert count_donors(db_path, OTHER_TELEGRAM_ID) == 1


def test_donors_are_returned_oldest_first(db_path):
    add_donor(db_path, TELEGRAM_ID, "file-1", 42, None)
    add_donor(db_path, TELEGRAM_ID, "file-2", 44, None)

    assert [donor.file_id for donor in get_donors(db_path, TELEGRAM_ID)] == [
        "file-1",
        "file-2",
    ]


def test_clear_donors_leaves_other_users_untouched(db_path):
    add_donor(db_path, TELEGRAM_ID, "file-1", 42, None)
    add_donor(db_path, OTHER_TELEGRAM_ID, "file-2", 44, None)

    clear_donors(db_path, TELEGRAM_ID)

    assert get_donors(db_path, TELEGRAM_ID) == []
    assert count_donors(db_path, OTHER_TELEGRAM_ID) == 1


def test_clear_donors_is_safe_for_unknown_user(db_path):
    clear_donors(db_path, TELEGRAM_ID)

    assert get_donors(db_path, TELEGRAM_ID) == []


def test_thresholds_match_the_spec(db_path):
    assert MIN_DONOR_SECONDS == 20
    assert RECOMMENDED_DONOR_SECONDS == 35
    assert MIN_DONOR_COUNT == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage_avatar_donors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.avatar_donors'`

- [ ] **Step 3: Write minimal implementation**

Создать `bot/storage/avatar_donors.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection

# Донор короче аудио приходится зацикливать, и на стыке видна склейка —
# кадр дёргается, кружок сразу читается как подделка. 20 секунд — жёсткий
# минимум приёма, 35 — то, что просим у пользователя в тексте приглашения.
MIN_DONOR_SECONDS = 20
RECOMMENDED_DONOR_SECONDS = 35

# Меньше трёх доноров — один и тот же фон в каждом кружке, подписчики
# замечают повтор быстрее, чем кажется.
MIN_DONOR_COUNT = 3


@dataclass(frozen=True)
class Donor:
    id: int
    file_id: str
    duration_sec: int
    transcript: str | None


def add_donor(
    db_path: str,
    telegram_id: int,
    file_id: str,
    duration_sec: int,
    transcript: str | None,
) -> int:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            "INSERT INTO avatar_donors "
            "(telegram_id, file_id, duration_sec, transcript, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (telegram_id, file_id, duration_sec, transcript, created_at),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_donors(db_path: str, telegram_id: int) -> list[Donor]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT id, file_id, duration_sec, transcript FROM avatar_donors "
            "WHERE telegram_id = ? AND is_active = 1 ORDER BY id ASC",
            (telegram_id,),
        ).fetchall()
        return [Donor(id=row[0], file_id=row[1], duration_sec=row[2], transcript=row[3]) for row in rows]
    finally:
        connection.close()


def count_donors(db_path: str, telegram_id: int) -> int:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM avatar_donors WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def clear_donors(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_donors WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage_avatar_donors.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add bot/storage/avatar_donors.py tests/test_storage_avatar_donors.py
git commit -m "feat: add avatar donor storage"
```

---

### Task 4: Хранилище голосовых профилей

**Files:**
- Create: `bot/storage/voice_profiles.py`
- Test: `tests/test_storage_voice_profiles.py`

**Interfaces:**
- Consumes: таблицу `voice_profiles` из Task 1.
- Produces:
  - `VoiceProfile` — frozen dataclass: `provider: str, external_voice_id: str, consent_at: str, created_at: str`
  - `save_voice_profile(db_path: str, telegram_id: int, provider: str, external_voice_id: str, consent_at: str) -> None` — upsert
  - `get_voice_profile(db_path: str, telegram_id: int) -> VoiceProfile | None`
  - `delete_voice_profile(db_path: str, telegram_id: int) -> None`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_voice_profiles.py`:

```python
from __future__ import annotations

from bot.storage.voice_profiles import (
    delete_voice_profile,
    get_voice_profile,
    save_voice_profile,
)

TELEGRAM_ID = 111
OTHER_TELEGRAM_ID = 222
CONSENT_AT = "2026-07-28T10:00:00+00:00"


def test_no_profile_for_unknown_user(db_path):
    assert get_voice_profile(db_path, TELEGRAM_ID) is None


def test_save_and_get_round_trip(db_path):
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", CONSENT_AT)

    profile = get_voice_profile(db_path, TELEGRAM_ID)

    assert profile is not None
    assert profile.provider == "elevenlabs"
    assert profile.external_voice_id == "voice-abc"
    assert profile.consent_at == CONSENT_AT
    assert profile.created_at


def test_save_overwrites_existing_profile(db_path):
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-old", CONSENT_AT)
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-new", CONSENT_AT)

    profile = get_voice_profile(db_path, TELEGRAM_ID)

    assert profile is not None
    assert profile.external_voice_id == "voice-new"


def test_profiles_are_isolated_per_user(db_path):
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-a", CONSENT_AT)
    save_voice_profile(db_path, OTHER_TELEGRAM_ID, "elevenlabs", "voice-b", CONSENT_AT)

    assert get_voice_profile(db_path, TELEGRAM_ID).external_voice_id == "voice-a"
    assert get_voice_profile(db_path, OTHER_TELEGRAM_ID).external_voice_id == "voice-b"


def test_delete_removes_only_own_profile(db_path):
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-a", CONSENT_AT)
    save_voice_profile(db_path, OTHER_TELEGRAM_ID, "elevenlabs", "voice-b", CONSENT_AT)

    delete_voice_profile(db_path, TELEGRAM_ID)

    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    assert get_voice_profile(db_path, OTHER_TELEGRAM_ID) is not None


def test_delete_is_safe_for_unknown_user(db_path):
    delete_voice_profile(db_path, TELEGRAM_ID)

    assert get_voice_profile(db_path, TELEGRAM_ID) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage_voice_profiles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.voice_profiles'`

- [ ] **Step 3: Write minimal implementation**

Создать `bot/storage/voice_profiles.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection


@dataclass(frozen=True)
class VoiceProfile:
    provider: str
    external_voice_id: str
    # Момент, когда пользователь согласился на клонирование. Юридический
    # артефакт, а не украшение: без него нечем подтвердить согласие.
    consent_at: str
    created_at: str


def save_voice_profile(
    db_path: str,
    telegram_id: int,
    provider: str,
    external_voice_id: str,
    consent_at: str,
) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO voice_profiles "
            "(telegram_id, provider, external_voice_id, consent_at, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET "
            "provider = excluded.provider, "
            "external_voice_id = excluded.external_voice_id, "
            "consent_at = excluded.consent_at, "
            "created_at = excluded.created_at",
            (telegram_id, provider, external_voice_id, consent_at, created_at),
        )
        connection.commit()
    finally:
        connection.close()


def get_voice_profile(db_path: str, telegram_id: int) -> VoiceProfile | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT provider, external_voice_id, consent_at, created_at "
            "FROM voice_profiles WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        return VoiceProfile(
            provider=row[0],
            external_voice_id=row[1],
            consent_at=row[2],
            created_at=row[3],
        )
    finally:
        connection.close()


def delete_voice_profile(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM voice_profiles WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage_voice_profiles.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add bot/storage/voice_profiles.py tests/test_storage_voice_profiles.py
git commit -m "feat: add voice profile storage"
```

---

### Task 5: Операции с медиа на ffmpeg

**Files:**
- Create: `bot/services/ffmpeg_tools.py`
- Test: `tests/test_services_ffmpeg_tools.py`

**Interfaces:**
- Consumes: ничего из предыдущих задач.
- Produces:
  - `FfmpegError(Exception)`
  - `_run` — модульная косвенность для подмены в тестах, по умолчанию `asyncio.create_subprocess_exec`
  - `async probe_duration(path: str) -> float`
  - `async extract_audio(video_path: str, out_path: str) -> str` — возвращает `out_path`
  - `async concat_audio(paths: list[str], out_path: str) -> str` — возвращает `out_path`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_ffmpeg_tools.py`:

```python
from __future__ import annotations

import pytest

from bot.services import ffmpeg_tools


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b"" if self.returncode == 0 else b"boom"


def _fake_run(stdout: bytes = b"", returncode: int = 0):
    calls: list[tuple[str, ...]] = []

    async def runner(*args, **kwargs):
        calls.append(args)
        return _FakeProcess(stdout=stdout, returncode=returncode)

    runner.calls = calls
    return runner


@pytest.mark.asyncio
async def test_probe_duration_parses_ffprobe_output(monkeypatch):
    runner = _fake_run(stdout=b"31.480000\n")
    monkeypatch.setattr(ffmpeg_tools, "_run", runner)

    duration = await ffmpeg_tools.probe_duration("donor.mp4")

    assert duration == pytest.approx(31.48)
    assert "ffprobe" in runner.calls[0][0]
    assert "donor.mp4" in runner.calls[0]


@pytest.mark.asyncio
async def test_probe_duration_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(ffmpeg_tools, "_run", _fake_run(returncode=1))

    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.probe_duration("donor.mp4")


@pytest.mark.asyncio
async def test_probe_duration_raises_on_unparsable_output(monkeypatch):
    monkeypatch.setattr(ffmpeg_tools, "_run", _fake_run(stdout=b"N/A\n"))

    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.probe_duration("donor.mp4")


@pytest.mark.asyncio
async def test_extract_audio_returns_output_path(monkeypatch):
    runner = _fake_run()
    monkeypatch.setattr(ffmpeg_tools, "_run", runner)

    result = await ffmpeg_tools.extract_audio("donor.mp4", "donor.wav")

    assert result == "donor.wav"
    assert "-vn" in runner.calls[0]


@pytest.mark.asyncio
async def test_extract_audio_raises_on_failure(monkeypatch):
    monkeypatch.setattr(ffmpeg_tools, "_run", _fake_run(returncode=1))

    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.extract_audio("donor.mp4", "donor.wav")


@pytest.mark.asyncio
async def test_concat_audio_writes_list_file_and_returns_path(monkeypatch, tmp_path):
    runner = _fake_run()
    monkeypatch.setattr(ffmpeg_tools, "_run", runner)
    out_path = str(tmp_path / "voice.wav")

    result = await ffmpeg_tools.concat_audio(
        [str(tmp_path / "a.wav"), str(tmp_path / "b.wav")], out_path
    )

    assert result == out_path
    assert "concat" in runner.calls[0]


@pytest.mark.asyncio
async def test_concat_audio_rejects_empty_input(tmp_path):
    with pytest.raises(ffmpeg_tools.FfmpegError):
        await ffmpeg_tools.concat_audio([], str(tmp_path / "voice.wav"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services_ffmpeg_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.ffmpeg_tools'`

- [ ] **Step 3: Write minimal implementation**

Создать `bot/services/ffmpeg_tools.py`:

```python
from __future__ import annotations

import asyncio
import logging
import pathlib
import tempfile

from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


class FfmpegError(Exception):
    """ffmpeg или ffprobe завершились с ошибкой либо вернули мусор."""


# Module-level indirection so tests can replace the process launcher and
# never need a real ffmpeg binary — same trick as `_sleep` in ai_gateway.py.
_run = asyncio.create_subprocess_exec


async def _execute(*args: str) -> bytes:
    process = await _run(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode(errors="replace").strip()
        logger.error(
            "ffmpeg command failed: args=%s returncode=%s stderr=%s",
            args,
            process.returncode,
            message,
        )
        raise FfmpegError(f"Команда {args[0]} завершилась с кодом {process.returncode}")
    return stdout


async def probe_duration(path: str) -> float:
    stdout = await _execute(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        path,
    )
    raw = stdout.decode(errors="replace").strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise FfmpegError(f"ffprobe вернул неразбираемую длительность: {raw!r}") from exc


async def extract_audio(video_path: str, out_path: str) -> str:
    # Моно 16 кГц: этого достаточно для клонирования голоса и на порядок
    # экономит трафик при загрузке дорожки провайдеру.
    await _execute(
        "ffmpeg",
        "-v",
        "error",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        out_path,
    )
    return out_path


async def concat_audio(paths: list[str], out_path: str) -> str:
    if not paths:
        raise FfmpegError("Нечего склеивать: список дорожек пуст")

    # concat-демультиплексор требует файла-списка; все дорожки уже приведены
    # к одному формату в extract_audio, поэтому -c copy безопасен.
    directory = pathlib.Path(out_path).parent
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, dir=str(directory), encoding="utf-8"
    ) as handle:
        for path in paths:
            handle.write(f"file '{path}'\n")
        list_path = handle.name

    try:
        await _execute(
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c",
            "copy",
            "-y",
            out_path,
        )
    finally:
        pathlib.Path(list_path).unlink(missing_ok=True)
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_services_ffmpeg_tools.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add bot/services/ffmpeg_tools.py tests/test_services_ffmpeg_tools.py
git commit -m "feat: add ffmpeg helpers for duration probing and audio extraction"
```

---

### Task 6: Шлюз клонирования голоса

**Files:**
- Create: `bot/services/voice_gateway.py`
- Modify: `bot/config.py`
- Test: `tests/test_services_voice_gateway.py`

**Interfaces:**
- Consumes: `load_settings()` из `bot/config.py`.
- Produces:
  - `VoiceGatewayError(Exception)`, `VoiceGatewayUnavailableError`, `VoiceGatewayInvalidResponseError`
  - `PROVIDER_NAME = "elevenlabs"`
  - `async clone_voice(audio_bytes: bytes, name: str) -> str` — возвращает `external_voice_id`
  - `async delete_voice(voice_id: str) -> None`
  - Новые поля `Settings`: `elevenlabs_api_key: str`, `elevenlabs_base_url: str`, `tmp_media_dir: str`

Синтез речи (`synthesize`) в этап 1 не входит — он нужен только для кружка и появится в этапе 2.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_voice_gateway.py`:

```python
from __future__ import annotations

import httpx
import pytest
import respx

from bot.services import voice_gateway

BASE_URL = "https://api.elevenlabs.io/v1"


@pytest.fixture(autouse=True)
def _configure_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "1")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "voice-key")


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_returns_voice_id():
    route = respx.post(f"{BASE_URL}/voices/add").mock(
        return_value=httpx.Response(200, json={"voice_id": "voice-abc"})
    )

    voice_id = await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")

    assert voice_id == "voice-abc"
    assert route.called
    assert route.calls[0].request.headers["xi-api-key"] == "voice-key"


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_raises_on_missing_voice_id():
    respx.post(f"{BASE_URL}/voices/add").mock(
        return_value=httpx.Response(200, json={"detail": "no id here"})
    )

    with pytest.raises(voice_gateway.VoiceGatewayInvalidResponseError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_raises_on_http_error():
    respx.post(f"{BASE_URL}/voices/add").mock(return_value=httpx.Response(422))

    with pytest.raises(voice_gateway.VoiceGatewayError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@respx.mock
@pytest.mark.asyncio
async def test_clone_voice_raises_on_transport_error():
    respx.post(f"{BASE_URL}/voices/add").mock(
        side_effect=httpx.ConnectError("no network")
    )

    with pytest.raises(voice_gateway.VoiceGatewayUnavailableError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@pytest.mark.asyncio
async def test_clone_voice_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")

    with pytest.raises(voice_gateway.VoiceGatewayError):
        await voice_gateway.clone_voice(b"audio-bytes", "Двойник 111")


@respx.mock
@pytest.mark.asyncio
async def test_delete_voice_calls_provider():
    route = respx.delete(f"{BASE_URL}/voices/voice-abc").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    await voice_gateway.delete_voice("voice-abc")

    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_delete_voice_raises_on_http_error():
    respx.delete(f"{BASE_URL}/voices/voice-abc").mock(
        return_value=httpx.Response(500)
    )

    with pytest.raises(voice_gateway.VoiceGatewayError):
        await voice_gateway.delete_voice("voice-abc")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services_voice_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.voice_gateway'`

- [ ] **Step 3: Add the settings**

В `bot/config.py` добавить константы рядом с остальными `DEFAULT_*`:

```python
DEFAULT_ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
DEFAULT_TMP_MEDIA_DIR = "tmp_media"
```

В `@dataclass(frozen=True) class Settings` добавить поля:

```python
    elevenlabs_api_key: str
    elevenlabs_base_url: str
    tmp_media_dir: str
```

В `load_settings()` перед `return Settings(` добавить:

```python
    # Намеренно НЕ через _require: уже развёрнутый в проде бот не должен
    # падать при старте после выката фичи «двойник». Пустой ключ означает,
    # что фича недоступна, и об этом сообщает voice_gateway, а не краш.
    elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    elevenlabs_base_url = os.environ.get("ELEVENLABS_BASE_URL", DEFAULT_ELEVENLABS_BASE_URL)
    tmp_media_dir = os.environ.get("TMP_MEDIA_DIR", DEFAULT_TMP_MEDIA_DIR)
```

И передать их в конструктор `Settings(...)`:

```python
        elevenlabs_api_key=elevenlabs_api_key,
        elevenlabs_base_url=elevenlabs_base_url,
        tmp_media_dir=tmp_media_dir,
```

- [ ] **Step 4: Write the gateway**

Создать `bot/services/voice_gateway.py`:

```python
from __future__ import annotations

import logging
from typing import Any

import httpx

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

PROVIDER_NAME = "elevenlabs"

_TIMEOUT_SECONDS = 120.0


class VoiceGatewayError(Exception):
    """Базовый класс всех отказов шлюза голоса."""


class VoiceGatewayUnavailableError(VoiceGatewayError):
    pass


class VoiceGatewayInvalidResponseError(VoiceGatewayError):
    pass


def _client() -> httpx.AsyncClient:
    settings = load_settings()
    if not settings.elevenlabs_api_key:
        raise VoiceGatewayError(
            "ELEVENLABS_API_KEY не задан — клонирование голоса недоступно"
        )
    return httpx.AsyncClient(
        base_url=settings.elevenlabs_base_url,
        timeout=_TIMEOUT_SECONDS,
        headers={"xi-api-key": settings.elevenlabs_api_key},
    )


def _check_status(response: httpx.Response, operation: str) -> None:
    if response.status_code >= 400:
        logger.error(
            "Voice gateway call failed: operation=%s provider=%s status=%s",
            operation,
            PROVIDER_NAME,
            response.status_code,
        )
        raise VoiceGatewayError(
            f"Провайдер голоса вернул ошибку {response.status_code}"
        )


async def clone_voice(audio_bytes: bytes, name: str) -> str:
    operation = "clone_voice"
    client = _client()
    async with client:
        try:
            response = await client.post(
                "/voices/add",
                data={"name": name},
                files={"files": ("voice.wav", audio_bytes, "audio/wav")},
            )
        except httpx.HTTPError as exc:
            logger.error(
                "Voice gateway transport failure: operation=%s error=%s",
                operation,
                exc,
                exc_info=True,
            )
            raise VoiceGatewayUnavailableError(
                "Не удалось связаться с провайдером голоса"
            ) from exc

    _check_status(response, operation)

    try:
        payload: Any = response.json()
        voice_id = payload["voice_id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise VoiceGatewayInvalidResponseError(
            "Ответ провайдера голоса не содержит идентификатора голоса"
        ) from exc

    if not voice_id:
        raise VoiceGatewayInvalidResponseError("Провайдер вернул пустой идентификатор голоса")

    logger.info(
        "Voice cloned: provider=%s operation=%s", PROVIDER_NAME, operation
    )
    return str(voice_id)


async def delete_voice(voice_id: str) -> None:
    operation = "delete_voice"
    client = _client()
    async with client:
        try:
            response = await client.delete(f"/voices/{voice_id}")
        except httpx.HTTPError as exc:
            raise VoiceGatewayUnavailableError(
                "Не удалось связаться с провайдером голоса"
            ) from exc

    _check_status(response, operation)
    logger.info("Voice deleted: provider=%s operation=%s", PROVIDER_NAME, operation)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services_voice_gateway.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Проверить, что конфиг не сломал существующие тесты**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 7: Обновить `.env.example`**

Дописать в `.env.example`:

```
# Клонирование голоса для фичи «двойник» (кружки). Пустое значение = фича выключена.
ELEVENLABS_API_KEY=
ELEVENLABS_BASE_URL=https://api.elevenlabs.io/v1
TMP_MEDIA_DIR=tmp_media
```

- [ ] **Step 8: Commit**

```bash
git add bot/services/voice_gateway.py bot/config.py .env.example tests/test_services_voice_gateway.py
git commit -m "feat: add ElevenLabs voice cloning gateway"
```

---

### Task 7: Клавиатуры двойника и все строки интерфейса

Все 20 строк сценария добавляются здесь и сразу во всех четырёх локалях.
Причина жёсткая: `tests/test_localization.py::test_all_locales_have_identical_keys`
требует одинакового набора ключей во всех локалях, поэтому добавление русских
строк без остальных языков оставило бы ветку красной на несколько коммитов.
Задачи 8–10 только используют готовые ключи и локали не трогают.

**Files:**
- Create: `bot/keyboards/circle.py`
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`
- Test: `tests/test_keyboards_circle.py`

**Interfaces:**
- Consumes: `get_string` из `bot/locales/loader.py`.
- Produces:
  - `CALLBACK_MY_DOUBLE = "menu:my_double"`
  - `CALLBACK_CONSENT_ACCEPT = "circle:consent_ok"`
  - `CALLBACK_DONORS_DONE = "circle:donors_done"`
  - `CALLBACK_ADD_DONORS = "circle:add_donors"`
  - `CALLBACK_DELETE = "circle:delete"`
  - `CALLBACK_DELETE_CONFIRM = "circle:delete_confirm"`
  - `build_consent_keyboard(lang: str) -> InlineKeyboardMarkup`
  - `build_donors_keyboard(lang: str, can_finish: bool) -> InlineKeyboardMarkup`
  - `build_my_double_keyboard(lang: str) -> InlineKeyboardMarkup`
  - `build_delete_confirm_keyboard(lang: str) -> InlineKeyboardMarkup`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_keyboards_circle.py`:

```python
from __future__ import annotations

from bot.keyboards.circle import (
    CALLBACK_ADD_DONORS,
    CALLBACK_CONSENT_ACCEPT,
    CALLBACK_DELETE,
    CALLBACK_DELETE_CONFIRM,
    CALLBACK_DONORS_DONE,
    build_consent_keyboard,
    build_delete_confirm_keyboard,
    build_donors_keyboard,
    build_my_double_keyboard,
)


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_consent_keyboard_offers_accept():
    assert _callbacks(build_consent_keyboard("ru")) == [CALLBACK_CONSENT_ACCEPT]


def test_donors_keyboard_hides_finish_until_enough_donors():
    assert _callbacks(build_donors_keyboard("ru", can_finish=False)) == []


def test_donors_keyboard_shows_finish_when_enough():
    assert _callbacks(build_donors_keyboard("ru", can_finish=True)) == [
        CALLBACK_DONORS_DONE
    ]


def test_my_double_keyboard_has_add_and_delete():
    callbacks = _callbacks(build_my_double_keyboard("ru"))

    assert CALLBACK_ADD_DONORS in callbacks
    assert CALLBACK_DELETE in callbacks


def test_delete_confirm_keyboard_asks_for_confirmation():
    assert CALLBACK_DELETE_CONFIRM in _callbacks(build_delete_confirm_keyboard("ru"))


def test_callback_data_fits_telegram_limit():
    # Telegram отводит под callback_data 64 байта.
    for value in (
        CALLBACK_CONSENT_ACCEPT,
        CALLBACK_DONORS_DONE,
        CALLBACK_ADD_DONORS,
        CALLBACK_DELETE,
        CALLBACK_DELETE_CONFIRM,
    ):
        assert len(value.encode("utf-8")) <= 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_keyboards_circle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.keyboards.circle'`

- [ ] **Step 3: Write minimal implementation**

Создать `bot/keyboards/circle.py`:

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_MY_DOUBLE = "menu:my_double"
CALLBACK_CONSENT_ACCEPT = "circle:consent_ok"
CALLBACK_DONORS_DONE = "circle:donors_done"
CALLBACK_ADD_DONORS = "circle:add_donors"
CALLBACK_DELETE = "circle:delete"
CALLBACK_DELETE_CONFIRM = "circle:delete_confirm"


def build_consent_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("double_consent_accept_button", lang),
                    callback_data=CALLBACK_CONSENT_ACCEPT,
                )
            ]
        ]
    )


def build_donors_keyboard(lang: str, can_finish: bool) -> InlineKeyboardMarkup:
    # Кнопку «Готово» показываем только когда доноров хватает: иначе она
    # обещает результат, которого сценарий выдать не может.
    rows: list[list[InlineKeyboardButton]] = []
    if can_finish:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("double_donors_done_button", lang),
                    callback_data=CALLBACK_DONORS_DONE,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_my_double_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("double_add_donors_button", lang),
                    callback_data=CALLBACK_ADD_DONORS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("double_delete_button", lang),
                    callback_data=CALLBACK_DELETE,
                )
            ],
        ]
    )


def build_delete_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("double_delete_confirm_button", lang),
                    callback_data=CALLBACK_DELETE_CONFIRM,
                )
            ]
        ]
    )
```

- [ ] **Step 4: Добавить все 20 строк в `bot/locales/ru.py`**

```python
    "double_consent_accept_button": "Согласен, создаём двойника",
    "double_donors_done_button": "Готово, создавай двойника",
    "double_add_donors_button": "Добавить кружки",
    "double_delete_button": "Удалить двойника",
    "double_delete_confirm_button": "Да, удалить всё",
    "double_consent_text": (
        "Сделаю твоего двойника для кружков.\n\n"
        "Возьму твои кружки, сниму с них лицо, мимику и голос. "
        "Храню у себя, удалить можно в любой момент одной кнопкой."
    ),
    "double_donors_invite": (
        "Перешли {minimum}–5 своих кружков подлиннее — те, которые тебе самому нравятся.\n"
        "Присылай по одному, я буду считать."
    ),
    "double_donor_saved": "Принято {collected} из {minimum}.",
    "double_donor_too_short": (
        "Этот кружок короче {minimum} секунд — на нём не получится собрать речь. "
        "Пришли подлиннее."
    ),
    "double_expected_video_note": "Жду именно кружок — запиши или перешли видеосообщение.",
    "double_status_text": "Твой двойник: доноров {donors}, голос — {voice}.",
    "double_voice_ready": "готов",
    "double_voice_missing": "ещё не создан",
    "double_need_more_donors": "Нужно хотя бы {minimum} кружка. Пришли ещё.",
    "double_voice_building": "Собираю голос, это займёт около минуты…",
    "double_voice_failed": (
        "Не получилось создать голос. Попробуй ещё раз чуть позже — "
        "кружки я сохранил, заново присылать не нужно."
    ),
    "double_ready": "Двойник готов: {donors} кружка в основе, голос создан.",
    "double_delete_confirm_text": (
        "Удалю кружки, расшифровки и голос. Отменить это будет нельзя — "
        "двойника придётся собирать заново."
    ),
    "double_deleted": "Двойник и все его данные удалены.",
    "menu_my_double_button": "🎭 Мой двойник",
```

- [ ] **Step 5: Добавить те же 20 ключей в `bot/locales/en.py`**

```python
    "double_consent_accept_button": "Agreed, build my double",
    "double_donors_done_button": "Done, build the double",
    "double_add_donors_button": "Add circles",
    "double_delete_button": "Delete double",
    "double_delete_confirm_button": "Yes, delete everything",
    "double_consent_text": (
        "I'll build your double for video circles.\n\n"
        "I'll take your circles and learn your face, expressions and voice from them. "
        "Stored on my side, and one button deletes it all whenever you want."
    ),
    "double_donors_invite": (
        "Forward me {minimum}-5 of your longer circles — the ones you like yourself.\n"
        "Send them one by one, I'll keep count."
    ),
    "double_donor_saved": "Got {collected} of {minimum}.",
    "double_donor_too_short": (
        "This circle is shorter than {minimum} seconds — too short to carry speech. "
        "Send a longer one."
    ),
    "double_expected_video_note": "I need a circle — record or forward a video message.",
    "double_status_text": "Your double: {donors} donor circles, voice — {voice}.",
    "double_voice_ready": "ready",
    "double_voice_missing": "not built yet",
    "double_need_more_donors": "I need at least {minimum} circles. Send more.",
    "double_voice_building": "Building the voice, this takes about a minute…",
    "double_voice_failed": (
        "Couldn't build the voice. Try again a bit later — "
        "your circles are saved, no need to resend them."
    ),
    "double_ready": "Double ready: built on {donors} circles, voice created.",
    "double_delete_confirm_text": (
        "This deletes the circles, the transcripts and the voice. "
        "It can't be undone — the double would have to be built from scratch."
    ),
    "double_deleted": "The double and all of its data are deleted.",
    "menu_my_double_button": "🎭 My double",
```

- [ ] **Step 6: Добавить те же 20 ключей в `bot/locales/vi.py` и `bot/locales/zh.py`**

Переводить с русского оригинала выше. Плейсхолдеры `{minimum}`, `{collected}`,
`{donors}`, `{voice}` обязаны сохраниться дословно — иначе `get_string()` упадёт
на `KeyError` при форматировании. Тон и длина строк — как у соседних ключей
в этих же файлах.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_circle.py tests/test_localization.py -v`
Expected: PASS — включая `test_all_locales_have_identical_keys`

- [ ] **Step 8: Commit**

```bash
git add bot/keyboards/circle.py bot/locales tests/test_keyboards_circle.py
git commit -m "feat: add keyboards and localised strings for the double flow"
```

---

### Task 8: Согласие и сбор доноров

**Files:**
- Create: `bot/handlers/circle.py`
- Test: `tests/test_handlers_circle_donors.py`

**Interfaces:**
- Consumes: `add_donor`, `count_donors`, `MIN_DONOR_SECONDS`, `MIN_DONOR_COUNT` (Task 3); `get_voice_profile` (Task 4); `probe_duration`, `extract_audio` (Task 5); клавиатуры (Task 7); `transcribe` из `bot/services/ai_gateway.py`; `_resolve_language` из `bot/handlers/content.py`.
- Produces:
  - `router` — `Router(name="circle")`
  - `CircleStates.collecting_donors`
  - `async on_my_double(callback: CallbackQuery, db_path: str, state: FSMContext) -> None`
  - `async on_consent_accept(callback: CallbackQuery, db_path: str, state: FSMContext) -> None`
  - `async on_donor_video_note(message: Message, db_path: str, state: FSMContext) -> None`
  - `async on_non_video_note(message: Message, db_path: str) -> None`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_circle_donors.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import circle
from bot.storage.avatar_donors import count_donors, get_donors
from bot.storage.style_examples import KIND_SPOKEN, get_style_examples

TELEGRAM_ID = 111


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _callback() -> MagicMock:
    callback = MagicMock()
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _video_note_message(duration: int = 40) -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.video_note.file_id = "donor-file-1"
    message.video_note.duration = duration
    message.answer = AsyncMock()
    message.bot.download = AsyncMock()
    return message


@pytest.fixture(autouse=True)
def _stub_media(monkeypatch, tmp_path):
    async def fake_probe(path: str) -> float:
        return 40.0

    async def fake_extract(video_path: str, out_path: str) -> str:
        return out_path

    async def fake_transcribe(audio_bytes: bytes, language_hint=None) -> str:
        return "Расшифровка кружка"

    monkeypatch.setattr(circle, "probe_duration", fake_probe)
    monkeypatch.setattr(circle, "extract_audio", fake_extract)
    monkeypatch.setattr(circle, "transcribe", fake_transcribe)
    monkeypatch.setattr(circle, "_read_bytes", lambda path: b"audio")


@pytest.mark.asyncio
async def test_my_double_without_donors_shows_consent(db_path, state):
    callback = _callback()

    await circle.on_my_double(callback, db_path=db_path, state=state)

    callback.message.answer.assert_awaited()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_consent_starts_donor_collection(db_path, state):
    callback = _callback()

    await circle.on_consent_accept(callback, db_path=db_path, state=state)

    assert await state.get_state() == circle.CircleStates.collecting_donors.state
    data = await state.get_data()
    assert data["consent_at"]


@pytest.mark.asyncio
async def test_video_note_is_saved_with_transcript(db_path, state):
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)
    message = _video_note_message()

    await circle.on_donor_video_note(message, db_path=db_path, state=state)

    donors = get_donors(db_path, TELEGRAM_ID)
    assert len(donors) == 1
    assert donors[0].file_id == "donor-file-1"
    assert donors[0].transcript == "Расшифровка кружка"


@pytest.mark.asyncio
async def test_transcript_is_stored_as_spoken_style_example(db_path, state):
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)

    await circle.on_donor_video_note(_video_note_message(), db_path=db_path, state=state)

    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == [
        "Расшифровка кружка"
    ]


@pytest.mark.asyncio
async def test_short_donor_is_rejected(db_path, state, monkeypatch):
    async def short_probe(path: str) -> float:
        return 12.0

    monkeypatch.setattr(circle, "probe_duration", short_probe)
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)

    await circle.on_donor_video_note(_video_note_message(12), db_path=db_path, state=state)

    assert count_donors(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_failed_transcription_still_saves_donor(db_path, state, monkeypatch):
    async def failing_transcribe(audio_bytes: bytes, language_hint=None) -> str:
        raise circle.TranscriptionError("boom")

    monkeypatch.setattr(circle, "transcribe", failing_transcribe)
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)

    await circle.on_donor_video_note(_video_note_message(), db_path=db_path, state=state)

    donors = get_donors(db_path, TELEGRAM_ID)
    assert len(donors) == 1
    assert donors[0].transcript is None


@pytest.mark.asyncio
async def test_non_video_note_is_rejected_without_counting(db_path, state):
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.answer = AsyncMock()

    await circle.on_non_video_note(message, db_path=db_path)

    message.answer.assert_awaited()
    assert count_donors(db_path, TELEGRAM_ID) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_circle_donors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.handlers.circle'`

- [ ] **Step 3: Write minimal implementation**

Создать `bot/handlers/circle.py`:

```python
from __future__ import annotations

import logging
import pathlib
import uuid
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.keyboards.circle import (
    CALLBACK_ADD_DONORS,
    CALLBACK_CONSENT_ACCEPT,
    CALLBACK_MY_DOUBLE,
    build_consent_keyboard,
    build_donors_keyboard,
    build_my_double_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import TranscriptionError, transcribe
from bot.services.ffmpeg_tools import FfmpegError, extract_audio, probe_duration
from bot.storage.avatar_donors import (
    MIN_DONOR_COUNT,
    MIN_DONOR_SECONDS,
    add_donor,
    count_donors,
)
from bot.storage.style_examples import KIND_SPOKEN, add_style_example
from bot.storage.voice_profiles import get_voice_profile

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="circle")


class CircleStates(StatesGroup):
    collecting_donors = State()


def _read_bytes(path: str) -> bytes:
    # Вынесено отдельной функцией, чтобы тесты подменяли чтение диска, не
    # трогая остальную логику обработчика.
    return pathlib.Path(path).read_bytes()


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


@router.callback_query(F.data == CALLBACK_MY_DOUBLE)
async def on_my_double(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    donors = count_donors(db_path, telegram_id)
    profile = get_voice_profile(db_path, telegram_id)

    if donors == 0 and profile is None:
        await callback.message.answer(
            get_string("double_consent_text", language),
            reply_markup=build_consent_keyboard(language),
        )
    else:
        await callback.message.answer(
            get_string(
                "double_status_text",
                language,
                donors=donors,
                voice=get_string(
                    "double_voice_ready" if profile else "double_voice_missing",
                    language,
                ),
            ),
            reply_markup=build_my_double_keyboard(language),
        )
    await callback.answer()


@router.callback_query(F.data.in_({CALLBACK_CONSENT_ACCEPT, CALLBACK_ADD_DONORS}))
async def on_consent_accept(
    callback: CallbackQuery, db_path: str, state: FSMContext
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    await state.set_state(CircleStates.collecting_donors)
    # Момент согласия фиксируем здесь и переносим в voice_profiles при
    # создании голоса — это и есть юридический артефакт.
    await state.update_data(consent_at=datetime.now(timezone.utc).isoformat())

    collected = count_donors(db_path, telegram_id)
    await callback.message.answer(
        get_string("double_donors_invite", language, minimum=MIN_DONOR_COUNT),
        reply_markup=build_donors_keyboard(
            language, can_finish=collected >= MIN_DONOR_COUNT
        ),
    )
    await callback.answer()


@router.message(CircleStates.collecting_donors, F.video_note)
async def on_donor_video_note(
    message: Message, db_path: str, state: FSMContext
) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    video_path = _tmp_path(".mp4")
    audio_path = _tmp_path(".wav")
    try:
        await message.bot.download(message.video_note.file_id, destination=video_path)
        try:
            duration = await probe_duration(video_path)
        except FfmpegError:
            # ffprobe не смог прочитать файл — доверяем длительности,
            # которую Telegram кладёт в само сообщение.
            duration = float(message.video_note.duration)

        if duration < MIN_DONOR_SECONDS:
            await message.answer(
                get_string("double_donor_too_short", language, minimum=MIN_DONOR_SECONDS),
                reply_markup=build_donors_keyboard(
                    language,
                    can_finish=count_donors(db_path, telegram_id) >= MIN_DONOR_COUNT,
                ),
            )
            return

        transcript: str | None = None
        try:
            await extract_audio(video_path, audio_path)
            transcript = await transcribe(_read_bytes(audio_path))
        except (FfmpegError, TranscriptionError):
            # Донор всё равно ценен: устный стиль соберётся из остальных.
            logger.warning(
                "Donor transcription failed",
                extra={"user_id": telegram_id, "operation": "handler:circle"},
                exc_info=True,
            )

        add_donor(
            db_path,
            telegram_id,
            message.video_note.file_id,
            int(duration),
            transcript,
        )
        if transcript:
            add_style_example(db_path, telegram_id, transcript, kind=KIND_SPOKEN)
    finally:
        pathlib.Path(video_path).unlink(missing_ok=True)
        pathlib.Path(audio_path).unlink(missing_ok=True)

    collected = count_donors(db_path, telegram_id)
    await message.answer(
        get_string(
            "double_donor_saved", language, collected=collected, minimum=MIN_DONOR_COUNT
        ),
        reply_markup=build_donors_keyboard(
            language, can_finish=collected >= MIN_DONOR_COUNT
        ),
    )


@router.message(CircleStates.collecting_donors)
async def on_non_video_note(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    await message.answer(
        get_string("double_expected_video_note", language),
        reply_markup=build_donors_keyboard(
            language, can_finish=count_donors(db_path, telegram_id) >= MIN_DONOR_COUNT
        ),
    )
```

Все строки этого сценария уже добавлены в Task 7 — локали здесь не трогаем.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handlers_circle_donors.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/circle.py tests/test_handlers_circle_donors.py
git commit -m "feat: collect donor circles with consent and transcription"
```

---

### Task 9: Создание клона голоса

**Files:**
- Modify: `bot/handlers/circle.py`
- Test: `tests/test_handlers_circle_voice.py`

**Interfaces:**
- Consumes: `get_donors` (Task 3), `save_voice_profile` (Task 4), `concat_audio`/`extract_audio` (Task 5), `clone_voice`/`PROVIDER_NAME`/`VoiceGatewayError` (Task 6), `CALLBACK_DONORS_DONE` (Task 7).
- Produces: `async on_donors_done(callback: CallbackQuery, db_path: str, state: FSMContext) -> None`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_circle_voice.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import circle
from bot.storage.avatar_donors import add_donor
from bot.storage.voice_profiles import get_voice_profile

TELEGRAM_ID = 111
CONSENT_AT = "2026-07-28T10:00:00+00:00"


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _callback() -> MagicMock:
    callback = MagicMock()
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.message.bot.download = AsyncMock()
    callback.answer = AsyncMock()
    return callback


@pytest.fixture(autouse=True)
def _stub_media(monkeypatch):
    async def fake_extract(video_path: str, out_path: str) -> str:
        return out_path

    async def fake_concat(paths: list[str], out_path: str) -> str:
        return out_path

    monkeypatch.setattr(circle, "extract_audio", fake_extract)
    monkeypatch.setattr(circle, "concat_audio", fake_concat)
    monkeypatch.setattr(circle, "_read_bytes", lambda path: b"audio")


def _seed_donors(db_path: str, count: int = 3) -> None:
    for index in range(count):
        add_donor(db_path, TELEGRAM_ID, f"file-{index}", 40, "Расшифровка")


@pytest.mark.asyncio
async def test_voice_profile_is_created(db_path, state, monkeypatch):
    clone = AsyncMock(return_value="voice-abc")
    monkeypatch.setattr(circle, "clone_voice", clone)
    _seed_donors(db_path)
    await state.update_data(consent_at=CONSENT_AT)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    profile = get_voice_profile(db_path, TELEGRAM_ID)
    assert profile is not None
    assert profile.external_voice_id == "voice-abc"
    assert profile.consent_at == CONSENT_AT
    clone.assert_awaited_once()


@pytest.mark.asyncio
async def test_state_is_reset_after_success(db_path, state, monkeypatch):
    monkeypatch.setattr(circle, "clone_voice", AsyncMock(return_value="voice-abc"))
    _seed_donors(db_path)
    await state.set_state(circle.CircleStates.collecting_donors)
    await state.update_data(consent_at=CONSENT_AT)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_refuses_when_not_enough_donors(db_path, state, monkeypatch):
    clone = AsyncMock(return_value="voice-abc")
    monkeypatch.setattr(circle, "clone_voice", clone)
    _seed_donors(db_path, count=1)
    await state.update_data(consent_at=CONSENT_AT)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    clone.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_leaves_no_profile(db_path, state, monkeypatch):
    monkeypatch.setattr(
        circle,
        "clone_voice",
        AsyncMock(side_effect=circle.VoiceGatewayError("boom")),
    )
    _seed_donors(db_path)
    await state.update_data(consent_at=CONSENT_AT)
    callback = _callback()

    await circle.on_donors_done(callback, db_path=db_path, state=state)

    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    callback.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_missing_consent_timestamp_falls_back_to_now(db_path, state, monkeypatch):
    # FSM в памяти: перезапуск бота между согласием и нажатием «Готово»
    # стирает данные. Профиль всё равно должен получить отметку согласия.
    monkeypatch.setattr(circle, "clone_voice", AsyncMock(return_value="voice-abc"))
    _seed_donors(db_path)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    profile = get_voice_profile(db_path, TELEGRAM_ID)
    assert profile is not None
    assert profile.consent_at
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_circle_voice.py -v`
Expected: FAIL — `AttributeError: module 'bot.handlers.circle' has no attribute 'on_donors_done'`

- [ ] **Step 3: Write minimal implementation**

В `bot/handlers/circle.py` дополнить импорты:

```python
from bot.keyboards.circle import CALLBACK_DONORS_DONE
from bot.services.ffmpeg_tools import concat_audio
from bot.services.voice_gateway import PROVIDER_NAME, VoiceGatewayError, clone_voice
from bot.storage.avatar_donors import get_donors
from bot.storage.voice_profiles import save_voice_profile
```

И добавить обработчик в конец файла:

```python
@router.callback_query(F.data == CALLBACK_DONORS_DONE)
async def on_donors_done(
    callback: CallbackQuery, db_path: str, state: FSMContext
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    donors = get_donors(db_path, telegram_id)
    if len(donors) < MIN_DONOR_COUNT:
        await callback.message.answer(
            get_string("double_need_more_donors", language, minimum=MIN_DONOR_COUNT)
        )
        await callback.answer()
        return

    await callback.message.answer(get_string("double_voice_building", language))

    audio_paths: list[str] = []
    combined_path = _tmp_path(".wav")
    try:
        for donor in donors:
            video_path = _tmp_path(".mp4")
            audio_path = _tmp_path(".wav")
            await callback.message.bot.download(donor.file_id, destination=video_path)
            await extract_audio(video_path, audio_path)
            pathlib.Path(video_path).unlink(missing_ok=True)
            audio_paths.append(audio_path)

        # Один кружок — 30-60 секунд, а клонированию нужны 1-2 минуты речи,
        # поэтому дорожки всех доноров склеиваются в одну.
        await concat_audio(audio_paths, combined_path)
        voice_id = await clone_voice(_read_bytes(combined_path), f"double-{telegram_id}")
    except (FfmpegError, VoiceGatewayError):
        logger.error(
            "Voice cloning failed",
            extra={"user_id": telegram_id, "operation": "handler:circle"},
            exc_info=True,
        )
        await callback.message.answer(get_string("double_voice_failed", language))
        await callback.answer()
        return
    finally:
        for path in [*audio_paths, combined_path]:
            pathlib.Path(path).unlink(missing_ok=True)

    data = await state.get_data()
    consent_at = data.get("consent_at") or datetime.now(timezone.utc).isoformat()
    save_voice_profile(db_path, telegram_id, PROVIDER_NAME, voice_id, consent_at)

    # Состояние сбрасываем немедленно: пока оно выставлено, обычные текстовые
    # сообщения перехватывает этот роутер, и бот перестаёт отвечать на всё
    # остальное (та же причина, что в сценарии авторского поста).
    await state.set_state(None)
    await callback.message.answer(
        get_string("double_ready", language, donors=len(donors)),
        reply_markup=build_my_double_keyboard(language),
    )
    await callback.answer()
```

Все строки этого сценария уже добавлены в Task 7 — локали здесь не трогаем.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handlers_circle_voice.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/circle.py tests/test_handlers_circle_voice.py
git commit -m "feat: build a cloned voice from collected donor circles"
```

---

### Task 10: Удаление двойника

**Files:**
- Modify: `bot/handlers/circle.py`
- Test: `tests/test_handlers_circle_delete.py`

**Interfaces:**
- Consumes: `clear_donors` (Task 3), `delete_voice_profile`/`get_voice_profile` (Task 4), `delete_voice` (Task 6), `CALLBACK_DELETE`/`CALLBACK_DELETE_CONFIRM`/`build_delete_confirm_keyboard` (Task 7), `clear_style_examples` с `kind=KIND_SPOKEN` (Task 2).
- Produces:
  - `async on_delete_request(callback: CallbackQuery, db_path: str) -> None`
  - `async on_delete_confirm(callback: CallbackQuery, db_path: str, state: FSMContext) -> None`

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_circle_delete.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import circle
from bot.storage.avatar_donors import add_donor, count_donors
from bot.storage.style_examples import (
    KIND_SPOKEN,
    KIND_WRITTEN,
    add_style_example,
    get_style_examples,
)
from bot.storage.voice_profiles import get_voice_profile, save_voice_profile

TELEGRAM_ID = 111
CONSENT_AT = "2026-07-28T10:00:00+00:00"


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _callback() -> MagicMock:
    callback = MagicMock()
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _seed_double(db_path: str) -> None:
    add_donor(db_path, TELEGRAM_ID, "file-1", 40, "Расшифровка")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка", kind=KIND_SPOKEN)
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост", kind=KIND_WRITTEN)
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", CONSENT_AT)


@pytest.mark.asyncio
async def test_delete_request_asks_for_confirmation(db_path):
    _seed_double(db_path)
    callback = _callback()

    await circle.on_delete_request(callback, db_path=db_path)

    callback.message.answer.assert_awaited()
    assert count_donors(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_confirm_deletes_donors_voice_and_transcripts(db_path, state, monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(circle, "delete_voice", delete)
    _seed_double(db_path)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    assert count_donors(db_path, TELEGRAM_ID) == 0
    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == []
    delete.assert_awaited_once_with("voice-abc")


@pytest.mark.asyncio
async def test_written_style_examples_survive_deletion(db_path, state, monkeypatch):
    # Удаление двойника не должно задевать сценарий авторского поста.
    monkeypatch.setattr(circle, "delete_voice", AsyncMock())
    _seed_double(db_path)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_WRITTEN) == [
        "Письменный пост"
    ]


@pytest.mark.asyncio
async def test_local_data_is_wiped_even_if_provider_delete_fails(
    db_path, state, monkeypatch
):
    monkeypatch.setattr(
        circle,
        "delete_voice",
        AsyncMock(side_effect=circle.VoiceGatewayError("boom")),
    )
    _seed_double(db_path)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    assert count_donors(db_path, TELEGRAM_ID) == 0
    assert get_voice_profile(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_delete_is_safe_without_a_double(db_path, state, monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(circle, "delete_voice", delete)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    delete.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_circle_delete.py -v`
Expected: FAIL — `AttributeError: module 'bot.handlers.circle' has no attribute 'on_delete_request'`

- [ ] **Step 3: Write minimal implementation**

В `bot/handlers/circle.py` дополнить импорты:

```python
from bot.keyboards.circle import (
    CALLBACK_DELETE,
    CALLBACK_DELETE_CONFIRM,
    build_delete_confirm_keyboard,
)
from bot.services.voice_gateway import delete_voice
from bot.storage.avatar_donors import clear_donors
from bot.storage.style_examples import clear_style_examples
from bot.storage.voice_profiles import delete_voice_profile
```

И добавить обработчики в конец файла:

```python
@router.callback_query(F.data == CALLBACK_DELETE)
async def on_delete_request(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    await callback.message.answer(
        get_string("double_delete_confirm_text", language),
        reply_markup=build_delete_confirm_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == CALLBACK_DELETE_CONFIRM)
async def on_delete_confirm(
    callback: CallbackQuery, db_path: str, state: FSMContext
) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    profile = get_voice_profile(db_path, telegram_id)
    if profile is not None:
        try:
            await delete_voice(profile.external_voice_id)
        except VoiceGatewayError:
            # Локальные данные стираем в любом случае: обещание «удалю всё»
            # не должно зависеть от доступности чужого сервиса. Осиротевший
            # голос у провайдера удаляется руками, это видно в логах.
            logger.error(
                "Provider voice deletion failed, wiping local data anyway",
                extra={"user_id": telegram_id, "operation": "handler:circle"},
                exc_info=True,
            )

    delete_voice_profile(db_path, telegram_id)
    clear_donors(db_path, telegram_id)
    clear_style_examples(db_path, telegram_id, kind=KIND_SPOKEN)
    await state.set_state(None)

    await callback.message.answer(get_string("double_deleted", language))
    await callback.answer()
```

Все строки этого сценария уже добавлены в Task 7 — локали здесь не трогаем.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_handlers_circle_delete.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/circle.py tests/test_handlers_circle_delete.py
git commit -m "feat: delete the double and all of its data on request"
```

---

### Task 11: Подключение к боту, локализация и деплой

**Files:**
- Modify: `bot/main.py`, `bot/keyboards/start.py`, `tests/conftest.py`, `docs/manual-checklist.md`, `deploy/README-deploy.md`
- Test: `tests/test_localization.py` (проходит автоматически), `tests/test_keyboards_start.py` (дописать)

**Interfaces:**
- Consumes: `router` из `bot/handlers/circle.py`, `CALLBACK_MY_DOUBLE` из `bot/keyboards/circle.py`.
- Produces: кнопку «Мой двойник» в главном меню; зарегистрированный `circle_router`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_keyboards_start.py`:

```python
from bot.keyboards.circle import CALLBACK_MY_DOUBLE


def test_start_menu_offers_my_double():
    markup = build_start_menu_keyboard("ru")

    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]

    assert CALLBACK_MY_DOUBLE in callbacks
```

(имя `build_start_menu_keyboard` уже импортировано в этом файле; если нет — добавить в существующий импорт из `bot.keyboards.start`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_keyboards_start.py -v`
Expected: FAIL — `assert 'menu:my_double' in [...]`

- [ ] **Step 3: Добавить кнопку в меню**

В `bot/keyboards/start.py` дописать импорт:

```python
from bot.keyboards.circle import CALLBACK_MY_DOUBLE
```

и добавить ряд в `build_start_menu_keyboard` после ряда с дайджестом:

```python
            [
                InlineKeyboardButton(
                    text=get_string("menu_my_double_button", lang),
                    callback_data=CALLBACK_MY_DOUBLE,
                )
            ],
```

Ключ `menu_my_double_button` уже добавлен во все четыре локали в Task 7 —
локали здесь не трогаем.

- [ ] **Step 4: Зарегистрировать роутер**

В `bot/main.py` добавить импорт:

```python
from bot.handlers.circle import router as circle_router
```

и включить его в `build_dispatcher()` **до** `content_router` (у `circle_router` есть перехват сообщений в состоянии; `content_router` фильтруется по `StateFilter(None)` и должен идти после):

```python
    dispatcher.include_router(circle_router)
```

- [ ] **Step 5: Добавить роутер в conftest**

В `tests/conftest.py` добавить импорт и элемент кортежа:

```python
from bot.handlers.circle import router as circle_router
```

```python
_SINGLETON_ROUTERS = (
    start_router,
    language_router,
    channel_router,
    site_router,
    settov_router,
    circle_router,
    content_router,
    refine_router,
    errors_router,
)
```

- [ ] **Step 6: Run the whole suite**

Run: `pytest -q`
Expected: PASS, включая `tests/test_localization.py` (он проверяет совпадение ключей во всех локалях)

- [ ] **Step 7: Задокументировать ffmpeg как зависимость деплоя**

Дописать в `deploy/README-deploy.md`:

```markdown
## Системные зависимости

Фича «двойник» (кружки) требует ffmpeg и ffprobe на сервере:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
ffmpeg -version && ffprobe -version
```

Без них бот запустится, но сбор доноров будет падать на замере длительности.
```

- [ ] **Step 8: Дописать ручной чеклист**

Дописать в `docs/manual-checklist.md`:

```markdown
## Двойник (этап 1)

- [ ] «Мой двойник» на чистом аккаунте показывает экран согласия
- [ ] После согласия бот принимает кружки и считает их: «принято 1 из 3»
- [ ] Кружок короче 20 секунд отклоняется с понятным объяснением
- [ ] Обычное текстовое сообщение в режиме сбора не ломает счётчик
- [ ] Кнопка «Готово» появляется только с третьего кружка
- [ ] После создания голоса бот отвечает на обычные сообщения (состояние сброшено)
- [ ] Расшифровки кружков похожи на реальную речь, а не на набор слов
- [ ] «Удалить двойника» действительно стирает всё, а авторский пост продолжает работать
- [ ] Сценарий авторского поста не потерял письменные образцы стиля
```

- [ ] **Step 9: Commit**

```bash
git add bot/main.py bot/keyboards/start.py tests/conftest.py tests/test_keyboards_start.py docs/manual-checklist.md deploy/README-deploy.md
git commit -m "feat: wire the double flow into the bot, localise it, document ffmpeg"
```

---

## Проверка плана против спеки

| Требование спеки (этап 1) | Задача |
|---|---|
| Таблица `avatar_donors` | Task 1, 3 |
| Таблица `voice_profiles` с `consent_at` | Task 1, 4 |
| Колонка `kind`, раздельное вытеснение | Task 1, 2 |
| Экран согласия | Task 7, 8 |
| Сбор доноров, минимум 3, счётчик | Task 3, 8 |
| Отказ донору короче 20 секунд | Task 8 |
| Расшифровка донора в устный стиль | Task 8 |
| Расшифровка не удалась → донор сохраняется | Task 8 |
| Склейка дорожек всех доноров | Task 5, 9 |
| Клонирование голоса | Task 6, 9 |
| Клонирование не удалось → профиль не создаётся | Task 9 |
| Экран «Мой двойник» | Task 7, 8, 11 |
| Удаление двойника и всех данных | Task 10 |
| Видео на диске не хранятся | Task 8, 9 (временные файлы удаляются в `finally`) |
| ffmpeg как зависимость деплоя | Task 11 |
| Локализация на 4 языка | Task 7 |

**Вне этапа 1 и осознанно не покрыто планом:** кнопка «🎥 ЗАПИШИ КРУЖОК» под дайджестом, `circle_jobs`, `circle_usage`, `lipsync_gateway`, `circle_pipeline`, `circle_worker`, `video_note.py`, `plan_donor_fit`, синтез речи, ротация доноров по `last_used_at`, «Перетренировать голос». Всё это — этап 2.
