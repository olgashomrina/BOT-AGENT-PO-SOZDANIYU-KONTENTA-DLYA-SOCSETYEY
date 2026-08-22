# Говорящий двойник — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Готовый двойник (лицо, образы, голос) произносит речь, написанную текстом или наговорённую голосом, и отдаёт её кружком — без пересоздания двойника.

**Architecture:** Хранилища (`avatar_faces`, `avatar_looks`, `speech_jobs`, `render_usage`) держат состояние в SQLite. Шлюзы (`avatar_gateway`, `voice_gateway`, `ai_gateway.edit_image`) знают про провайдеров и не знают про бота. Оркестратор `speech_pipeline` ведёт задание по статусам и не знает про aiogram. Фоновый воркер опрашивает провайдера и уведомляет пользователя. Хендлеры рисуют экраны и не знают, какой движок под капотом.

**Tech Stack:** Python 3.11+, aiogram 3, httpx, SQLite, APScheduler, ffmpeg/ffprobe, pytest + pytest-asyncio + respx.

Спека: `docs/superpowers/specs/2026-08-22-talking-double-design.md`.
Замеры и контракты провайдеров: `docs/reference-video-avatar-engines.md`.

## Global Constraints

- Язык комментариев и строк локали `ru` — русский; имена функций и переменных — английские. Так написан весь существующий код.
- Каждый файл начинается с `from __future__ import annotations`.
- Хранилища открывают соединение через `bot.storage.db.get_connection(db_path)` и закрывают его в `finally`. Никаких глобальных соединений.
- Время — только UTC ISO-8601: `datetime.now(timezone.utc).isoformat()`.
- Настройки читаются через `bot.config.load_settings()` **внутри** функции, а не на импорте модуля.
- Личные фото и аудио уходят провайдеру **только base64**, в виде `data:image/jpeg;base64,...` и `data:audio/mpeg;base64,...`. Публичная ссылка на личный файл не формируется никогда.
- Движок рендера: `klingai:avatar@2.0-standard`, форма входа `inputs.image` + `inputs.audio`, обе **строками**.
- Video note: квадрат, H.264 + AAC, `+faststart`, сторона 512, не длиннее 60 секунд.
- Доступ — вайтлист, он же список купивших подписку. `WhitelistMiddleware` зарегистрирован только на сообщениях, поэтому каждый **платный** обработчик callback-кнопки зовёт `check_whitelist_or_reply` из `bot/handlers/guards.py` сам.
- Тесты: `pytest`, асинхронные помечаются `@pytest.mark.asyncio`, HTTP мокается `respx`, БД берётся фикстурой `db_path` из `tests/conftest.py`, хендлеры вызываются напрямую с `MagicMock`/`AsyncMock`.
- Прогон всех тестов: `python -m pytest -q` из корня проекта.
- Коммит после каждой задачи, сообщение на английском, префиксы `feat:` / `fix:` / `docs:` как в истории репозитория.

## Отклонения от спеки (осознанные, с причиной)

1. **Хендлеры не складываются в `bot/handlers/circle.py`.** Файл уже 320 строк и отвечает за сбор доноров. Новые экраны разъезжаются по двум файлам: `bot/handlers/double.py` (лицо и образы) и `bot/handlers/speech.py` (речь). В `circle.py` меняется ровно один обработчик — `on_my_double`, рисующий экран двойника.
2. **`bot/services/ffmpeg_tools.py` получает одну публичную функцию** `run_ffmpeg`. Спека обещала не трогать файл, но `video_note.py` иначе продублировал бы запуск процесса вместе с разбором кода возврата и логированием.

## Структура файлов

| Файл | Ответственность |
|---|---|
| `bot/storage/avatar_faces.py` | Базовое лицо: одна строка на пользователя |
| `bot/storage/avatar_looks.py` | Образы и ровно один активный |
| `bot/storage/speech_jobs.py` | Задания рендера и их статусы |
| `bot/storage/render_usage.py` | Секунды и деньги по месяцам |
| `bot/services/look_prompt.py` | Чистая сборка промпта образа |
| `bot/services/avatar_gateway.py` | Говорящее видео: запуск и опрос |
| `bot/services/video_note.py` | ffmpeg: апскейл образа, приведение к video note |
| `bot/services/speech_pipeline.py` | Оркестратор задания, деньги, лимиты |
| `bot/services/speech_worker.py` | Фоновый опрос и уведомление |
| `bot/handlers/double.py` | Экраны лица и образов |
| `bot/handlers/speech.py` | Экраны речи ①–④ |

---

### Task 1: Настройки двойника

**Files:**
- Modify: `bot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: ничего.
- Produces: поля `Settings`: `avatar_provider: str`, `avatar_model: str`, `avatar_look_model: str`, `avatar_target_seconds: int`, `avatar_max_seconds: int`, `avatar_monthly_seconds_limit: int`, `avatar_voice_synthesis_enabled: bool`, `avatar_poll_interval_seconds: int`.

- [ ] **Step 1: Write the failing test**

Дописать в конец `tests/test_config.py`:

```python
def test_avatar_settings_have_measured_defaults(monkeypatch):
    for key in (
        "AVATAR_PROVIDER",
        "AVATAR_MODEL",
        "AVATAR_LOOK_MODEL",
        "AVATAR_TARGET_SECONDS",
        "AVATAR_MAX_SECONDS",
        "AVATAR_MONTHLY_SECONDS_LIMIT",
        "AVATAR_VOICE_SYNTHESIS_ENABLED",
        "AVATAR_POLL_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.avatar_provider == "runware"
    assert settings.avatar_model == "klingai:avatar@2.0-standard"
    assert settings.avatar_look_model == "google:4@1"
    assert settings.avatar_target_seconds == 30
    assert settings.avatar_max_seconds == 60
    assert settings.avatar_monthly_seconds_limit == 300
    assert settings.avatar_voice_synthesis_enabled is False
    assert settings.avatar_poll_interval_seconds == 20


def test_avatar_voice_synthesis_flag_reads_truthy_words(monkeypatch):
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "true")
    assert load_settings().avatar_voice_synthesis_enabled is True

    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "0")
    assert load_settings().avatar_voice_synthesis_enabled is False


def test_avatar_seconds_must_be_integers(monkeypatch):
    monkeypatch.setenv("AVATAR_MAX_SECONDS", "минута")

    with pytest.raises(ConfigError):
        load_settings()
```

Проверить, что `ConfigError` и `load_settings` уже импортированы в этом файле; если нет — дописать в импорты `from bot.config import ConfigError, load_settings`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -q -k avatar`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'avatar_provider'`.

- [ ] **Step 3: Write minimal implementation**

В `bot/config.py` рядом с остальными константами по умолчанию (после `DEFAULT_ELEVENLABS_BASE_URL`) добавить:

```python
# Движок говорящего видео. Выбран замерами 2026-08-06 на десяти движках:
# 270 ₽ за минуту при качестве, которое владелец утвердила. Соседи по цене
# и форма их входа — в docs/reference-video-avatar-engines.md; смена движка
# делается этой настройкой, без правки кода.
DEFAULT_AVATAR_PROVIDER = "runware"
DEFAULT_AVATAR_MODEL = "klingai:avatar@2.0-standard"
DEFAULT_AVATAR_LOOK_MODEL = "google:4@1"

# 30 секунд вдвое дешевле шестидесяти и лучше досматриваются; 60 — жёсткий
# предел формата video note, а не предпочтение.
DEFAULT_AVATAR_TARGET_SECONDS = 30
DEFAULT_AVATAR_MAX_SECONDS = 60

# 300 секунд рендера в месяц на пользователя — 10 кружков по 30 секунд,
# около 1350 ₽. Потолок в секундах, а не в запросах: RateLimitMiddleware
# считает обращения, здесь важны деньги.
DEFAULT_AVATAR_MONTHLY_SECONDS_LIMIT = 300

# Рендер пяти секунд занимал 213–520 с. Опрос раз в 20 секунд не нагружает
# провайдера и не заставляет пользователя ждать лишнюю минуту после готовности.
DEFAULT_AVATAR_POLL_INTERVAL_SECONDS = 20
```

В `dataclass Settings` после `tmp_media_dir` добавить:

```python
    avatar_provider: str
    avatar_model: str
    avatar_look_model: str
    avatar_target_seconds: int
    avatar_max_seconds: int
    avatar_monthly_seconds_limit: int
    avatar_voice_synthesis_enabled: bool
    avatar_poll_interval_seconds: int
```

Рядом с `_optional` добавить помощник:

```python
def _flag(key: str, default: bool) -> bool:
    """Булева переменная окружения.

    Пустая строка означает «не задано» — по той же причине, что в `_optional`:
    `.env.example` предлагает оставлять необязательные строки пустыми.
    """
    raw = os.environ.get(key)
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}
```

В теле `load_settings` перед сборкой `Settings(...)`:

```python
    avatar_provider = _optional("AVATAR_PROVIDER", DEFAULT_AVATAR_PROVIDER)
    avatar_model = _optional("AVATAR_MODEL", DEFAULT_AVATAR_MODEL)
    avatar_look_model = _optional("AVATAR_LOOK_MODEL", DEFAULT_AVATAR_LOOK_MODEL)
    avatar_voice_synthesis_enabled = _flag("AVATAR_VOICE_SYNTHESIS_ENABLED", False)

    try:
        avatar_target_seconds = int(
            os.environ.get("AVATAR_TARGET_SECONDS", DEFAULT_AVATAR_TARGET_SECONDS)
        )
        avatar_max_seconds = int(
            os.environ.get("AVATAR_MAX_SECONDS", DEFAULT_AVATAR_MAX_SECONDS)
        )
        avatar_monthly_seconds_limit = int(
            os.environ.get(
                "AVATAR_MONTHLY_SECONDS_LIMIT", DEFAULT_AVATAR_MONTHLY_SECONDS_LIMIT
            )
        )
        avatar_poll_interval_seconds = int(
            os.environ.get(
                "AVATAR_POLL_INTERVAL_SECONDS", DEFAULT_AVATAR_POLL_INTERVAL_SECONDS
            )
        )
    except ValueError as exc:
        raise ConfigError(
            "AVATAR_TARGET_SECONDS, AVATAR_MAX_SECONDS, "
            "AVATAR_MONTHLY_SECONDS_LIMIT и AVATAR_POLL_INTERVAL_SECONDS "
            "должны быть целыми числами."
        ) from exc
```

И в сам вызов `Settings(...)` — восемь новых аргументов:

```python
        avatar_provider=avatar_provider,
        avatar_model=avatar_model,
        avatar_look_model=avatar_look_model,
        avatar_target_seconds=avatar_target_seconds,
        avatar_max_seconds=avatar_max_seconds,
        avatar_monthly_seconds_limit=avatar_monthly_seconds_limit,
        avatar_voice_synthesis_enabled=avatar_voice_synthesis_enabled,
        avatar_poll_interval_seconds=avatar_poll_interval_seconds,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS, все тесты файла.

- [ ] **Step 5: Commit**

```bash
git add bot/config.py tests/test_config.py
git commit -m "feat: add the talking-double settings"
```

---

### Task 2: Четыре таблицы в схеме

**Files:**
- Modify: `bot/storage/db.py`
- Test: `tests/test_storage_db_double_schema.py`

**Interfaces:**
- Consumes: `bot.storage.db.init_db`, `get_connection`.
- Produces: таблицы `avatar_faces`, `avatar_looks`, `speech_jobs`, `render_usage`.

- [ ] **Step 1: Write the failing test**

Дописать в конец `tests/test_storage_db_double_schema.py`:

```python
def _columns(db_path: str, table: str) -> set[str]:
    connection = get_connection(db_path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def test_avatar_faces_table_holds_one_row_per_user(db_path):
    assert _columns(db_path, "avatar_faces") == {
        "telegram_id",
        "file_id",
        "created_at",
    }


def test_avatar_looks_table_has_activity_flag(db_path):
    assert _columns(db_path, "avatar_looks") == {
        "id",
        "telegram_id",
        "file_id",
        "title",
        "source",
        "prompt",
        "is_active",
        "created_at",
    }


def test_speech_jobs_table_carries_money_and_format(db_path):
    assert _columns(db_path, "speech_jobs") == {
        "id",
        "telegram_id",
        "source_text",
        "script",
        "look_id",
        "audio_path",
        "audio_duration_sec",
        "format",
        "status",
        "provider_task_id",
        "result_file_id",
        "cost_rub",
        "error",
        "created_at",
        "updated_at",
    }


def test_render_usage_is_keyed_by_user_and_month(db_path):
    assert _columns(db_path, "render_usage") == {
        "telegram_id",
        "usage_month",
        "seconds_rendered",
        "cost_rub",
    }


def test_init_db_is_idempotent_on_an_existing_database(db_path):
    # Развёрнутая база уже существует: повторный init_db не должен ни падать,
    # ни стирать данные. Это и есть вся миграция для новых таблиц.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO avatar_faces (telegram_id, file_id, created_at) VALUES (1, 'f', 'now')"
        )
        connection.commit()
    finally:
        connection.close()

    init_db(db_path)

    connection = get_connection(db_path)
    try:
        row = connection.execute("SELECT file_id FROM avatar_faces").fetchone()
    finally:
        connection.close()
    assert row[0] == "f"
```

Проверить импорты файла: нужны `from bot.storage.db import get_connection, init_db`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage_db_double_schema.py -q`
Expected: FAIL — четыре новых теста падают, `PRAGMA table_info` возвращает пустое множество.

- [ ] **Step 3: Write minimal implementation**

В `bot/storage/db.py` в конец строки `SCHEMA` (перед закрывающими кавычками) добавить:

```sql
-- Лицо ровно одно на пользователя: замена перезаписывает строку, поэтому
-- ключ — telegram_id, а не автоинкремент.
CREATE TABLE IF NOT EXISTS avatar_faces (
    telegram_id INTEGER PRIMARY KEY,
    file_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Образов много, активный один. Флаг снимается со старого и ставится новому
-- в одной транзакции (bot/storage/avatar_looks.py) — частичного уникального
-- индекса тут недостаточно, он бы только запретил второй активный, а не
-- обеспечил ровно один.
CREATE TABLE IF NOT EXISTS avatar_looks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    file_id TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    prompt TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Задания рендера живут в базе, а не в состоянии диалога: рестарт бота
-- посреди оплаченного рендера — это выброшенные 135 ₽. audio_path хранит
-- кэш озвучки, из-за которого смена образа не пересинтезирует голос.
-- format пока всегда 'video_note'; длинное видео добавится значением.
CREATE TABLE IF NOT EXISTS speech_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    script TEXT,
    look_id INTEGER,
    audio_path TEXT,
    audio_duration_sec REAL,
    format TEXT NOT NULL DEFAULT 'video_note',
    status TEXT NOT NULL,
    provider_task_id TEXT,
    result_file_id TEXT,
    cost_rub REAL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Отдельно от usage_log: тот считает обращения, а рендер меряется секундами
-- и рублями. Один кружок стоит как несколько сотен текстовых генераций.
CREATE TABLE IF NOT EXISTS render_usage (
    telegram_id INTEGER NOT NULL,
    usage_month TEXT NOT NULL,
    seconds_rendered INTEGER NOT NULL DEFAULT 0,
    cost_rub REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (telegram_id, usage_month)
);
```

Отдельной процедуры миграции не добавлять: новых колонок в старых таблицах нет, `CREATE TABLE IF NOT EXISTS` покрывает и чистую установку, и развёрнутую базу.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_storage_db_double_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/storage/db.py tests/test_storage_db_double_schema.py
git commit -m "feat: add the talking-double tables to the schema"
```

---

### Task 3: Хранилище лица

**Files:**
- Create: `bot/storage/avatar_faces.py`
- Test: `tests/test_storage_avatar_faces.py`

**Interfaces:**
- Consumes: таблица `avatar_faces` (Task 2).
- Produces: `Face(file_id: str, created_at: str)`, `save_face(db_path: str, telegram_id: int, file_id: str) -> None`, `get_face(db_path: str, telegram_id: int) -> Face | None`, `delete_face(db_path: str, telegram_id: int) -> None`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_avatar_faces.py`:

```python
from __future__ import annotations

from bot.storage.avatar_faces import delete_face, get_face, save_face

TELEGRAM_ID = 501


def test_missing_face_reads_as_none(db_path):
    assert get_face(db_path, TELEGRAM_ID) is None


def test_saved_face_reads_back(db_path):
    save_face(db_path, TELEGRAM_ID, "photo-1")

    face = get_face(db_path, TELEGRAM_ID)

    assert face is not None
    assert face.file_id == "photo-1"
    assert face.created_at


def test_second_save_replaces_the_face(db_path):
    # Лицо ровно одно: «Заменить лицо» должно заменять, а не копить.
    save_face(db_path, TELEGRAM_ID, "photo-1")
    save_face(db_path, TELEGRAM_ID, "photo-2")

    assert get_face(db_path, TELEGRAM_ID).file_id == "photo-2"


def test_faces_are_per_user(db_path):
    save_face(db_path, TELEGRAM_ID, "photo-mine")
    save_face(db_path, 502, "photo-theirs")

    assert get_face(db_path, TELEGRAM_ID).file_id == "photo-mine"


def test_delete_removes_the_face(db_path):
    save_face(db_path, TELEGRAM_ID, "photo-1")

    delete_face(db_path, TELEGRAM_ID)

    assert get_face(db_path, TELEGRAM_ID) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage_avatar_faces.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.avatar_faces'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/storage/avatar_faces.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection


@dataclass(frozen=True)
class Face:
    file_id: str
    created_at: str


def save_face(db_path: str, telegram_id: int, file_id: str) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO avatar_faces (telegram_id, file_id, created_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET "
            "file_id = excluded.file_id, created_at = excluded.created_at",
            (telegram_id, file_id, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def get_face(db_path: str, telegram_id: int) -> Face | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT file_id, created_at FROM avatar_faces WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return None if row is None else Face(file_id=row[0], created_at=row[1])
    finally:
        connection.close()


def delete_face(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_faces WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_storage_avatar_faces.py -q`
Expected: PASS, 5 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/storage/avatar_faces.py tests/test_storage_avatar_faces.py
git commit -m "feat: store the double's base face"
```

---

### Task 4: Хранилище образов

**Files:**
- Create: `bot/storage/avatar_looks.py`
- Test: `tests/test_storage_avatar_looks.py`

**Interfaces:**
- Consumes: таблица `avatar_looks` (Task 2).
- Produces: `SOURCE_UPLOADED = "uploaded"`, `SOURCE_GENERATED = "generated"`, `Look(id: int, file_id: str, title: str, source: str, prompt: str | None, is_active: bool, created_at: str)`, `add_look(db_path: str, telegram_id: int, file_id: str, title: str, source: str, prompt: str | None = None) -> int`, `get_looks(db_path: str, telegram_id: int) -> list[Look]`, `get_look(db_path: str, telegram_id: int, look_id: int) -> Look | None`, `get_active_look(db_path: str, telegram_id: int) -> Look | None`, `set_active_look(db_path: str, telegram_id: int, look_id: int) -> None`, `delete_look(db_path: str, telegram_id: int, look_id: int) -> None`, `clear_looks(db_path: str, telegram_id: int) -> None`, `count_looks(db_path: str, telegram_id: int) -> int`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_avatar_looks.py`:

```python
from __future__ import annotations

from bot.storage.avatar_looks import (
    SOURCE_GENERATED,
    SOURCE_UPLOADED,
    add_look,
    clear_looks,
    count_looks,
    delete_look,
    get_active_look,
    get_look,
    get_looks,
    set_active_look,
)

TELEGRAM_ID = 601


def test_no_looks_reads_as_none_and_zero(db_path):
    assert get_looks(db_path, TELEGRAM_ID) == []
    assert get_active_look(db_path, TELEGRAM_ID) is None
    assert count_looks(db_path, TELEGRAM_ID) == 0


def test_first_look_becomes_active_by_itself(db_path):
    # Иначе первый же образ пришлось бы включать вторым действием, и сценарий
    # речи упирался бы в «активного образа нет» сразу после добавления.
    look_id = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)

    active = get_active_look(db_path, TELEGRAM_ID)
    assert active is not None
    assert active.id == look_id
    assert active.is_active is True


def test_second_look_does_not_steal_activity(db_path):
    first = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    assert get_active_look(db_path, TELEGRAM_ID).id == first


def test_set_active_moves_the_flag_and_leaves_exactly_one(db_path):
    add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    second = add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    set_active_look(db_path, TELEGRAM_ID, second)

    assert get_active_look(db_path, TELEGRAM_ID).id == second
    assert [look.is_active for look in get_looks(db_path, TELEGRAM_ID)].count(True) == 1


def test_generated_look_keeps_its_prompt(db_path):
    look_id = add_look(
        db_path,
        TELEGRAM_ID,
        "img-1",
        "вечер",
        SOURCE_GENERATED,
        prompt="белая рубашка, тёмный фон",
    )

    look = get_look(db_path, TELEGRAM_ID, look_id)
    assert look.source == SOURCE_GENERATED
    assert look.prompt == "белая рубашка, тёмный фон"


def test_looks_are_per_user(db_path):
    add_look(db_path, TELEGRAM_ID, "img-mine", "студия", SOURCE_UPLOADED)
    add_look(db_path, 602, "img-theirs", "улица", SOURCE_UPLOADED)

    assert [look.file_id for look in get_looks(db_path, TELEGRAM_ID)] == ["img-mine"]
    assert get_look(db_path, TELEGRAM_ID, 2) is None


def test_deleting_the_active_look_promotes_the_newest_remaining(db_path):
    # Без этого удаление активного образа оставило бы пользователя без
    # активного вовсе, и следующая речь уперлась бы в пустой экран.
    first = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    second = add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    delete_look(db_path, TELEGRAM_ID, first)

    assert get_active_look(db_path, TELEGRAM_ID).id == second


def test_deleting_the_last_look_leaves_nothing_active(db_path):
    only = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)

    delete_look(db_path, TELEGRAM_ID, only)

    assert get_active_look(db_path, TELEGRAM_ID) is None


def test_clear_removes_every_look_of_the_user(db_path):
    add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    clear_looks(db_path, TELEGRAM_ID)

    assert get_looks(db_path, TELEGRAM_ID) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage_avatar_looks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.avatar_looks'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/storage/avatar_looks.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection

# Присланная пользователем картинка и картинка, которую бот собрал из лица
# по описанию, ведут себя одинаково при рендере, но по-разному объясняются
# в интерфейсе: у второй есть промпт, который можно показать и повторить.
SOURCE_UPLOADED = "uploaded"
SOURCE_GENERATED = "generated"

_FIELDS = "id, file_id, title, source, prompt, is_active, created_at"


@dataclass(frozen=True)
class Look:
    id: int
    file_id: str
    title: str
    source: str
    prompt: str | None
    is_active: bool
    created_at: str


def _row_to_look(row: tuple) -> Look:
    return Look(
        id=row[0],
        file_id=row[1],
        title=row[2],
        source=row[3],
        prompt=row[4],
        is_active=bool(row[5]),
        created_at=row[6],
    )


def add_look(
    db_path: str,
    telegram_id: int,
    file_id: str,
    title: str,
    source: str,
    prompt: str | None = None,
) -> int:
    connection = get_connection(db_path)
    try:
        has_active = connection.execute(
            "SELECT 1 FROM avatar_looks WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        cursor = connection.execute(
            "INSERT INTO avatar_looks "
            "(telegram_id, file_id, title, source, prompt, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                telegram_id,
                file_id,
                title,
                source,
                prompt,
                0 if has_active else 1,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_looks(db_path: str, telegram_id: int) -> list[Look]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            f"SELECT {_FIELDS} FROM avatar_looks WHERE telegram_id = ? ORDER BY id ASC",
            (telegram_id,),
        ).fetchall()
        return [_row_to_look(row) for row in rows]
    finally:
        connection.close()


def get_look(db_path: str, telegram_id: int, look_id: int) -> Look | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM avatar_looks WHERE telegram_id = ? AND id = ?",
            (telegram_id, look_id),
        ).fetchone()
        return None if row is None else _row_to_look(row)
    finally:
        connection.close()


def get_active_look(db_path: str, telegram_id: int) -> Look | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM avatar_looks "
            "WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        return None if row is None else _row_to_look(row)
    finally:
        connection.close()


def count_looks(db_path: str, telegram_id: int) -> int:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM avatar_looks WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def set_active_look(db_path: str, telegram_id: int, look_id: int) -> None:
    # Снятие и установка флага — одна транзакция: между ними база не должна
    # быть видна ни с двумя активными образами, ни с нулём.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "UPDATE avatar_looks SET is_active = 0 WHERE telegram_id = ?",
            (telegram_id,),
        )
        connection.execute(
            "UPDATE avatar_looks SET is_active = 1 WHERE telegram_id = ? AND id = ?",
            (telegram_id, look_id),
        )
        connection.commit()
    finally:
        connection.close()


def delete_look(db_path: str, telegram_id: int, look_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_looks WHERE telegram_id = ? AND id = ?",
            (telegram_id, look_id),
        )
        orphaned = connection.execute(
            "SELECT 1 FROM avatar_looks WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        if orphaned is None:
            # Удалили активный образ — активным становится самый свежий из
            # оставшихся. Иначе следующая речь упрётся в «образа нет», хотя
            # образы у пользователя есть.
            connection.execute(
                "UPDATE avatar_looks SET is_active = 1 WHERE id = ("
                "SELECT id FROM avatar_looks WHERE telegram_id = ? "
                "ORDER BY id DESC LIMIT 1)",
                (telegram_id,),
            )
        connection.commit()
    finally:
        connection.close()


def clear_looks(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_looks WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_storage_avatar_looks.py -q`
Expected: PASS, 9 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/storage/avatar_looks.py tests/test_storage_avatar_looks.py
git commit -m "feat: store the double's looks with exactly one active"
```

---

### Task 5: Хранилище заданий речи

**Files:**
- Create: `bot/storage/speech_jobs.py`
- Test: `tests/test_storage_speech_jobs.py`

**Interfaces:**
- Consumes: таблица `speech_jobs` (Task 2).
- Produces: `STATUS_DRAFT = "draft"`, `STATUS_VOICED = "voiced"`, `STATUS_RENDERING = "rendering"`, `STATUS_READY = "ready"`, `STATUS_PUBLISHED = "published"`, `STATUS_FAILED = "failed"`, `FORMAT_VIDEO_NOTE = "video_note"`, `SpeechJob` (поля один в один с колонками таблицы), `create_job(db_path: str, telegram_id: int, source_text: str) -> int`, `get_job(db_path: str, job_id: int) -> SpeechJob | None`, `get_active_job(db_path: str, telegram_id: int) -> SpeechJob | None`, `get_jobs_by_status(db_path: str, status: str) -> list[SpeechJob]`, `update_job(db_path: str, job_id: int, **fields) -> None`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_speech_jobs.py`:

```python
from __future__ import annotations

import pytest

from bot.storage.speech_jobs import (
    FORMAT_VIDEO_NOTE,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_PUBLISHED,
    STATUS_RENDERING,
    STATUS_VOICED,
    create_job,
    get_active_job,
    get_job,
    get_jobs_by_status,
    update_job,
)

TELEGRAM_ID = 701


def test_new_job_starts_as_a_draft_video_note(db_path):
    job_id = create_job(db_path, TELEGRAM_ID, "Расскажу про запуск")

    job = get_job(db_path, job_id)
    assert job.status == STATUS_DRAFT
    assert job.format == FORMAT_VIDEO_NOTE
    assert job.source_text == "Расскажу про запуск"
    assert job.script is None
    assert job.audio_path is None
    assert job.created_at and job.updated_at


def test_update_writes_the_named_fields_and_bumps_updated_at(db_path):
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    before = get_job(db_path, job_id).updated_at

    update_job(
        db_path,
        job_id,
        status=STATUS_VOICED,
        audio_path="/tmp/a.mp3",
        audio_duration_sec=28.4,
    )

    job = get_job(db_path, job_id)
    assert job.status == STATUS_VOICED
    assert job.audio_path == "/tmp/a.mp3"
    assert job.audio_duration_sec == pytest.approx(28.4)
    assert job.updated_at >= before


def test_update_refuses_an_unknown_column(db_path):
    # Иначе опечатка в имени поля молча ничего не записала бы, а задание
    # осталось бы в прежнем статусе — с уже оплаченным рендером.
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    with pytest.raises(ValueError):
        update_job(db_path, job_id, statuss=STATUS_VOICED)


def test_jobs_by_status_finds_what_the_worker_must_pick_up(db_path):
    mine = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, mine, status=STATUS_RENDERING, provider_task_id="task-1")
    create_job(db_path, TELEGRAM_ID, "другой текст")

    rendering = get_jobs_by_status(db_path, STATUS_RENDERING)

    assert [job.id for job in rendering] == [mine]
    assert rendering[0].provider_task_id == "task-1"


def test_active_job_is_the_latest_unfinished_one(db_path):
    finished = create_job(db_path, TELEGRAM_ID, "старое")
    update_job(db_path, finished, status=STATUS_PUBLISHED)
    current = create_job(db_path, TELEGRAM_ID, "новое")

    assert get_active_job(db_path, TELEGRAM_ID).id == current


def test_failed_and_published_jobs_are_not_active(db_path):
    failed = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, failed, status=STATUS_FAILED, error="провайдер отказал")

    assert get_active_job(db_path, TELEGRAM_ID) is None


def test_active_job_is_per_user(db_path):
    create_job(db_path, 702, "чужое")

    assert get_active_job(db_path, TELEGRAM_ID) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage_speech_jobs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.speech_jobs'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/storage/speech_jobs.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection

STATUS_DRAFT = "draft"
STATUS_VOICED = "voiced"
STATUS_RENDERING = "rendering"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"

# Задание закончено, когда ролик опубликован или сгорел. Всё остальное —
# незавершённая работа, к которой пользователь может вернуться.
_TERMINAL_STATUSES = (STATUS_PUBLISHED, STATUS_FAILED)

FORMAT_VIDEO_NOTE = "video_note"

# Колонки, которые вправе менять `update_job`. Список закрытый: имя поля
# приходит из кода как строка, и опечатка иначе прошла бы молча.
_UPDATABLE = frozenset(
    {
        "source_text",
        "script",
        "look_id",
        "audio_path",
        "audio_duration_sec",
        "format",
        "status",
        "provider_task_id",
        "result_file_id",
        "cost_rub",
        "error",
    }
)

_FIELDS = (
    "id, telegram_id, source_text, script, look_id, audio_path, "
    "audio_duration_sec, format, status, provider_task_id, result_file_id, "
    "cost_rub, error, created_at, updated_at"
)


@dataclass(frozen=True)
class SpeechJob:
    id: int
    telegram_id: int
    source_text: str
    script: str | None
    look_id: int | None
    audio_path: str | None
    audio_duration_sec: float | None
    format: str
    status: str
    provider_task_id: str | None
    result_file_id: str | None
    cost_rub: float | None
    error: str | None
    created_at: str
    updated_at: str


def _row_to_job(row: tuple) -> SpeechJob:
    return SpeechJob(*row)


def create_job(db_path: str, telegram_id: int, source_text: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            "INSERT INTO speech_jobs "
            "(telegram_id, source_text, format, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, source_text, FORMAT_VIDEO_NOTE, STATUS_DRAFT, now, now),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_job(db_path: str, job_id: int) -> SpeechJob | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM speech_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return None if row is None else _row_to_job(row)
    finally:
        connection.close()


def get_active_job(db_path: str, telegram_id: int) -> SpeechJob | None:
    placeholders = ", ".join("?" for _ in _TERMINAL_STATUSES)
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM speech_jobs WHERE telegram_id = ? "
            f"AND status NOT IN ({placeholders}) ORDER BY id DESC LIMIT 1",
            (telegram_id, *_TERMINAL_STATUSES),
        ).fetchone()
        return None if row is None else _row_to_job(row)
    finally:
        connection.close()


def get_jobs_by_status(db_path: str, status: str) -> list[SpeechJob]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            f"SELECT {_FIELDS} FROM speech_jobs WHERE status = ? ORDER BY id ASC",
            (status,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]
    finally:
        connection.close()


def update_job(db_path: str, job_id: int, **fields) -> None:
    unknown = set(fields) - _UPDATABLE
    if unknown:
        raise ValueError(f"Неизвестные поля задания: {sorted(unknown)}")
    if not fields:
        return

    assignments = ", ".join(f"{name} = ?" for name in fields)
    connection = get_connection(db_path)
    try:
        connection.execute(
            f"UPDATE speech_jobs SET {assignments}, updated_at = ? WHERE id = ?",
            (*fields.values(), datetime.now(timezone.utc).isoformat(), job_id),
        )
        connection.commit()
    finally:
        connection.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_storage_speech_jobs.py -q`
Expected: PASS, 7 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/storage/speech_jobs.py tests/test_storage_speech_jobs.py
git commit -m "feat: store speech render jobs in sqlite"
```

---

### Task 6: Счётчик секунд и денег

**Files:**
- Create: `bot/storage/render_usage.py`
- Test: `tests/test_storage_render_usage.py`

**Interfaces:**
- Consumes: таблица `render_usage` (Task 2).
- Produces: `add_usage(db_path: str, telegram_id: int, seconds: int, cost_rub: float, now: datetime | None = None) -> None`, `get_month_seconds(db_path: str, telegram_id: int, now: datetime | None = None) -> int`, `seconds_left(db_path: str, telegram_id: int, limit: int, now: datetime | None = None) -> int`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_storage_render_usage.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.storage.render_usage import add_usage, get_month_seconds, seconds_left

TELEGRAM_ID = 801
AUGUST = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
SEPTEMBER = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def test_untouched_user_has_the_whole_limit(db_path):
    assert get_month_seconds(db_path, TELEGRAM_ID, now=AUGUST) == 0
    assert seconds_left(db_path, TELEGRAM_ID, 300, now=AUGUST) == 300


def test_usage_accumulates_within_the_month(db_path):
    add_usage(db_path, TELEGRAM_ID, 30, 135.0, now=AUGUST)
    add_usage(db_path, TELEGRAM_ID, 30, 135.0, now=AUGUST)

    assert get_month_seconds(db_path, TELEGRAM_ID, now=AUGUST) == 60
    assert seconds_left(db_path, TELEGRAM_ID, 300, now=AUGUST) == 240


def test_a_new_month_starts_from_zero(db_path):
    add_usage(db_path, TELEGRAM_ID, 300, 1350.0, now=AUGUST)

    assert get_month_seconds(db_path, TELEGRAM_ID, now=SEPTEMBER) == 0
    assert seconds_left(db_path, TELEGRAM_ID, 300, now=SEPTEMBER) == 300


def test_usage_is_per_user(db_path):
    add_usage(db_path, 802, 300, 1350.0, now=AUGUST)

    assert get_month_seconds(db_path, TELEGRAM_ID, now=AUGUST) == 0


def test_seconds_left_never_goes_negative(db_path):
    # Провайдер может отрендерить чуть длиннее заказанного; отрицательный
    # остаток превратил бы отказ по лимиту в странное «осталось -4 секунды».
    add_usage(db_path, TELEGRAM_ID, 310, 1400.0, now=AUGUST)

    assert seconds_left(db_path, TELEGRAM_ID, 300, now=AUGUST) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_storage_render_usage.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.storage.render_usage'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/storage/render_usage.py`:

```python
"""Сколько секунд рендера и рублей потратил каждый пользователь за месяц.

Отдельно от `usage_log` и `cost_log` намеренно. `usage_log` считает обращения,
и рендер в тех же единицах не меряется: один кружок стоит как несколько сотен
текстовых генераций. `cost_log` — общая летопись расходов для отчёта; здесь
же лежит счётчик, по которому принимается решение «пускать или отказать»,
и ему нужен быстрый ответ по одному ключу.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection


def _resolve_month(now: datetime | None) -> str:
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.strftime("%Y-%m")


def add_usage(
    db_path: str,
    telegram_id: int,
    seconds: int,
    cost_rub: float,
    now: datetime | None = None,
) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO render_usage "
            "(telegram_id, usage_month, seconds_rendered, cost_rub) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(telegram_id, usage_month) DO UPDATE SET "
            "seconds_rendered = seconds_rendered + excluded.seconds_rendered, "
            "cost_rub = cost_rub + excluded.cost_rub",
            (telegram_id, _resolve_month(now), seconds, cost_rub),
        )
        connection.commit()
    finally:
        connection.close()


def get_month_seconds(
    db_path: str, telegram_id: int, now: datetime | None = None
) -> int:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT seconds_rendered FROM render_usage "
            "WHERE telegram_id = ? AND usage_month = ?",
            (telegram_id, _resolve_month(now)),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def seconds_left(
    db_path: str, telegram_id: int, limit: int, now: datetime | None = None
) -> int:
    return max(0, limit - get_month_seconds(db_path, telegram_id, now=now))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_storage_render_usage.py -q`
Expected: PASS, 5 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/storage/render_usage.py tests/test_storage_render_usage.py
git commit -m "feat: count rendered seconds and rubles per month"
```

---

### Task 7: Промпт образа

**Files:**
- Create: `bot/services/look_prompt.py`
- Test: `tests/test_services_look_prompt.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `build_look_prompt(description: str) -> str`, `mentions_hair(description: str) -> bool`, `BANNED_PHRASES: tuple[str, ...]`.

Рецепт взят из `docs/reference-video-avatar-engines.md`, раздел «Рецепт образа, дающий сходство лица». Он куплен тремя неудачными попытками, поэтому живёт в коде правилами, а не в голове пользователя.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_look_prompt.py`:

```python
from __future__ import annotations

import pytest

from bot.services.look_prompt import BANNED_PHRASES, build_look_prompt, mentions_hair


def test_prompt_carries_the_user_description():
    prompt = build_look_prompt("белая рубашка, тёмный фон, мягкий свет")

    assert "белая рубашка, тёмный фон, мягкий свет" in prompt


def test_prompt_demands_a_close_up_head_and_shoulders_frame():
    # Первый образ был собран общим планом, лицо заняло пятую часть кадра,
    # и движок был забракован несправедливо. Крупный план — не пожелание.
    prompt = build_look_prompt("студия").lower()

    assert "close-up" in prompt
    assert "head and shoulders" in prompt


def test_prompt_demands_a_frontal_pose_and_the_same_face():
    prompt = build_look_prompt("студия").lower()

    assert "frontal" in prompt
    assert "same face" in prompt


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_banned_phrases_are_stripped_from_the_description(phrase):
    # «editorial fashion photography» и родня тянут к обобщённому модельному
    # лицу — проверено на живых генерациях.
    prompt = build_look_prompt(f"студия, {phrase}, мягкий свет")

    assert phrase not in prompt.lower()


def test_empty_description_still_produces_a_usable_prompt():
    prompt = build_look_prompt("   ")

    assert prompt.strip()
    assert "close-up" in prompt.lower()


@pytest.mark.parametrize(
    "description",
    ["сделай каре", "длинные волосы", "hair down", "другая причёска", "ПРИЧЕСКА выше"],
)
def test_hair_changes_are_detected(description):
    assert mentions_hair(description) is True


@pytest.mark.parametrize("description", ["белая рубашка", "тёмный фон", "мягкий свет"])
def test_plain_wardrobe_descriptions_are_not_hair(description):
    assert mentions_hair(description) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_look_prompt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.look_prompt'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/services/look_prompt.py`:

```python
"""Сборка промпта образа по рецепту, купленному неудачными попытками.

Правила взяты из `docs/reference-video-avatar-engines.md` и живут здесь, а не
в тексте приглашения: пользователь описывает одежду и место своими словами,
а композицию и позу держит код. Общий план в кадре 512×512 оставляет рту
двадцать пикселей и делает бессмысленным любой рендер — это уже стоило
одного несправедливо забракованного движка.
"""

from __future__ import annotations

# Тянут модель к обобщённому модельному лицу вместо лица пользователя.
BANNED_PHRASES = (
    "editorial fashion photography",
    "editorial fashion",
    "fashion photography",
    "supermodel",
    "beauty retouch",
)

_HAIR_WORDS = (
    "причес",
    "причёс",
    "волос",
    "каре",
    "стрижк",
    "чёлк",
    "челк",
    "hair",
    "haircut",
    "bangs",
    "ponytail",
)

# Композиция, поза и опора на одно лицо — то, что модель обязана сохранить.
_RULES = (
    "Close-up portrait, head and shoulders filling the frame. "
    "Frontal pose, calm expression, the same face as in the reference photo, "
    "eyes to the camera. No furniture, no props, no other people. "
    "Plain natural photograph, not a magazine shoot."
)


def mentions_hair(description: str) -> bool:
    """Просит ли описание тронуть причёску.

    Владелец сознательно разрешила такие описания, но модель на них охотно
    «улучшает» длину и волну и уводит лицо, поэтому экран показывает
    предупреждение — а для этого сначала надо распознать сам случай.
    """
    lowered = description.lower()
    return any(word in lowered for word in _HAIR_WORDS)


def build_look_prompt(description: str) -> str:
    cleaned = description.strip()
    lowered = cleaned.lower()
    for phrase in BANNED_PHRASES:
        while phrase in lowered:
            start = lowered.index(phrase)
            cleaned = cleaned[:start] + cleaned[start + len(phrase) :]
            lowered = cleaned.lower()

    # Пустое описание — это «оставь как есть, только приведи кадр к портрету»,
    # и правил для такого запроса достаточно.
    cleaned = " ".join(cleaned.replace(" ,", ",").split()).strip(" ,")
    return f"{_RULES} {cleaned}".strip() if cleaned else _RULES
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_look_prompt.py -q`
Expected: PASS, все параметризованные варианты.

- [ ] **Step 5: Commit**

```bash
git add bot/services/look_prompt.py tests/test_services_look_prompt.py
git commit -m "feat: build look prompts from the measured recipe"
```

---

### Task 8: Образ из лица — `edit_image`

**Files:**
- Modify: `bot/services/ai_gateway.py`
- Test: `tests/test_ai_gateway.py`

**Interfaces:**
- Consumes: `_call_with_retries`, `_parse_runware_image_response`, `RUNWARE_PROVIDER` — всё уже есть в файле.
- Produces: `edit_image(reference_bytes: bytes, prompt: str, model: str | None = None, size: str | None = None) -> bytes`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_ai_gateway.py` (рядом с рунверовскими тестами, фикстура `_runware_env` уже есть в файле). В импорты добавить `edit_image`:

```python
@respx.mock
@pytest.mark.asyncio
async def test_edit_image_returns_decoded_bytes(_runware_env):
    raw = b"look-image-bytes"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"imageBase64Data": base64.b64encode(raw).decode()}]},
        )
    )

    assert await edit_image(b"face-photo", "close-up portrait") == raw


@respx.mock
@pytest.mark.asyncio
async def test_edit_image_sends_the_face_as_a_base64_reference(_runware_env):
    """Личное фото уходит только base64 — публичной ссылки не существует."""
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"imageBase64Data": base64.b64encode(b"x").decode()}]}
        )
    )

    await edit_image(b"face-photo", "close-up portrait", model="google:4@1")

    task = json.loads(route.calls.last.request.content)[0]
    assert task["taskType"] == "imageInference"
    assert task["model"] == "google:4@1"
    assert task["positivePrompt"] == "close-up portrait"
    reference = task["referenceImages"][0]
    assert reference.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(reference.split(",", 1)[1]) == b"face-photo"
    assert "http" not in reference


@respx.mock
@pytest.mark.asyncio
async def test_edit_image_reports_a_provider_error_body(_runware_env):
    # Runware кладёт отказ в массив errors и отвечает при этом двумя сотнями.
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "invalidWidth"}]})
    )

    with pytest.raises(AIGatewayInvalidResponseError):
        await edit_image(b"face-photo", "close-up portrait")
```

Убедиться, что `AIGatewayInvalidResponseError`, `base64`, `json`, `httpx` уже импортированы в файле; `AIGatewayInvalidResponseError` при необходимости дописать в импорт из `bot.services.ai_gateway`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ai_gateway.py -q -k edit_image`
Expected: FAIL — `ImportError: cannot import name 'edit_image'`.

- [ ] **Step 3: Write minimal implementation**

В `bot/services/ai_gateway.py` сразу после `generate_image` добавить:

```python
async def edit_image(
    reference_bytes: bytes,
    prompt: str,
    model: str | None = None,
    size: str | None = None,
) -> bytes:
    """Новый образ из фотографии лица.

    Отдельная функция, а не флаг у `generate_image`: там задача рисуется с
    нуля по тексту, здесь опорой служит личная фотография пользователя, и
    провайдер тут всегда Runware — только у него в каталоге есть модель
    правки по референсу (`google:4@1`, 4 ₽ за картинку, замер 2026-08-06).

    Фотография уходит **только base64**. Публичная ссылка на лицо
    пользователя не формируется никогда, даже временная.
    """
    settings = load_settings()
    resolved_model = model or settings.avatar_look_model
    width, height = _runware_dimensions(size or settings.ai_gateway_image_size)
    operation = "edit_image"
    overall_started = time.monotonic()
    reference = "data:image/jpeg;base64," + base64.b64encode(reference_bytes).decode()

    async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
        payload = [
            {
                "taskType": "imageInference",
                "taskUUID": str(uuid.uuid4()),
                "positivePrompt": prompt,
                "referenceImages": [reference],
                "width": width,
                "height": height,
                "model": resolved_model,
                "numberResults": 1,
                "outputType": "base64Data",
            }
        ]
        return await client.post(settings.runware_base_url, json=payload)

    async with httpx.AsyncClient(
        timeout=settings.ai_gateway_timeout_seconds,
        headers={"Authorization": f"Bearer {settings.runware_api_key}"},
    ) as client:
        result = await _call_with_retries(
            request=lambda: _do_request(client),
            operation=operation,
            provider=RUNWARE_PROVIDER,
            model=resolved_model,
            max_retries=settings.ai_gateway_max_retries,
            sleep=_sleep,
        )

    duration_ms = (time.monotonic() - overall_started) * 1000
    return _parse_runware_image_response(
        result.response,
        operation,
        RUNWARE_PROVIDER,
        resolved_model,
        result.retry_count,
        duration_ms,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ai_gateway.py -q`
Expected: PASS, весь файл целиком.

- [ ] **Step 5: Commit**

```bash
git add bot/services/ai_gateway.py tests/test_ai_gateway.py
git commit -m "feat: generate a look from the stored face photo"
```

---

### Task 9: Шлюз говорящего видео

**Files:**
- Create: `bot/services/avatar_gateway.py`
- Test: `tests/test_services_avatar_gateway.py`

**Interfaces:**
- Consumes: `bot.config.load_settings`.
- Produces: `PROVIDER_NAME = "runware"`, `AvatarGatewayError`, `AvatarGatewayUnavailableError`, `AvatarGatewayInvalidResponseError`, `RenderStatus(done: bool, failed: bool, video_bytes: bytes | None, cost_usd: float | None, error: str | None)`, `async start_render(image_bytes: bytes, audio_bytes: bytes) -> str`, `async poll_render(task_uuid: str) -> RenderStatus`.

**Перед первым живым прогоном** сверить тело запроса с рабочим скриптом `/root/avatar_live_test.py` на сервере `159.194.214.72` — им сделаны все замеры 06.08, и он единственный проверенный источник формы запроса. Тесты проверяют форму, которую мы обещали в спеке; живой прогон проверяет, что провайдер её принимает.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_avatar_gateway.py`:

```python
from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from bot.services.avatar_gateway import (
    AvatarGatewayInvalidResponseError,
    AvatarGatewayUnavailableError,
    poll_render,
    start_render,
)

RUNWARE_URL = "https://runware.test/v1"
TASK_UUID = "0f5a5f4c-1a11-4d0e-9b2b-2f0f0f0f0f0f"


@pytest.fixture(autouse=True)
def _runware_env(monkeypatch):
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-test-key")
    monkeypatch.setenv("RUNWARE_BASE_URL", RUNWARE_URL)
    monkeypatch.setenv("AVATAR_MODEL", "klingai:avatar@2.0-standard")


@respx.mock
@pytest.mark.asyncio
async def test_start_render_returns_the_task_uuid():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    assert await start_render(b"image", b"audio") == TASK_UUID


@respx.mock
@pytest.mark.asyncio
async def test_start_render_sends_kling_shaped_inputs_as_base64():
    """`klingai:avatar` ждёт inputs.image и inputs.audio строками, не списками."""
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    await start_render(b"image-bytes", b"audio-bytes")

    task = json.loads(route.calls.last.request.content)[0]
    assert task["taskType"] == "videoInference"
    assert task["model"] == "klingai:avatar@2.0-standard"
    assert task["deliveryMethod"] == "async"
    assert task["includeCost"] is True
    assert task["inputs"]["image"].startswith("data:image/jpeg;base64,")
    assert task["inputs"]["audio"].startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(task["inputs"]["image"].split(",", 1)[1]) == b"image-bytes"
    assert base64.b64decode(task["inputs"]["audio"].split(",", 1)[1]) == b"audio-bytes"


@respx.mock
@pytest.mark.asyncio
async def test_start_render_never_sends_a_public_url():
    # Личное лицо и личный голос не должны существовать по ссылке ни секунды.
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    await start_render(b"image", b"audio")

    body = route.calls.last.request.content.decode()
    assert "http://" not in body
    assert "https://" not in body


@respx.mock
@pytest.mark.asyncio
async def test_pixverse_gets_its_own_top_level_shape(monkeypatch):
    # У PixVerse поля лежат на верхнем уровне, а не в inputs. Это единственная
    # причина, по которой шлюз не может быть тоньше.
    monkeypatch.setenv("AVATAR_MODEL", "pixverse:lipsync@1")
    route = respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    await start_render(b"image", b"audio")

    task = json.loads(route.calls.last.request.content)[0]
    assert "inputs" not in task
    assert task["referenceImages"][0].startswith("data:image/jpeg;base64,")
    assert task["inputAudios"][0].startswith("data:audio/mpeg;base64,")


@respx.mock
@pytest.mark.asyncio
async def test_poll_reports_a_render_still_running():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"data": [{"taskUUID": TASK_UUID, "status": "processing"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is False
    assert status.failed is False
    assert status.video_bytes is None


@respx.mock
@pytest.mark.asyncio
async def test_poll_returns_video_bytes_and_cost_when_ready():
    raw = b"mp4-bytes"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoBase64Data": base64.b64encode(raw).decode(),
                        "cost": 0.2231,
                    }
                ]
            },
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.done is True
    assert status.video_bytes == raw
    assert status.cost_usd == pytest.approx(0.2231)


@respx.mock
@pytest.mark.asyncio
async def test_poll_downloads_the_video_when_only_a_url_comes_back():
    # Runware отдаёт результат то байтами, то ссылкой. Наружу шлюз в обоих
    # случаях отдаёт байты — вызывающий код о разнице знать не должен.
    raw = b"mp4-from-url"
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "taskUUID": TASK_UUID,
                        "status": "success",
                        "videoURL": "https://cdn.runware.test/v.mp4",
                        "cost": 0.2,
                    }
                ]
            },
        )
    )
    respx.get("https://cdn.runware.test/v.mp4").mock(
        return_value=httpx.Response(200, content=raw)
    )

    status = await poll_render(TASK_UUID)

    assert status.video_bytes == raw


@respx.mock
@pytest.mark.asyncio
async def test_poll_reports_a_provider_error_as_failed():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "invalidWidth"}]}
        )
    )

    status = await poll_render(TASK_UUID)

    assert status.failed is True
    assert "invalidWidth" in status.error


@respx.mock
@pytest.mark.asyncio
async def test_start_render_raises_on_a_provider_error():
    respx.post(RUNWARE_URL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "no balance"}]})
    )

    with pytest.raises(AvatarGatewayInvalidResponseError):
        await start_render(b"image", b"audio")


@respx.mock
@pytest.mark.asyncio
async def test_start_render_raises_when_the_provider_is_unreachable():
    respx.post(RUNWARE_URL).mock(side_effect=httpx.ConnectError("no route"))

    with pytest.raises(AvatarGatewayUnavailableError):
        await start_render(b"image", b"audio")


@respx.mock
@pytest.mark.asyncio
async def test_start_render_raises_on_http_error_status():
    respx.post(RUNWARE_URL).mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(AvatarGatewayUnavailableError):
        await start_render(b"image", b"audio")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_avatar_gateway.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.avatar_gateway'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/services/avatar_gateway.py`:

```python
"""Говорящее видео из картинки и звука.

Один интерфейс на все движки: запустить рендер, потом опрашивать. Асинхронно,
потому что рендер занимает минуты (на пяти секундах замерено 213–520 с), и
держать ради него HTTP-соединение нельзя.

Про бота этот модуль не знает ничего: на вход байты, на выход байты. Смена
движка — правка `AVATAR_MODEL` в `.env`; разная форма входа у разных движков
живёт в `_build_inputs` и больше нигде.
"""

from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

PROVIDER_NAME = "runware"

_TIMEOUT_SECONDS = 120.0


class AvatarGatewayError(Exception):
    """Базовый класс всех отказов шлюза говорящего видео."""


class AvatarGatewayUnavailableError(AvatarGatewayError):
    pass


class AvatarGatewayInvalidResponseError(AvatarGatewayError):
    pass


@dataclass(frozen=True)
class RenderStatus:
    done: bool
    failed: bool
    video_bytes: bytes | None
    cost_usd: float | None
    error: str | None


def _data_uri(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode()


def _build_inputs(model: str, image: str, audio: str) -> dict[str, Any]:
    """Форма входа под конкретный движок.

    Получена разбором ошибок валидации 06.08 (docs/reference-video-avatar-
    engines.md). У PixVerse поля лежат на верхнем уровне задачи, у остальных —
    внутри `inputs`, и это единственное, что мешает шлюзу быть тоньше.
    """
    if model.startswith("pixverse:"):
        return {"referenceImages": [image], "inputAudios": [audio]}
    return {"inputs": {"image": image, "audio": audio}}


async def _post(payload: list[dict[str, Any]], operation: str) -> dict[str, Any]:
    settings = load_settings()
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS,
        headers={"Authorization": f"Bearer {settings.runware_api_key}"},
    ) as client:
        try:
            response = await client.post(settings.runware_base_url, json=payload)
        except httpx.HTTPError as exc:
            logger.error(
                "Avatar gateway transport failure: operation=%s error=%s",
                operation,
                exc,
                exc_info=True,
            )
            raise AvatarGatewayUnavailableError(
                "Не удалось связаться с сервисом видео"
            ) from exc

    if response.status_code >= 400:
        logger.error(
            "Avatar gateway call failed: operation=%s provider=%s status=%s",
            operation,
            PROVIDER_NAME,
            response.status_code,
        )
        raise AvatarGatewayUnavailableError(
            f"Сервис видео вернул ошибку {response.status_code}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AvatarGatewayInvalidResponseError(
            "Не удалось разобрать ответ сервиса видео"
        ) from exc

    if not isinstance(body, dict):
        raise AvatarGatewayInvalidResponseError(
            "Ответ сервиса видео не прошёл базовую валидацию"
        )
    return body


def _provider_error(body: dict[str, Any]) -> str | None:
    """Текст отказа, который Runware кладёт в `errors` при HTTP 200."""
    errors = body.get("errors")
    if not errors:
        return None
    first = errors[0]
    return str(first.get("message", first)) if isinstance(first, dict) else str(first)


def _first_task(body: dict[str, Any]) -> dict[str, Any]:
    try:
        task = body["data"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise AvatarGatewayInvalidResponseError(
            "Ответ сервиса видео не содержит задачи"
        ) from exc
    if not isinstance(task, dict):
        raise AvatarGatewayInvalidResponseError(
            "Ответ сервиса видео не прошёл базовую валидацию"
        )
    return task


async def start_render(image_bytes: bytes, audio_bytes: bytes) -> str:
    operation = "start_render"
    settings = load_settings()
    model = settings.avatar_model
    task_uuid = str(uuid.uuid4())

    task: dict[str, Any] = {
        "taskType": "videoInference",
        # Runware требует UUIDv4 и сверяет по нему ответ с запросом; своего
        # он не придумывает и любую другую строку отвергает.
        "taskUUID": task_uuid,
        "model": model,
        # Рендер идёт минутами — синхронного ответа тут не существует.
        "deliveryMethod": "async",
        # Фактическая цена приходит в ответе; по прайсу считать нельзя,
        # у одной модели документация разошлась с фактом в 7,4 раза.
        "includeCost": True,
    }
    task.update(
        _build_inputs(
            model,
            _data_uri(image_bytes, "image/jpeg"),
            _data_uri(audio_bytes, "audio/mpeg"),
        )
    )

    body = await _post([task], operation)
    error = _provider_error(body)
    if error:
        raise AvatarGatewayInvalidResponseError(f"Сервис видео отказал: {error}")

    returned = _first_task(body).get("taskUUID") or task_uuid
    logger.info(
        "Avatar render started: provider=%s model=%s operation=%s",
        PROVIDER_NAME,
        model,
        operation,
    )
    return str(returned)


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise AvatarGatewayUnavailableError(
                "Не удалось скачать готовое видео"
            ) from exc
    if response.status_code >= 400:
        raise AvatarGatewayUnavailableError(
            f"Скачивание видео вернуло ошибку {response.status_code}"
        )
    return response.content


async def poll_render(task_uuid: str) -> RenderStatus:
    operation = "poll_render"
    body = await _post(
        [{"taskType": "getResponse", "taskUUID": task_uuid}], operation
    )

    error = _provider_error(body)
    if error:
        return RenderStatus(
            done=False, failed=True, video_bytes=None, cost_usd=None, error=error
        )

    task = _first_task(body)
    status = str(task.get("status", "")).lower()
    if status in {"error", "failed"}:
        return RenderStatus(
            done=False,
            failed=True,
            video_bytes=None,
            cost_usd=None,
            error=str(task.get("error") or "рендер не удался"),
        )

    encoded = task.get("videoBase64Data")
    url = task.get("videoURL")
    if not encoded and not url:
        return RenderStatus(
            done=False, failed=False, video_bytes=None, cost_usd=None, error=None
        )

    # Наружу — всегда байты. То, что провайдер иногда отвечает ссылкой,
    # а иногда телом, остаётся его личным делом.
    video_bytes = base64.b64decode(encoded) if encoded else await _download(str(url))
    cost = task.get("cost")
    logger.info(
        "Avatar render ready: provider=%s operation=%s", PROVIDER_NAME, operation
    )
    return RenderStatus(
        done=True,
        failed=False,
        video_bytes=video_bytes,
        cost_usd=float(cost) if cost is not None else None,
        error=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_avatar_gateway.py -q`
Expected: PASS, 11 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/services/avatar_gateway.py tests/test_services_avatar_gateway.py
git commit -m "feat: add the talking-video gateway"
```

---

### Task 10: Синтез речи клонированным голосом

**Files:**
- Modify: `bot/services/voice_gateway.py`
- Test: `tests/test_services_voice_gateway.py`

**Interfaces:**
- Consumes: `_client`, `_check_status`, `VoiceGatewayError` — уже есть в файле.
- Produces: `async synthesize(text: str, voice_id: str) -> bytes`, `SYNTHESIS_MODEL = "eleven_multilingual_v2"`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_services_voice_gateway.py` (в импорты добавить `synthesize`):

```python
@respx.mock
@pytest.mark.asyncio
async def test_synthesize_returns_audio_bytes(_elevenlabs_env):
    route = respx.post(f"{ELEVENLABS_URL}/text-to-speech/voice-abc").mock(
        return_value=httpx.Response(200, content=b"mp3-bytes")
    )

    assert await synthesize("Привет, это я", "voice-abc") == b"mp3-bytes"
    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_asks_for_a_multilingual_model(_elevenlabs_env):
    """Русская речь на одноязычной модели звучит как акцент — проверено."""
    route = respx.post(f"{ELEVENLABS_URL}/text-to-speech/voice-abc").mock(
        return_value=httpx.Response(200, content=b"mp3")
    )

    await synthesize("Привет", "voice-abc")

    body = json.loads(route.calls.last.request.content)
    assert body["text"] == "Привет"
    assert body["model_id"] == "eleven_multilingual_v2"


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_raises_on_provider_error(_elevenlabs_env):
    respx.post(f"{ELEVENLABS_URL}/text-to-speech/voice-abc").mock(
        return_value=httpx.Response(402, text="quota")
    )

    with pytest.raises(VoiceGatewayError):
        await synthesize("Привет", "voice-abc")


@respx.mock
@pytest.mark.asyncio
async def test_synthesize_raises_on_empty_audio(_elevenlabs_env):
    # Пустой ответ — это не «тихая озвучка», а отказ: дальше по цепочке он
    # превратился бы в оплаченный рендер немого ролика.
    respx.post(f"{ELEVENLABS_URL}/text-to-speech/voice-abc").mock(
        return_value=httpx.Response(200, content=b"")
    )

    with pytest.raises(VoiceGatewayError):
        await synthesize("Привет", "voice-abc")


@pytest.mark.asyncio
async def test_synthesize_refuses_without_an_api_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")

    with pytest.raises(VoiceGatewayError):
        await synthesize("Привет", "voice-abc")
```

Если в файле ещё нет фикстуры `_elevenlabs_env` и константы `ELEVENLABS_URL`, добавить их в начало файла:

```python
ELEVENLABS_URL = "https://elevenlabs.test/v1"


@pytest.fixture
def _elevenlabs_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test-key")
    monkeypatch.setenv("ELEVENLABS_BASE_URL", ELEVENLABS_URL)
```

Проверить, что `json`, `httpx`, `respx`, `pytest` импортированы.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_voice_gateway.py -q -k synthesize`
Expected: FAIL — `ImportError: cannot import name 'synthesize'`.

- [ ] **Step 3: Write minimal implementation**

В `bot/services/voice_gateway.py` добавить константу рядом с `PROVIDER_NAME`:

```python
# Одноязычные модели читают русский с акцентом. Мультиязычная — единственная,
# на которой клон звучит как оригинал.
SYNTHESIS_MODEL = "eleven_multilingual_v2"
```

И функцию в конец файла:

```python
async def synthesize(text: str, voice_id: str) -> bytes:
    """Озвучка текста готовым клонированным голосом.

    Голос уже создан этапом 1 и живёт у провайдера под своим идентификатором —
    сюда он приходит параметром. Пересоздавать голос ради каждой речи не нужно
    и нельзя: это главное требование сценария.
    """
    operation = "synthesize"
    client = _client()
    async with client:
        try:
            response = await client.post(
                f"/text-to-speech/{voice_id}",
                json={"text": text, "model_id": SYNTHESIS_MODEL},
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

    audio = response.content
    if not audio:
        raise VoiceGatewayInvalidResponseError("Провайдер вернул пустую озвучку")

    logger.info(
        "Voice synthesized: provider=%s operation=%s", PROVIDER_NAME, operation
    )
    return audio
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_voice_gateway.py -q`
Expected: PASS, весь файл.

- [ ] **Step 5: Commit**

```bash
git add bot/services/voice_gateway.py tests/test_services_voice_gateway.py
git commit -m "feat: synthesize speech with the cloned voice"
```

---

### Task 11: ffmpeg — апскейл образа и формат кружка

**Files:**
- Modify: `bot/services/ffmpeg_tools.py`
- Create: `bot/services/video_note.py`
- Test: `tests/test_services_video_note.py`

**Interfaces:**
- Consumes: `bot.services.ffmpeg_tools.run_ffmpeg`, `probe_duration`, `FfmpegError`.
- Produces: `run_ffmpeg(*args: str) -> bytes` (в `ffmpeg_tools`); `VIDEO_NOTE_SIDE = 512`, `MIN_PROVIDER_SIDE = 512`, `async ensure_min_side(src_path: str, out_path: str, min_side: int = MIN_PROVIDER_SIDE) -> str`, `async to_video_note(src_path: str, out_path: str, side: int = VIDEO_NOTE_SIDE) -> str` (в `video_note`).

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_video_note.py`:

```python
from __future__ import annotations

import pytest

from bot.services import video_note


class _FakeProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


@pytest.fixture
def calls(monkeypatch):
    """Перехват запуска ffmpeg: настоящий двоичный файл тестам не нужен."""
    recorded: list[tuple[str, ...]] = []

    async def fake_run(*args, **kwargs):
        recorded.append(args)
        return _FakeProcess()

    monkeypatch.setattr("bot.services.ffmpeg_tools._run", fake_run)
    return recorded


@pytest.mark.asyncio
async def test_ensure_min_side_upscales_a_small_square(calls, monkeypatch):
    # Телеграмный кружок приходит 400×400, а Kling требует сторону 512–2160
    # и отвечает invalidWidth. Апскейл обязателен, а не украшение.
    monkeypatch.setattr(video_note, "_probe_side", _fake_side(400))

    await video_note.ensure_min_side("in.jpg", "out.jpg")

    args = " ".join(calls[-1])
    assert "scale=512:512" in args
    assert "out.jpg" in args


@pytest.mark.asyncio
async def test_ensure_min_side_leaves_a_big_image_alone(calls, monkeypatch):
    # Лишний прогон ffmpeg — это лишняя пересжатая картинка и потеря резкости,
    # на которой держится сходство лица.
    monkeypatch.setattr(video_note, "_probe_side", _fake_side(1024))

    result = await video_note.ensure_min_side("in.jpg", "out.jpg")

    assert result == "in.jpg"
    assert calls == []


@pytest.mark.asyncio
async def test_to_video_note_produces_a_square_h264_aac_stream(calls):
    await video_note.to_video_note("in.mp4", "out.mp4")

    args = " ".join(calls[-1])
    assert "scale=512:512" in args
    assert "libx264" in args
    assert "aac" in args
    assert "+faststart" in args
    assert args.endswith("out.mp4")


@pytest.mark.asyncio
async def test_ffmpeg_failure_surfaces_as_ffmpeg_error(monkeypatch):
    async def failing_run(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"broken input")

    monkeypatch.setattr("bot.services.ffmpeg_tools._run", failing_run)

    from bot.services.ffmpeg_tools import FfmpegError

    with pytest.raises(FfmpegError):
        await video_note.to_video_note("in.mp4", "out.mp4")


def _fake_side(value: int):
    async def _probe(path: str) -> int:
        return value

    return _probe
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_video_note.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.video_note'`.

- [ ] **Step 3: Write minimal implementation**

В `bot/services/ffmpeg_tools.py` сразу после `_execute` добавить публичную обёртку:

```python
async def run_ffmpeg(*args: str) -> bytes:
    """Запуск ffmpeg/ffprobe для соседних модулей.

    `video_note.py` держит свои команды у себя, но запуск процесса, разбор
    кода возврата и логирование одни на всех — дублировать их значит завести
    второе место, где эти ошибки обрабатываются по-своему.
    """
    return await _execute(*args)
```

Создать `bot/services/video_note.py`:

```python
"""Приведение картинки и видео к тому, что принимают провайдер и Telegram.

Два ограничения, оба куплены ошибками (docs/reference-video-avatar-engines.md):
Kling отвечает `invalidWidth` на телеграмных кружках 400×400 и требует сторону
512–2160; Telegram принимает video note только квадратом, H.264 + AAC,
с `+faststart` и не длиннее 60 секунд.
"""

from __future__ import annotations

from bot.services.ffmpeg_tools import FfmpegError, run_ffmpeg

# Практический размер кружка. Больше Telegram всё равно ужмёт, меньше —
# заметно мылит лицо.
VIDEO_NOTE_SIDE = 512

# Нижняя граница провайдера, а не наше пожелание.
MIN_PROVIDER_SIDE = 512


async def _probe_side(path: str) -> int:
    """Меньшая сторона картинки в пикселях."""
    stdout = await run_ffmpeg(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        path,
    )
    raw = stdout.decode(errors="replace").strip()
    try:
        width, height = (int(part) for part in raw.split("x")[:2])
    except ValueError as exc:
        raise FfmpegError(f"ffprobe вернул неразбираемый размер: {raw!r}") from exc
    return min(width, height)


async def ensure_min_side(
    src_path: str, out_path: str, min_side: int = MIN_PROVIDER_SIDE
) -> str:
    """Путь к картинке, у которой обе стороны не меньше `min_side`.

    Если исходник и так крупный, возвращается он сам: лишний прогон ffmpeg —
    это лишнее пересжатие, а сходство лица держится на резкости.
    """
    if await _probe_side(src_path) >= min_side:
        return src_path

    await run_ffmpeg(
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-vf",
        f"scale={min_side}:{min_side}:flags=lanczos",
        out_path,
    )
    return out_path


async def to_video_note(
    src_path: str, out_path: str, side: int = VIDEO_NOTE_SIDE
) -> str:
    await run_ffmpeg(
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-vf",
        f"scale={side}:{side}:force_original_aspect_ratio=increase,crop={side}:{side}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        out_path,
    )
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_video_note.py tests/test_services_ffmpeg_tools.py -q`
Expected: PASS, оба файла.

- [ ] **Step 5: Commit**

```bash
git add bot/services/ffmpeg_tools.py bot/services/video_note.py tests/test_services_video_note.py
git commit -m "feat: fit images and video to the provider and video note limits"
```

---

### Task 12: Цена рендера и образа

**Files:**
- Modify: `bot/services/cost_tracker.py`
- Test: `tests/test_services_cost_tracker.py`

**Interfaces:**
- Consumes: `_USD_RUB`, `_IMAGE_RUB_PER_IMAGE` — уже в файле.
- Produces: `video_cost(model: str, seconds: float) -> float`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_services_cost_tracker.py` (в импорты добавить `image_cost`, `video_cost`):

```python
def test_video_cost_is_linear_in_seconds():
    thirty = video_cost("klingai:avatar@2.0-standard", 30)
    sixty = video_cost("klingai:avatar@2.0-standard", 60)

    assert sixty == pytest.approx(thirty * 2)


def test_video_cost_of_the_chosen_engine_matches_the_measurement():
    # Замер 2026-08-06: $0.0446 за секунду. Тридцать секунд — около 135 ₽
    # по курсу, которым живёт весь отчёт.
    assert video_cost("klingai:avatar@2.0-standard", 30) == pytest.approx(
        0.0446 * 30 * 92.0
    )


def test_unknown_video_model_falls_back_to_the_dearest_measured_rate():
    # Новая модель не должна молча отчитаться как бесплатная — иначе отчёт
    # покажет ноль там, где ушли реальные деньги.
    assert video_cost("some:new@1", 30) > video_cost(
        "klingai:avatar@2.0-standard", 30
    )


def test_look_model_is_priced_from_the_live_measurement():
    assert image_cost("google:4@1") == pytest.approx(4.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_cost_tracker.py -q -k "video_cost or look_model"`
Expected: FAIL — `ImportError: cannot import name 'video_cost'`.

- [ ] **Step 3: Write minimal implementation**

В `bot/services/cost_tracker.py` в словарь `_IMAGE_RUB_PER_IMAGE` добавить строку:

```python
    # runware.ai, Nano Banana — правка образа по фотографии лица. Замер
    # 2026-08-06 живым прогоном: 4 ₽ за картинку.
    "google:4@1": 4.0,
```

И в конец файла:

```python
# ₽ за секунду готового видео. Замерено живыми оплаченными прогонами
# 2026-08-06 (docs/reference-video-avatar-engines.md), а не взято из прайса:
# у klingai:7@1 документация разошлась с фактом в 7,4 раза.
_VIDEO_RUB_PER_SECOND = {
    "pixverse:lipsync@1": 0.0136 * _USD_RUB,
    "prunaai:p-video@avatar": 0.0245 * _USD_RUB,
    "sync:lipsync-2@1": 0.0443 * _USD_RUB,
    "klingai:avatar@2.0-standard": 0.0446 * _USD_RUB,
    "klingai:7@1": 0.0684 * _USD_RUB,
    "klingai:avatar@2.0-pro": 0.0881 * _USD_RUB,
    "heygen:avatar@4": 0.0977 * _USD_RUB,
    "bytedance:5@2": 0.1200 * _USD_RUB,
}
# Незнакомая модель считается по самому дорогому из замеренных движков:
# отчёт должен пугать, а не убаюкивать.
_VIDEO_FALLBACK_RUB_PER_SECOND = 0.1200 * _USD_RUB


def video_cost(model: str, seconds: float) -> float:
    """Оценка стоимости `seconds` секунд готового видео у `model`.

    Это оценка «до факта»: показать цену и проверить лимит. Списывается
    всегда фактическая цена из ответа провайдера, если он её вернул.
    """
    rate = _VIDEO_RUB_PER_SECOND.get(model, _VIDEO_FALLBACK_RUB_PER_SECOND)
    return rate * seconds
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_cost_tracker.py -q`
Expected: PASS, весь файл.

- [ ] **Step 5: Commit**

```bash
git add bot/services/cost_tracker.py tests/test_services_cost_tracker.py
git commit -m "feat: price talking video and look generation"
```

---

### Task 13: Оркестратор задания

**Files:**
- Create: `bot/services/speech_pipeline.py`
- Test: `tests/test_services_speech_pipeline.py`

**Interfaces:**
- Consumes: `bot.storage.speech_jobs` (Task 5), `bot.storage.render_usage` (Task 6), `bot.services.avatar_gateway` (Task 9), `bot.services.ffmpeg_tools.probe_duration`, `bot.services.cost_tracker.video_cost` (Task 12), `bot.storage.costs.record_cost`.
- Produces: `REASON_TOO_LONG = "too_long"`, `REASON_LIMIT = "limit"`, `RenderRefused(reason: str, detail: int)`, `async attach_audio(db_path: str, job_id: int, audio_bytes: bytes) -> float`, `async request_render(db_path: str, job_id: int, image_bytes: bytes, look_id: int) -> None`, `async collect_ready(db_path: str, job: SpeechJob) -> bytes | None`.

Оркестратор не знает про aiogram: картинку и звук ему приносят байтами, готовое видео он отдаёт байтами. Всё, что связано с Telegram, живёт в воркере и хендлерах.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_speech_pipeline.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from bot.services import speech_pipeline
from bot.services.avatar_gateway import RenderStatus
from bot.storage.render_usage import get_month_seconds
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_RENDERING,
    STATUS_VOICED,
    create_job,
    get_job,
    update_job,
)

TELEGRAM_ID = 901


@pytest.fixture(autouse=True)
def _tmp_media(monkeypatch, tmp_path):
    monkeypatch.setenv("TMP_MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("AVATAR_MODEL", "klingai:avatar@2.0-standard")
    monkeypatch.setenv("AVATAR_MAX_SECONDS", "60")
    monkeypatch.setenv("AVATAR_MONTHLY_SECONDS_LIMIT", "300")


@pytest.fixture
def _probe(monkeypatch):
    def _set(seconds: float):
        monkeypatch.setattr(
            speech_pipeline, "probe_duration", AsyncMock(return_value=seconds)
        )

    return _set


@pytest.mark.asyncio
async def test_attach_audio_stores_the_file_and_marks_the_job_voiced(
    db_path, _probe
):
    _probe(28.4)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    duration = await attach(db_path, job_id, b"mp3-bytes")

    job = get_job(db_path, job_id)
    assert duration == pytest.approx(28.4)
    assert job.status == STATUS_VOICED
    assert job.audio_duration_sec == pytest.approx(28.4)
    with open(job.audio_path, "rb") as handle:
        assert handle.read() == b"mp3-bytes"


@pytest.mark.asyncio
async def test_audio_longer_than_the_format_allows_is_refused(db_path, _probe):
    # Video note не бывает длиннее 60 секунд. Отказ до оплаты — ноль расхода.
    _probe(75.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")

    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await attach(db_path, job_id, b"mp3-bytes")

    assert refusal.value.reason == speech_pipeline.REASON_TOO_LONG


@pytest.mark.asyncio
async def test_request_render_starts_the_provider_and_marks_rendering(
    db_path, _probe, monkeypatch
):
    _probe(30.0)
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")

    await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    job = get_job(db_path, job_id)
    assert job.status == STATUS_RENDERING
    assert job.provider_task_id == "task-1"
    assert job.look_id == 7
    start.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_is_refused_before_the_paid_call_when_the_limit_is_out(
    db_path, _probe, monkeypatch
):
    # Проверка лимита обязана стоять ДО обращения к провайдеру: после — это
    # уже оплаченный рендер, который мы просто не покажем.
    _probe(30.0)
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech_pipeline, "start_render", start)
    speech_pipeline.add_usage(db_path, TELEGRAM_ID, 300, 1350.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await attach(db_path, job_id, b"mp3")

    with pytest.raises(speech_pipeline.RenderRefused) as refusal:
        await speech_pipeline.request_render(db_path, job_id, b"image", look_id=7)

    assert refusal.value.reason == speech_pipeline.REASON_LIMIT
    start.assert_not_awaited()


@pytest.mark.asyncio
async def test_collect_ready_returns_none_while_the_render_runs(
    db_path, monkeypatch
):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=False, failed=False, video_bytes=None, cost_usd=None, error=None
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status=STATUS_RENDERING, provider_task_id="task-1")

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None
    assert get_job(db_path, job_id).status == STATUS_RENDERING


@pytest.mark.asyncio
async def test_collect_ready_charges_the_actual_provider_cost(db_path, monkeypatch):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=True,
                failed=False,
                video_bytes=b"mp4",
                cost_usd=0.2231,
                error=None,
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    video = await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert video == b"mp4"
    assert get_month_seconds(db_path, TELEGRAM_ID) == 30
    # 0.2231 доллара по курсу отчёта, а не оценка по прайсу.
    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.2231 * 92.0)


@pytest.mark.asyncio
async def test_collect_ready_falls_back_to_the_estimate_without_a_cost_field(
    db_path, monkeypatch
):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=True, failed=False, video_bytes=b"mp4", cost_usd=None, error=None
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_job(db_path, job_id).cost_rub == pytest.approx(0.0446 * 30 * 92.0)


@pytest.mark.asyncio
async def test_a_failed_render_is_not_charged(db_path, monkeypatch):
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=False,
                failed=True,
                video_bytes=None,
                cost_usd=None,
                error="invalidWidth",
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    assert await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id)) is None

    job = get_job(db_path, job_id)
    assert job.status == STATUS_FAILED
    assert "invalidWidth" in job.error
    assert get_month_seconds(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_polling_a_job_twice_charges_once(db_path, monkeypatch):
    # Воркер опрашивает по кругу; двойное списание за один рендер — это
    # двойные деньги в отчёте и съеденный лимит пользователя.
    monkeypatch.setattr(
        speech_pipeline,
        "poll_render",
        AsyncMock(
            return_value=RenderStatus(
                done=True, failed=False, video_bytes=b"mp4", cost_usd=0.2, error=None
            )
        ),
    )
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
    )

    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))
    await speech_pipeline.collect_ready(db_path, get_job(db_path, job_id))

    assert get_month_seconds(db_path, TELEGRAM_ID) == 30


async def attach(db_path: str, job_id: int, audio: bytes) -> float:
    """Короткая обёртка: имя `attach_audio` длинное, а зовут его в каждом тесте."""
    return await speech_pipeline.attach_audio(db_path, job_id, audio)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_speech_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.speech_pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/services/speech_pipeline.py`:

```python
"""Ведение задания речи от текста до готового видео.

Про aiogram здесь нет ни строчки: картинка и звук приходят байтами, готовое
видео уходит байтами. Всё телеграмное живёт в воркере и хендлерах — благодаря
этому весь денежный путь тестируется без сети и без бота.

Задание живёт в SQLite, а не в состоянии диалога. Причина денежная: рестарт
бота посреди оплаченного рендера — это выброшенные деньги.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME
from bot.services.avatar_gateway import poll_render, start_render
from bot.services.cost_tracker import video_cost
from bot.services.ffmpeg_tools import probe_duration
from bot.storage.costs import record_cost
from bot.storage.render_usage import add_usage, seconds_left
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    STATUS_VOICED,
    SpeechJob,
    update_job,
)

logger = logging.getLogger(LOGGER_NAME)

REASON_TOO_LONG = "too_long"
REASON_LIMIT = "limit"

OPERATION_RENDER = "avatar_render"


class RenderRefused(Exception):
    """Отказ до обращения к провайдеру, то есть с нулевым расходом.

    `detail` — число, которое пользователю надо назвать: предел формата
    в секундах либо остаток месячного лимита.
    """

    def __init__(self, reason: str, detail: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


async def attach_audio(db_path: str, job_id: int, audio_bytes: bytes) -> float:
    """Положить озвучку к заданию и замерить её длительность.

    Порядок именно такой: сначала звук и его фактическая длительность, потом
    всё остальное. Длительность синтеза по числу символов заранее точно не
    предсказывается, а от неё зависят и допустимость, и цена.
    """
    settings = load_settings()
    audio_path = _tmp_path(".mp3")
    pathlib.Path(audio_path).write_bytes(audio_bytes)

    duration = await probe_duration(audio_path)
    if duration > settings.avatar_max_seconds:
        pathlib.Path(audio_path).unlink(missing_ok=True)
        raise RenderRefused(REASON_TOO_LONG, settings.avatar_max_seconds)

    update_job(
        db_path,
        job_id,
        status=STATUS_VOICED,
        audio_path=audio_path,
        audio_duration_sec=duration,
    )
    return duration


async def request_render(
    db_path: str, job_id: int, image_bytes: bytes, look_id: int
) -> None:
    """Запустить платный рендер, проверив лимит до обращения к провайдеру."""
    settings = load_settings()
    from bot.storage.speech_jobs import get_job

    job = get_job(db_path, job_id)
    if job is None or job.audio_path is None or job.audio_duration_sec is None:
        raise RenderRefused(REASON_TOO_LONG, settings.avatar_max_seconds)

    needed = int(round(job.audio_duration_sec))
    left = seconds_left(
        db_path, job.telegram_id, settings.avatar_monthly_seconds_limit
    )
    if needed > left:
        # Единственное место, где отказ обязан случиться раньше вызова:
        # после него секунды уже оплачены, отказывать поздно.
        raise RenderRefused(REASON_LIMIT, left)

    audio_bytes = pathlib.Path(job.audio_path).read_bytes()
    task_uuid = await start_render(image_bytes, audio_bytes)

    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id=task_uuid,
        look_id=look_id,
        error=None,
    )


async def collect_ready(db_path: str, job: SpeechJob) -> bytes | None:
    """Опросить провайдера. Байты — когда готово, None — пока нет или отказ.

    Списание идёт здесь и ровно один раз: статус уходит из `rendering` тем же
    вызовом, а воркер выбирает задания только по этому статусу.
    """
    if job.provider_task_id is None:
        return None

    status = await poll_render(job.provider_task_id)

    if status.failed:
        logger.warning(
            "Avatar render failed",
            extra={"user_id": job.telegram_id, "operation": "speech_pipeline"},
        )
        update_job(db_path, job.id, status=STATUS_FAILED, error=status.error)
        return None

    if not status.done or status.video_bytes is None:
        return None

    settings = load_settings()
    seconds = int(round(job.audio_duration_sec or 0))
    cost_rub = (
        status.cost_usd * settings.usd_rub_rate
        if status.cost_usd is not None
        # Провайдер не вернул фактическую цену — считаем по замерам. Ноль
        # писать нельзя: отчёт показал бы бесплатный рендер.
        else video_cost(settings.avatar_model, seconds)
    )

    add_usage(db_path, job.telegram_id, seconds, cost_rub)
    record_cost(
        db_path,
        job.telegram_id,
        OPERATION_RENDER,
        settings.avatar_model,
        cost_rub,
    )
    update_job(db_path, job.id, status=STATUS_READY, cost_rub=cost_rub)
    return status.video_bytes
```

Заметить: `add_usage` импортируется в модуль, чтобы тест мог позвать его как `speech_pipeline.add_usage`, а `get_job` берётся внутри функции — на уровне модуля он не нужен и создал бы лишнюю связь.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_speech_pipeline.py -q`
Expected: PASS, 9 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/services/speech_pipeline.py tests/test_services_speech_pipeline.py
git commit -m "feat: orchestrate the speech render job and its money"
```

---

### Task 14: Фоновый воркер

**Files:**
- Create: `bot/services/speech_worker.py`
- Test: `tests/test_services_speech_worker.py`

**Interfaces:**
- Consumes: `speech_pipeline.collect_ready` (Task 13), `bot.storage.speech_jobs`, `bot.services.video_note.to_video_note` (Task 11), `bot.locales.loader.get_string`.
- Produces: `async process_rendering_jobs(bot, db_path: str) -> None`, `build_speech_scheduler(bot, db_path: str, interval_seconds: int) -> AsyncIOScheduler`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_services_speech_worker.py`:

```python
from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services import speech_worker
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RENDERING,
    create_job,
    get_job,
    update_job,
)

TELEGRAM_ID = 1001


@pytest.fixture(autouse=True)
def _tmp_media(monkeypatch, tmp_path):
    monkeypatch.setenv("TMP_MEDIA_DIR", str(tmp_path))


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.send_video_note = AsyncMock(
        return_value=MagicMock(video_note=MagicMock(file_id="note-1"))
    )
    bot.send_message = AsyncMock()
    return bot


def _rendering_job(db_path: str, audio_path: str) -> int:
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path,
        job_id,
        status=STATUS_RENDERING,
        provider_task_id="task-1",
        audio_duration_sec=30.0,
        audio_path=audio_path,
    )
    return job_id


@pytest.fixture
def audio_file(tmp_path) -> str:
    path = tmp_path / "voice.mp3"
    path.write_bytes(b"mp3")
    return str(path)


@pytest.mark.asyncio
async def test_ready_render_is_sent_as_a_video_note(
    db_path, monkeypatch, audio_file
):
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    job_id = _rendering_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_awaited_once()
    job = get_job(db_path, job_id)
    assert job.status == STATUS_READY
    assert job.result_file_id == "note-1"


@pytest.mark.asyncio
async def test_a_job_still_rendering_is_left_alone(db_path, monkeypatch, audio_file):
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=None)
    )
    job_id = _rendering_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_not_awaited()
    assert get_job(db_path, job_id).status == STATUS_RENDERING


@pytest.mark.asyncio
async def test_a_failed_job_tells_the_user_and_is_not_sent(
    db_path, monkeypatch, audio_file
):
    async def fail(db_path_arg, job):
        update_job(db_path_arg, job.id, status=STATUS_FAILED, error="провайдер отказал")
        return None

    monkeypatch.setattr(speech_worker, "collect_ready", fail)
    _rendering_job(db_path, audio_file)
    bot = _bot()

    await speech_worker.process_rendering_jobs(bot, db_path)

    bot.send_video_note.assert_not_awaited()
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_temporary_files_are_cleaned_up_after_delivery(
    db_path, monkeypatch, audio_file
):
    # Кэш озвучки и скачанное видео не должны копиться в TMP_MEDIA_DIR:
    # media_cache.py уже отучил нас надеяться, что кто-то приберёт потом.
    monkeypatch.setattr(
        speech_worker, "collect_ready", AsyncMock(return_value=b"mp4")
    )
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    _rendering_job(db_path, audio_file)

    await speech_worker.process_rendering_jobs(_bot(), db_path)

    assert not pathlib.Path(audio_file).exists()


@pytest.mark.asyncio
async def test_one_broken_job_does_not_stop_the_others(
    db_path, monkeypatch, audio_file
):
    # Рестарт подбирает пачку заданий; исключение на первом не должно
    # оставить остальные висеть в rendering навсегда.
    calls: list[int] = []

    async def flaky(db_path_arg, job):
        calls.append(job.id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return b"mp4"

    monkeypatch.setattr(speech_worker, "collect_ready", flaky)
    monkeypatch.setattr(
        speech_worker, "to_video_note", AsyncMock(side_effect=_write_note)
    )
    _rendering_job(db_path, audio_file)
    _rendering_job(db_path, audio_file)

    await speech_worker.process_rendering_jobs(_bot(), db_path)

    assert len(calls) == 2


def test_scheduler_runs_on_the_configured_interval(db_path):
    scheduler = speech_worker.build_speech_scheduler(_bot(), db_path, 20)

    job = scheduler.get_job("speech_render_poll")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 20


async def _write_note(src_path: str, out_path: str, *args, **kwargs) -> str:
    pathlib.Path(out_path).write_bytes(b"note")
    return out_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services_speech_worker.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.services.speech_worker'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/services/speech_worker.py`:

```python
"""Фоновый опрос рендеров и доставка готовых кружков.

Асинхронная задача, стартующая вместе с ботом. На каждом тике берёт все
задания в статусе `rendering` — в том числе оставшиеся от прошлого запуска.
Это и есть страховка от рестарта: рендер уже оплачен, и потерять его нельзя.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import load_settings
from bot.locales.loader import DEFAULT_LANGUAGE, get_string
from bot.logging_config import LOGGER_NAME
from bot.services.speech_pipeline import collect_ready
from bot.services.video_note import to_video_note
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_RENDERING,
    get_job,
    get_jobs_by_status,
    update_job,
)
from bot.storage.users import get_interface_language

logger = logging.getLogger(LOGGER_NAME)

JOB_ID = "speech_render_poll"


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


def _language(db_path: str, telegram_id: int) -> str:
    return get_interface_language(db_path, telegram_id) or DEFAULT_LANGUAGE


async def _deliver(bot: Bot, db_path: str, job_id: int, video_bytes: bytes) -> None:
    raw_path = _tmp_path(".mp4")
    note_path = _tmp_path(".mp4")
    job = get_job(db_path, job_id)
    language = _language(db_path, job.telegram_id)
    try:
        pathlib.Path(raw_path).write_bytes(video_bytes)
        await to_video_note(raw_path, note_path)
        message = await bot.send_video_note(
            job.telegram_id, FSInputFile(note_path)
        )
        # file_id кэшируется: публикация в канал дальше бесплатна и мгновенна.
        update_job(db_path, job_id, result_file_id=message.video_note.file_id)
        await bot.send_message(job.telegram_id, get_string("speech_ready", language))
    finally:
        for path in (raw_path, note_path, job.audio_path):
            if path:
                pathlib.Path(path).unlink(missing_ok=True)


async def process_rendering_jobs(bot: Bot, db_path: str) -> None:
    for job in get_jobs_by_status(db_path, STATUS_RENDERING):
        try:
            video_bytes = await collect_ready(db_path, job)
        except Exception:
            # Один сломавшийся рендер не должен оставить соседние задания
            # висеть в rendering до следующего тика — и тем более навсегда.
            logger.warning(
                "Speech job polling failed",
                extra={"user_id": job.telegram_id, "operation": "speech_worker"},
                exc_info=True,
            )
            continue

        refreshed = get_job(db_path, job.id)
        if refreshed is not None and refreshed.status == STATUS_FAILED:
            await bot.send_message(
                job.telegram_id,
                get_string("speech_failed", _language(db_path, job.telegram_id)),
            )
            continue

        if video_bytes is None:
            continue

        try:
            await _deliver(bot, db_path, job.id, video_bytes)
        except Exception:
            logger.error(
                "Speech job delivery failed",
                extra={"user_id": job.telegram_id, "operation": "speech_worker"},
                exc_info=True,
            )
            update_job(
                db_path, job.id, status=STATUS_FAILED, error="доставка не удалась"
            )
            await bot.send_message(
                job.telegram_id,
                get_string("speech_failed", _language(db_path, job.telegram_id)),
            )


def build_speech_scheduler(
    bot: Bot, db_path: str, interval_seconds: int
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        process_rendering_jobs,
        trigger=IntervalTrigger(seconds=interval_seconds),
        args=[bot, db_path],
        id=JOB_ID,
        # Рендер идёт минутами: пропущенный тик наверстывается следующим,
        # и накапливать очередь одинаковых запусков незачем.
        coalesce=True,
        max_instances=1,
        misfire_grace_time=interval_seconds * 3,
    )
    return scheduler
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services_speech_worker.py -q`
Expected: PASS, 6 тестов.

**Порядок:** воркер зовёт `get_string("speech_ready")` и `get_string("speech_failed")`, а эти ключи заводит Task 16. Если эта задача выполняется раньше, тесты упадут с `KeyError` на отсутствующем ключе — тогда сделать сначала Task 16 и вернуться сюда.

- [ ] **Step 5: Commit**

```bash
git add bot/services/speech_worker.py tests/test_services_speech_worker.py
git commit -m "feat: poll renders in the background and deliver the circle"
```

---

### Task 15: Устный сценарий

**Files:**
- Modify: `bot/services/content_generator.py`
- Test: `tests/test_content_generator.py`

**Interfaces:**
- Consumes: `generate_text` из `bot.services.ai_gateway`, `bot.storage.style_examples.get_style_examples` с `kind=KIND_SPOKEN`.
- Produces: `async generate_spoken_script(source_text: str, target_seconds: int, spoken_examples: list[str]) -> str`, `SPOKEN_WORDS_PER_SECOND = 2.3`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_content_generator.py` (в импорты добавить `generate_spoken_script`):

```python
@pytest.mark.asyncio
async def test_spoken_script_asks_for_the_measured_word_budget(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_generate_text(prompt: str, **kwargs) -> str:
        captured["prompt"] = prompt
        return "Привет, коротко о главном."

    monkeypatch.setattr(content_generator, "generate_text", fake_generate_text)

    await content_generator.generate_spoken_script(
        "запуск нового курса", target_seconds=30, spoken_examples=[]
    )

    # 30 секунд разговорной речи — около 69 слов. Без бюджета модель пишет
    # текст на две минуты, и озвучка не влезает в формат.
    assert "69" in captured["prompt"]


@pytest.mark.asyncio
async def test_spoken_script_leans_on_the_users_own_speech(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_generate_text(prompt: str, **kwargs) -> str:
        captured["prompt"] = prompt
        return "текст"

    monkeypatch.setattr(content_generator, "generate_text", fake_generate_text)

    await content_generator.generate_spoken_script(
        "запуск",
        target_seconds=30,
        spoken_examples=["Ну смотрите, я вам сейчас расскажу"],
    )

    assert "Ну смотрите, я вам сейчас расскажу" in captured["prompt"]


@pytest.mark.asyncio
async def test_spoken_script_forbids_hashtags_and_markup(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_generate_text(prompt: str, **kwargs) -> str:
        captured["prompt"] = prompt
        return "текст"

    monkeypatch.setattr(content_generator, "generate_text", fake_generate_text)

    await content_generator.generate_spoken_script(
        "запуск", target_seconds=30, spoken_examples=[]
    )

    lowered = captured["prompt"].lower()
    assert "хэштег" in lowered or "hashtag" in lowered
    assert "разметк" in lowered or "markup" in lowered


@pytest.mark.asyncio
async def test_spoken_script_returns_the_model_text_trimmed(monkeypatch):
    async def fake_generate_text(prompt: str, **kwargs) -> str:
        return "  Готовый сценарий.  \n"

    monkeypatch.setattr(content_generator, "generate_text", fake_generate_text)

    result = await content_generator.generate_spoken_script(
        "запуск", target_seconds=30, spoken_examples=[]
    )

    assert result == "Готовый сценарий."
```

Проверить, что модуль импортирован как `from bot.services import content_generator`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_content_generator.py -q -k spoken`
Expected: FAIL — `AttributeError: module 'bot.services.content_generator' has no attribute 'generate_spoken_script'`.

- [ ] **Step 3: Write minimal implementation**

В конец `bot/services/content_generator.py` добавить:

```python
# Разговорный темп русской речи — около 140 слов в минуту. Считать бюджет
# в словах, а не в символах: длительность озвучки зависит от слов.
SPOKEN_WORDS_PER_SECOND = 2.3

_SPOKEN_PROMPT = (
    "Перепиши материал как текст для устного выступления на камеру.\n\n"
    "Требования:\n"
    "- ровно столько, сколько произносится за {seconds} секунд, "
    "это примерно {words} слов;\n"
    "- живая устная речь: короткие фразы, обращение к зрителю на «ты»;\n"
    "- без хэштегов, без эмодзи, без разметки, без заголовка и без "
    "пояснений — только то, что будет произнесено вслух;\n"
    "- начни сразу с сути, без «здравствуйте, сегодня мы поговорим».\n\n"
    "Материал:\n{source}\n"
)

_SPOKEN_STYLE_BLOCK = (
    "\nВот как этот человек говорит на самом деле — держись этой манеры:\n{examples}\n"
)


async def generate_spoken_script(
    source_text: str, target_seconds: int, spoken_examples: list[str]
) -> str:
    """Текст выступления из материала пользователя.

    Опирается на расшифровки его же кружков (`style_examples.kind='spoken'`),
    собранные этапом 1: письменный стиль постов для речи не годится — вслух
    он звучит как зачитанная статья.
    """
    words = int(round(target_seconds * SPOKEN_WORDS_PER_SECOND))
    prompt = _SPOKEN_PROMPT.format(
        seconds=target_seconds, words=words, source=source_text
    )
    if spoken_examples:
        prompt += _SPOKEN_STYLE_BLOCK.format(examples="\n---\n".join(spoken_examples))

    return (await generate_text(prompt)).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_content_generator.py -q`
Expected: PASS, весь файл.

- [ ] **Step 5: Commit**

```bash
git add bot/services/content_generator.py tests/test_content_generator.py
git commit -m "feat: turn a written text into a spoken script"
```

---

### Task 16: Строки интерфейса на четырёх языках

**Files:**
- Modify: `bot/locales/ru.py`, `bot/locales/en.py`, `bot/locales/vi.py`, `bot/locales/zh.py`
- Test: `tests/test_localization.py`

**Interfaces:**
- Consumes: ничего.
- Produces: 53 новых ключа в каждом из четырёх словарей `STRINGS`.

`tests/test_localization.py::test_all_locales_have_identical_keys` уже требует одинаковый набор ключей во всех четырёх файлах — забыть язык не получится, тест упадёт.

Переиспользуются готовые ключи, новых для них не заводить: `publish_to_channel_button`, `publish_success`, `publish_failed`, `error_not_whitelisted`.

- [ ] **Step 1: Write the failing test**

Дописать в конец `tests/test_localization.py`:

```python
_TALKING_DOUBLE_KEYS = (
    "double_status_full",
    "double_face_present",
    "double_face_missing",
    "double_look_none",
    "double_speak_button",
    "double_looks_button",
    "double_face_button",
    "double_voice_button",
    "face_invite",
    "face_saved",
    "face_expected_photo",
    "looks_title",
    "looks_add_photo_button",
    "looks_add_prompt_button",
    "looks_upload_invite",
    "looks_prompt_invite",
    "looks_hair_warning",
    "looks_need_face",
    "looks_building",
    "looks_failed",
    "looks_saved",
    "looks_activated",
    "look_activate_button",
    "look_delete_button",
    "look_deleted",
    "speech_invite",
    "speech_text_received",
    "speech_voice_as_is_button",
    "speech_script_button",
    "speech_rewrite_button",
    "speech_cancel_button",
    "speech_cancelled",
    "speech_script_failed",
    "speech_prompter",
    "speech_voice_failed",
    "speech_voiced",
    "speech_render_button",
    "speech_revoice_button",
    "speech_back_to_text_button",
    "speech_too_long",
    "speech_look_screen",
    "speech_render_with_look_button",
    "speech_other_look_button",
    "speech_rendering",
    "speech_ready",
    "speech_rewrite_text_button",
    "speech_drop_button",
    "speech_failed",
    "speech_retry_button",
    "speech_limit_exceeded",
    "speech_need_face",
    "speech_need_look",
    "speech_expected_input",
)


@pytest.mark.parametrize("key", _TALKING_DOUBLE_KEYS)
@pytest.mark.parametrize("lang", ["ru", "en", "vi", "zh"])
def test_talking_double_strings_exist_in_every_language(key, lang):
    assert _LOCALE_MODULES[lang].STRINGS.get(key, "").strip()


def test_placeholder_keys_accept_their_arguments():
    # Опечатка в имени подстановки видна только в момент показа экрана —
    # то есть у пользователя. Проверяем здесь.
    assert get_string(
        "double_status_full", "ru", face="есть", looks=3, active="студия"
    )
    assert get_string("looks_title", "ru", count=3, active="студия")
    assert get_string("speech_text_received", "ru", text="привет")
    assert get_string("speech_voiced", "ru", seconds=28)
    assert get_string("speech_too_long", "ru", limit=60)
    assert get_string("speech_limit_exceeded", "ru", left=0)
    assert get_string("speech_look_screen", "ru", title="студия")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_localization.py -q`
Expected: FAIL — 212 параметризованных проверок падают, ключей нет.

- [ ] **Step 3: Write minimal implementation**

В `bot/locales/ru.py` перед закрывающей скобкой словаря `STRINGS` добавить:

```python
    "double_status_full": (
        "Твой двойник: лицо — {face}, образов — {looks}, активный — {active}."
    ),
    "double_face_present": "загружено",
    "double_face_missing": "не загружено",
    "double_look_none": "нет",
    "double_speak_button": "🎤 Сказать речь",
    "double_looks_button": "🖼 Образы",
    "double_face_button": "📸 Заменить лицо",
    "double_voice_button": "🎙 Голос",
    "face_invite": (
        "Пришли одну резкую фотографию лица анфас: голова и плечи во весь кадр, "
        "спокойное выражение, взгляд в камеру.\n\n"
        "Это лицо станет опорой для всех образов, поэтому чем оно резче, "
        "тем больше сходства будет в кружках."
    ),
    "face_saved": "Лицо сохранено. Теперь можно собирать образы.",
    "face_expected_photo": "Жду фотографию — пришли её картинкой, не файлом.",
    "looks_title": "Образов: {count}. Активный — {active}.",
    "looks_add_photo_button": "Прислать картинку",
    "looks_add_prompt_button": "Описать словами",
    "looks_upload_invite": (
        "Пришли картинку образа.\n\n"
        "Важно: крупный план — голова и плечи во весь кадр. На общем плане "
        "лицо занимает пятую часть кадра, и кружок получится смазанным."
    ),
    "looks_prompt_invite": (
        "Опиши одежду, место и свет — например: «белая рубашка, тёмный фон, "
        "мягкий свет сбоку».\n\n"
        "Сделаю образ из твоего лица за 4 ₽ и покажу до того, как снимать кружок."
    ),
    "looks_hair_warning": (
        "Учти: когда просишь изменить причёску, модель охотно меняет и лицо. "
        "Сделаю, но посмотри на результат внимательно."
    ),
    "looks_need_face": "Сначала пришли фотографию лица — образ строится из неё.",
    "looks_building": "Собираю образ, это меньше минуты…",
    "looks_failed": (
        "Не получилось собрать образ. Попробуй ещё раз или пришли готовую картинку."
    ),
    "looks_saved": "Образ сохранён.",
    "looks_activated": "Активный образ изменён.",
    "look_activate_button": "Сделать активным",
    "look_delete_button": "Удалить образ",
    "look_deleted": "Образ удалён.",
    "speech_invite": (
        "Напиши текст выступления или наговори его голосовым.\n\n"
        "Голосовое пойдёт в кружок как есть — твоим настоящим голосом."
    ),
    "speech_text_received": "Принял текст:\n\n{text}",
    "speech_voice_as_is_button": "Озвучить как есть",
    "speech_script_button": "Сделай сценарий",
    "speech_rewrite_button": "Переписать",
    "speech_cancel_button": "Отмена",
    "speech_cancelled": "Отменил. Ничего не потрачено.",
    "speech_script_failed": "Не смог собрать сценарий. Текст твой сохранён.",
    "speech_prompter": (
        "Синтез голоса пока выключен, поэтому вот суфлёр — наговори этот текст "
        "голосовым, и я сниму кружок:\n\n{text}"
    ),
    "speech_voice_failed": (
        "Не получилось озвучить. Текст сохранён — попробуй ещё раз или "
        "наговори голосовым."
    ),
    "speech_voiced": "Вот озвучка, {seconds} секунд. Послушай перед съёмкой.",
    "speech_render_button": "Снять кружок",
    "speech_revoice_button": "Перезаписать",
    "speech_back_to_text_button": "Назад к тексту",
    "speech_too_long": (
        "Это длиннее {limit} секунд, а кружок длиннее не бывает. Сократи речь."
    ),
    "speech_look_screen": "Сниму с этим образом: {title}",
    "speech_render_with_look_button": "Снять с этим образом",
    "speech_other_look_button": "Другой образ",
    "speech_rendering": (
        "Снимаю. Это займёт несколько минут — пришлю, когда будет готово, "
        "ждать в чате не нужно."
    ),
    "speech_ready": "Кружок готов. Посмотри и реши, публиковать ли.",
    "speech_rewrite_text_button": "Переписать текст",
    "speech_drop_button": "Удалить",
    "speech_failed": (
        "Съёмка не удалась. Текст и озвучка сохранены — повтор будет стоить "
        "только саму съёмку."
    ),
    "speech_retry_button": "Повторить",
    "speech_limit_exceeded": (
        "На этот месяц секунды съёмки закончились: осталось {left}. "
        "Лимит обнулится первого числа."
    ),
    "speech_need_face": "Сначала загрузи лицо двойника — без него снимать нечего.",
    "speech_need_look": "Сначала добавь хотя бы один образ.",
    "speech_expected_input": "Жду текст или голосовое сообщение.",
```

В `bot/locales/en.py`:

```python
    "double_status_full": (
        "Your double: face — {face}, looks — {looks}, active — {active}."
    ),
    "double_face_present": "uploaded",
    "double_face_missing": "not uploaded",
    "double_look_none": "none",
    "double_speak_button": "🎤 Give a speech",
    "double_looks_button": "🖼 Looks",
    "double_face_button": "📸 Replace face",
    "double_voice_button": "🎙 Voice",
    "face_invite": (
        "Send one sharp frontal photo of your face: head and shoulders filling "
        "the frame, calm expression, eyes to the camera.\n\n"
        "Every look is built from this face, so the sharper it is, the more "
        "the circles will look like you."
    ),
    "face_saved": "Face saved. Now you can build looks.",
    "face_expected_photo": "I need a photo — send it as a picture, not a file.",
    "looks_title": "Looks: {count}. Active — {active}.",
    "looks_add_photo_button": "Send a picture",
    "looks_add_prompt_button": "Describe it",
    "looks_upload_invite": (
        "Send the look as a picture.\n\n"
        "It matters: close-up, head and shoulders filling the frame. In a wide "
        "shot the face takes a fifth of the frame and the circle comes out blurry."
    ),
    "looks_prompt_invite": (
        "Describe the clothes, the place and the light — for example: «white "
        "shirt, dark background, soft side light».\n\n"
        "I'll build the look from your face for 4 ₽ and show it before any filming."
    ),
    "looks_hair_warning": (
        "A warning: when you ask to change the hair, the model happily changes "
        "the face too. I'll do it, but look at the result closely."
    ),
    "looks_need_face": "Send a photo of your face first — the look is built from it.",
    "looks_building": "Building the look, under a minute…",
    "looks_failed": "Couldn't build the look. Try again or send a ready picture.",
    "looks_saved": "Look saved.",
    "looks_activated": "Active look changed.",
    "look_activate_button": "Make active",
    "look_delete_button": "Delete look",
    "look_deleted": "Look deleted.",
    "speech_invite": (
        "Write the text of your speech or record it as a voice message.\n\n"
        "A voice message goes into the circle as is — in your real voice."
    ),
    "speech_text_received": "Got the text:\n\n{text}",
    "speech_voice_as_is_button": "Voice it as is",
    "speech_script_button": "Make it a script",
    "speech_rewrite_button": "Rewrite",
    "speech_cancel_button": "Cancel",
    "speech_cancelled": "Cancelled. Nothing was spent.",
    "speech_script_failed": "Couldn't write the script. Your text is saved.",
    "speech_prompter": (
        "Voice synthesis is off for now, so here's a prompter — read this out "
        "as a voice message and I'll film the circle:\n\n{text}"
    ),
    "speech_voice_failed": (
        "Couldn't voice it. The text is saved — try again or record a voice message."
    ),
    "speech_voiced": "Here's the audio, {seconds} seconds. Listen before filming.",
    "speech_render_button": "Film the circle",
    "speech_revoice_button": "Record again",
    "speech_back_to_text_button": "Back to the text",
    "speech_too_long": (
        "That's longer than {limit} seconds, and a circle can't be. Shorten the speech."
    ),
    "speech_look_screen": "I'll film with this look: {title}",
    "speech_render_with_look_button": "Film with this look",
    "speech_other_look_button": "Another look",
    "speech_rendering": (
        "Filming. It takes a few minutes — I'll send it when it's ready, "
        "no need to wait in the chat."
    ),
    "speech_ready": "The circle is ready. Take a look and decide about publishing.",
    "speech_rewrite_text_button": "Rewrite the text",
    "speech_drop_button": "Delete",
    "speech_failed": (
        "Filming failed. The text and the audio are saved — a retry costs "
        "only the filming."
    ),
    "speech_retry_button": "Retry",
    "speech_limit_exceeded": (
        "You're out of filming seconds this month: {left} left. "
        "The limit resets on the first."
    ),
    "speech_need_face": "Upload the double's face first — there's nothing to film without it.",
    "speech_need_look": "Add at least one look first.",
    "speech_expected_input": "I'm waiting for text or a voice message.",
```

В `bot/locales/vi.py`:

```python
    "double_status_full": (
        "Bản sao của bạn: khuôn mặt — {face}, tạo hình — {looks}, đang dùng — {active}."
    ),
    "double_face_present": "đã tải lên",
    "double_face_missing": "chưa tải lên",
    "double_look_none": "chưa có",
    "double_speak_button": "🎤 Nói một bài",
    "double_looks_button": "🖼 Tạo hình",
    "double_face_button": "📸 Đổi khuôn mặt",
    "double_voice_button": "🎙 Giọng nói",
    "face_invite": (
        "Gửi một ảnh chân dung rõ nét, chính diện: đầu và vai chiếm trọn khung "
        "hình, biểu cảm bình thản, nhìn thẳng vào máy ảnh.\n\n"
        "Mọi tạo hình đều dựng từ khuôn mặt này, ảnh càng nét thì video tròn "
        "càng giống bạn."
    ),
    "face_saved": "Đã lưu khuôn mặt. Giờ có thể tạo hình.",
    "face_expected_photo": "Tôi cần một bức ảnh — gửi dạng ảnh, không phải tệp.",
    "looks_title": "Tạo hình: {count}. Đang dùng — {active}.",
    "looks_add_photo_button": "Gửi ảnh",
    "looks_add_prompt_button": "Mô tả bằng lời",
    "looks_upload_invite": (
        "Gửi ảnh tạo hình.\n\n"
        "Lưu ý: cận cảnh, đầu và vai chiếm trọn khung hình. Ảnh toàn cảnh khiến "
        "khuôn mặt chỉ chiếm một phần năm và video tròn sẽ bị mờ."
    ),
    "looks_prompt_invite": (
        "Mô tả trang phục, bối cảnh và ánh sáng — ví dụ: «áo sơ mi trắng, nền "
        "tối, ánh sáng dịu từ bên».\n\n"
        "Tôi sẽ dựng tạo hình từ khuôn mặt của bạn với giá 4 ₽ và cho xem trước khi quay."
    ),
    "looks_hair_warning": (
        "Lưu ý: khi bạn yêu cầu đổi kiểu tóc, mô hình cũng đổi luôn khuôn mặt. "
        "Tôi sẽ làm, nhưng hãy xem kỹ kết quả."
    ),
    "looks_need_face": "Hãy gửi ảnh khuôn mặt trước — tạo hình được dựng từ đó.",
    "looks_building": "Đang dựng tạo hình, chưa tới một phút…",
    "looks_failed": "Không dựng được tạo hình. Thử lại hoặc gửi ảnh có sẵn.",
    "looks_saved": "Đã lưu tạo hình.",
    "looks_activated": "Đã đổi tạo hình đang dùng.",
    "look_activate_button": "Chọn dùng",
    "look_delete_button": "Xoá tạo hình",
    "look_deleted": "Đã xoá tạo hình.",
    "speech_invite": (
        "Viết nội dung bài nói hoặc thu bằng tin nhắn thoại.\n\n"
        "Tin nhắn thoại sẽ vào video tròn nguyên bản — bằng giọng thật của bạn."
    ),
    "speech_text_received": "Đã nhận nội dung:\n\n{text}",
    "speech_voice_as_is_button": "Lồng tiếng nguyên văn",
    "speech_script_button": "Viết thành kịch bản",
    "speech_rewrite_button": "Viết lại",
    "speech_cancel_button": "Huỷ",
    "speech_cancelled": "Đã huỷ. Không tốn gì cả.",
    "speech_script_failed": "Không viết được kịch bản. Nội dung của bạn vẫn được giữ.",
    "speech_prompter": (
        "Tổng hợp giọng nói đang tắt, nên đây là bản nhắc thoại — hãy đọc nội "
        "dung này bằng tin nhắn thoại và tôi sẽ quay video tròn:\n\n{text}"
    ),
    "speech_voice_failed": (
        "Không lồng tiếng được. Nội dung vẫn được giữ — thử lại hoặc thu tin nhắn thoại."
    ),
    "speech_voiced": "Đây là bản tiếng, {seconds} giây. Nghe thử trước khi quay.",
    "speech_render_button": "Quay video tròn",
    "speech_revoice_button": "Thu lại",
    "speech_back_to_text_button": "Quay lại nội dung",
    "speech_too_long": (
        "Dài hơn {limit} giây rồi, video tròn không dài hơn được. Hãy rút ngắn bài nói."
    ),
    "speech_look_screen": "Sẽ quay với tạo hình này: {title}",
    "speech_render_with_look_button": "Quay với tạo hình này",
    "speech_other_look_button": "Tạo hình khác",
    "speech_rendering": (
        "Đang quay. Mất vài phút — xong tôi sẽ gửi, bạn không cần chờ trong khung chat."
    ),
    "speech_ready": "Video tròn đã xong. Xem thử rồi quyết định có đăng không.",
    "speech_rewrite_text_button": "Viết lại nội dung",
    "speech_drop_button": "Xoá",
    "speech_failed": (
        "Quay không thành. Nội dung và bản tiếng vẫn được giữ — làm lại chỉ "
        "tốn tiền quay."
    ),
    "speech_retry_button": "Thử lại",
    "speech_limit_exceeded": (
        "Tháng này bạn đã hết số giây quay: còn {left}. Hạn mức đặt lại vào ngày mùng một."
    ),
    "speech_need_face": "Hãy tải khuôn mặt của bản sao lên trước — không có thì không quay được.",
    "speech_need_look": "Hãy thêm ít nhất một tạo hình trước.",
    "speech_expected_input": "Tôi đang chờ nội dung hoặc tin nhắn thoại.",
```

В `bot/locales/zh.py`:

```python
    "double_status_full": "你的分身：面容 — {face}，造型 — {looks}，当前 — {active}。",
    "double_face_present": "已上传",
    "double_face_missing": "未上传",
    "double_look_none": "暂无",
    "double_speak_button": "🎤 发表讲话",
    "double_looks_button": "🖼 造型",
    "double_face_button": "📸 更换面容",
    "double_voice_button": "🎙 声音",
    "face_invite": (
        "发一张清晰的正面面部照片：头肩占满画面，表情平静，目视镜头。\n\n"
        "所有造型都以这张面容为基础，照片越清晰，圆形视频就越像你。"
    ),
    "face_saved": "面容已保存。现在可以做造型了。",
    "face_expected_photo": "我需要一张照片 — 请以图片形式发送，不要用文件。",
    "looks_title": "造型：{count} 个。当前 — {active}。",
    "looks_add_photo_button": "发送图片",
    "looks_add_prompt_button": "用文字描述",
    "looks_upload_invite": (
        "把造型图片发过来。\n\n"
        "要点：特写，头肩占满画面。全景里面部只占五分之一，圆形视频会糊。"
    ),
    "looks_prompt_invite": (
        "描述服装、场景和光线 — 例如「白衬衫，深色背景，侧面柔光」。\n\n"
        "我会用你的面容生成造型，花费 4 ₽，并在拍摄前先给你看。"
    ),
    "looks_hair_warning": (
        "提醒一句：一旦要求改发型，模型往往连面容一起改。我会照做，但请仔细看结果。"
    ),
    "looks_need_face": "请先发面部照片 — 造型是以它为基础生成的。",
    "looks_building": "正在生成造型，不到一分钟…",
    "looks_failed": "造型没能生成。再试一次，或者直接发一张现成图片。",
    "looks_saved": "造型已保存。",
    "looks_activated": "已更换当前造型。",
    "look_activate_button": "设为当前",
    "look_delete_button": "删除造型",
    "look_deleted": "造型已删除。",
    "speech_invite": (
        "写下讲话内容，或者用语音消息说出来。\n\n语音消息会原样进入圆形视频 — 用你真实的声音。"
    ),
    "speech_text_received": "收到内容：\n\n{text}",
    "speech_voice_as_is_button": "按原文配音",
    "speech_script_button": "改写成讲稿",
    "speech_rewrite_button": "重写",
    "speech_cancel_button": "取消",
    "speech_cancelled": "已取消，没有产生任何花费。",
    "speech_script_failed": "讲稿没能生成。你的原文已保留。",
    "speech_prompter": (
        "语音合成目前是关闭的，所以这里给你一份提词稿 — 用语音消息把它念出来，我就去拍圆形视频：\n\n{text}"
    ),
    "speech_voice_failed": "配音失败。原文已保留 — 再试一次，或者录一条语音消息。",
    "speech_voiced": "这是配音，{seconds} 秒。拍摄前先听一下。",
    "speech_render_button": "拍圆形视频",
    "speech_revoice_button": "重新录制",
    "speech_back_to_text_button": "回到文本",
    "speech_too_long": "这超过了 {limit} 秒，圆形视频不能更长。请把讲话缩短。",
    "speech_look_screen": "将用这个造型拍摄：{title}",
    "speech_render_with_look_button": "用这个造型拍",
    "speech_other_look_button": "换个造型",
    "speech_rendering": "正在拍摄。需要几分钟 — 好了我会发给你，不用在聊天里等。",
    "speech_ready": "圆形视频拍好了。看一下，再决定要不要发布。",
    "speech_rewrite_text_button": "重写文本",
    "speech_drop_button": "删除",
    "speech_failed": "拍摄失败。文本和配音都已保留 — 重试只需再付拍摄的钱。",
    "speech_retry_button": "重试",
    "speech_limit_exceeded": "本月的拍摄秒数用完了：还剩 {left} 秒。额度每月一号重置。",
    "speech_need_face": "请先上传分身的面容 — 没有它就没法拍。",
    "speech_need_look": "请先添加至少一个造型。",
    "speech_expected_input": "我在等文本或语音消息。",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_localization.py -q`
Expected: PASS, включая `test_all_locales_have_identical_keys`.

- [ ] **Step 5: Commit**

```bash
git add bot/locales/ tests/test_localization.py
git commit -m "feat: add the talking-double interface strings in four languages"
```

---

### Task 17: Клавиатуры и экран двойника

**Files:**
- Modify: `bot/keyboards/circle.py`, `bot/handlers/circle.py`
- Test: `tests/test_keyboards_circle.py`, `tests/test_handlers_circle_donors.py`

**Interfaces:**
- Consumes: строки из Task 16, `bot.storage.avatar_faces.get_face` (Task 3), `bot.storage.avatar_looks` (Task 4).
- Produces: константы `CALLBACK_SPEAK = "double:speak"`, `CALLBACK_LOOKS = "double:looks"`, `CALLBACK_FACE = "double:face"`, `CALLBACK_VOICE = "double:voice"`, `CALLBACK_LOOK_ADD_PHOTO = "double:look_photo"`, `CALLBACK_LOOK_ADD_PROMPT = "double:look_prompt"`, `CALLBACK_LOOK_ACTIVATE_PREFIX = "double:look_on"`, `CALLBACK_LOOK_DELETE_PREFIX = "double:look_del"`, `CALLBACK_SPEECH_SCRIPT = "speech:script"`, `CALLBACK_SPEECH_VOICE_AS_IS = "speech:as_is"`, `CALLBACK_SPEECH_REWRITE = "speech:rewrite"`, `CALLBACK_SPEECH_CANCEL = "speech:cancel"`, `CALLBACK_SPEECH_RENDER = "speech:render"`, `CALLBACK_SPEECH_REVOICE = "speech:revoice"`, `CALLBACK_SPEECH_BACK_TO_TEXT = "speech:back"`, `CALLBACK_SPEECH_OTHER_LOOK = "speech:other_look"`, `CALLBACK_SPEECH_PUBLISH = "speech:publish"`, `CALLBACK_SPEECH_DROP = "speech:drop"`, `CALLBACK_SPEECH_RETRY = "speech:retry"`; функции `build_my_double_keyboard(lang, has_face, has_look)`, `build_looks_keyboard(lang, looks)`, `build_look_actions_keyboard(lang, look_id, is_active)`, `build_speech_text_keyboard(lang)`, `build_speech_voiced_keyboard(lang)`, `build_speech_look_keyboard(lang, has_other_looks)`, `build_speech_ready_keyboard(lang, can_publish)`, `build_speech_failed_keyboard(lang)`.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_keyboards_circle.py`:

```python
def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_double_screen_offers_speech_looks_face_and_voice():
    markup = build_my_double_keyboard("ru", has_face=True, has_look=True)

    assert CALLBACK_SPEAK in _callbacks(markup)
    assert CALLBACK_LOOKS in _callbacks(markup)
    assert CALLBACK_FACE in _callbacks(markup)
    assert CALLBACK_VOICE in _callbacks(markup)
    assert CALLBACK_DELETE in _callbacks(markup)


def test_speech_button_is_hidden_until_face_and_look_exist():
    # Кнопка, которая ведёт в отказ, честнее не показываться вовсе.
    without_face = build_my_double_keyboard("ru", has_face=False, has_look=True)
    without_look = build_my_double_keyboard("ru", has_face=True, has_look=False)

    assert CALLBACK_SPEAK not in _callbacks(without_face)
    assert CALLBACK_SPEAK not in _callbacks(without_look)


def test_looks_keyboard_lists_every_look_and_marks_the_active_one():
    looks = [
        Look(id=1, file_id="a", title="студия", source=SOURCE_UPLOADED, prompt=None, is_active=True, created_at="now"),
        Look(id=2, file_id="b", title="улица", source=SOURCE_UPLOADED, prompt=None, is_active=False, created_at="now"),
    ]

    markup = build_looks_keyboard("ru", looks)

    labels = _labels(markup)
    assert any(label.startswith("✓") and "студия" in label for label in labels)
    assert any(label == "улица" for label in labels)
    assert f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:2" in _callbacks(markup)


def test_looks_keyboard_always_offers_both_ways_to_add():
    markup = build_looks_keyboard("ru", [])

    assert CALLBACK_LOOK_ADD_PHOTO in _callbacks(markup)
    assert CALLBACK_LOOK_ADD_PROMPT in _callbacks(markup)


def test_look_actions_hide_activate_for_the_active_look():
    markup = build_look_actions_keyboard("ru", look_id=3, is_active=True)

    assert f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:3" not in _callbacks(markup)
    assert f"{CALLBACK_LOOK_DELETE_PREFIX}:3" in _callbacks(markup)


def test_speech_text_screen_offers_voicing_script_and_cancel():
    markup = build_speech_text_keyboard("ru")

    assert CALLBACK_SPEECH_VOICE_AS_IS in _callbacks(markup)
    assert CALLBACK_SPEECH_SCRIPT in _callbacks(markup)
    assert CALLBACK_SPEECH_REWRITE in _callbacks(markup)
    assert CALLBACK_SPEECH_CANCEL in _callbacks(markup)


def test_voiced_screen_offers_filming_revoicing_and_going_back():
    markup = build_speech_voiced_keyboard("ru")

    # Именно TO_LOOK, а не RENDER: с этого экрана деньги ещё не тратятся.
    assert CALLBACK_SPEECH_TO_LOOK in _callbacks(markup)
    assert CALLBACK_SPEECH_RENDER not in _callbacks(markup)
    assert CALLBACK_SPEECH_REVOICE in _callbacks(markup)
    assert CALLBACK_SPEECH_BACK_TO_TEXT in _callbacks(markup)


def test_other_look_button_hidden_when_there_is_only_one_look():
    single = build_speech_look_keyboard("ru", has_other_looks=False)
    several = build_speech_look_keyboard("ru", has_other_looks=True)

    assert CALLBACK_SPEECH_OTHER_LOOK not in _callbacks(single)
    assert CALLBACK_SPEECH_OTHER_LOOK in _callbacks(several)


def test_ready_screen_hides_publishing_without_a_channel():
    # Канал не привязан — кнопка публикации не показывается, а не отказывает.
    without = build_speech_ready_keyboard("ru", can_publish=False)
    with_channel = build_speech_ready_keyboard("ru", can_publish=True)

    assert CALLBACK_SPEECH_PUBLISH not in _callbacks(without)
    assert CALLBACK_SPEECH_PUBLISH in _callbacks(with_channel)
    assert CALLBACK_SPEECH_DROP in _callbacks(without)


def test_failed_screen_offers_a_retry():
    markup = build_speech_failed_keyboard("ru")

    assert CALLBACK_SPEECH_RETRY in _callbacks(markup)
```

В импорты файла добавить всё новое из `bot.keyboards.circle` плюс `from bot.storage.avatar_looks import SOURCE_UPLOADED, Look`.

В `tests/test_handlers_circle_donors.py` дописать:

```python
@pytest.mark.asyncio
async def test_double_screen_reports_face_and_looks(db_path):
    from bot.storage.avatar_faces import save_face
    from bot.storage.avatar_looks import SOURCE_UPLOADED, add_look

    save_face(db_path, TELEGRAM_ID, "photo-1")
    add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    callback = _callback()

    await circle.on_my_double(callback, db_path=db_path, state=_state())

    text = callback.message.answer.await_args.args[0]
    assert "студия" in text
```

Использовать те же помощники `_callback()`/`_state()`, что уже есть в файле; если их нет — скопировать из `tests/test_handlers_circle_voice.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_keyboards_circle.py -q`
Expected: FAIL — `ImportError: cannot import name 'CALLBACK_SPEAK'`.

- [ ] **Step 3: Write minimal implementation**

В `bot/keyboards/circle.py` добавить константы после существующих:

```python
CALLBACK_SPEAK = "double:speak"
CALLBACK_LOOKS = "double:looks"
CALLBACK_FACE = "double:face"
CALLBACK_VOICE = "double:voice"
CALLBACK_LOOK_ADD_PHOTO = "double:look_photo"
CALLBACK_LOOK_ADD_PROMPT = "double:look_prompt"
CALLBACK_LOOK_ACTIVATE_PREFIX = "double:look_on"
CALLBACK_LOOK_DELETE_PREFIX = "double:look_del"

CALLBACK_SPEECH_SCRIPT = "speech:script"
CALLBACK_SPEECH_VOICE_AS_IS = "speech:as_is"
CALLBACK_SPEECH_REWRITE = "speech:rewrite"
CALLBACK_SPEECH_CANCEL = "speech:cancel"
# Две разные кнопки: «Снять кружок» на экране озвучки только показывает образ,
# а платит уже «Снять с этим образом». Один callback на обе означал бы, что
# нажатие на экране ② сразу тратит деньги.
CALLBACK_SPEECH_TO_LOOK = "speech:to_look"
CALLBACK_SPEECH_RENDER = "speech:render"
CALLBACK_SPEECH_REVOICE = "speech:revoice"
CALLBACK_SPEECH_BACK_TO_TEXT = "speech:back"
CALLBACK_SPEECH_OTHER_LOOK = "speech:other_look"
CALLBACK_SPEECH_PUBLISH = "speech:publish"
CALLBACK_SPEECH_DROP = "speech:drop"
CALLBACK_SPEECH_RETRY = "speech:retry"
```

Заменить существующую `build_my_double_keyboard` на:

```python
def _row(text_key: str, lang: str, callback: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=get_string(text_key, lang), callback_data=callback)
    ]


def build_my_double_keyboard(
    lang: str, has_face: bool = False, has_look: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    # Кнопка речи появляется, только когда снимать действительно есть чем.
    # Показать её и отказать — хуже, чем не показывать.
    if has_face and has_look:
        rows.append(_row("double_speak_button", lang, CALLBACK_SPEAK))
    rows.append(_row("double_looks_button", lang, CALLBACK_LOOKS))
    rows.append(_row("double_face_button", lang, CALLBACK_FACE))
    rows.append(_row("double_voice_button", lang, CALLBACK_VOICE))
    rows.append(_row("double_delete_button", lang, CALLBACK_DELETE))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_looks_keyboard(lang: str, looks) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for look in looks:
        # Галочка прямо в подписи: иначе активный образ виден только в тексте
        # над клавиатурой, и пользователь жмёт наугад.
        label = f"✓ {look.title}" if look.is_active else look.title
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:{look.id}",
                )
            ]
        )
    rows.append(_row("looks_add_photo_button", lang, CALLBACK_LOOK_ADD_PHOTO))
    rows.append(_row("looks_add_prompt_button", lang, CALLBACK_LOOK_ADD_PROMPT))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_look_actions_keyboard(
    lang: str, look_id: int, is_active: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not is_active:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("look_activate_button", lang),
                    callback_data=f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:{look_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("look_delete_button", lang),
                callback_data=f"{CALLBACK_LOOK_DELETE_PREFIX}:{look_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_speech_text_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            _row("speech_voice_as_is_button", lang, CALLBACK_SPEECH_VOICE_AS_IS),
            _row("speech_script_button", lang, CALLBACK_SPEECH_SCRIPT),
            _row("speech_rewrite_button", lang, CALLBACK_SPEECH_REWRITE),
            _row("speech_cancel_button", lang, CALLBACK_SPEECH_CANCEL),
        ]
    )


def build_speech_voiced_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            # Ведёт на экран образа, а не в оплату: платит следующий экран.
            _row("speech_render_button", lang, CALLBACK_SPEECH_TO_LOOK),
            _row("speech_revoice_button", lang, CALLBACK_SPEECH_REVOICE),
            _row("speech_back_to_text_button", lang, CALLBACK_SPEECH_BACK_TO_TEXT),
        ]
    )


def build_speech_look_keyboard(lang: str, has_other_looks: bool) -> InlineKeyboardMarkup:
    rows = [_row("speech_render_with_look_button", lang, CALLBACK_SPEECH_RENDER)]
    # Один образ — кнопка «другой» ведёт в тот же самый. Не показываем.
    if has_other_looks:
        rows.append(_row("speech_other_look_button", lang, CALLBACK_SPEECH_OTHER_LOOK))
    rows.append(_row("speech_cancel_button", lang, CALLBACK_SPEECH_CANCEL))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_speech_ready_keyboard(lang: str, can_publish: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_publish:
        rows.append(_row("publish_to_channel_button", lang, CALLBACK_SPEECH_PUBLISH))
    rows.append(_row("speech_other_look_button", lang, CALLBACK_SPEECH_OTHER_LOOK))
    rows.append(_row("speech_rewrite_text_button", lang, CALLBACK_SPEECH_BACK_TO_TEXT))
    rows.append(_row("speech_drop_button", lang, CALLBACK_SPEECH_DROP))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_speech_failed_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[_row("speech_retry_button", lang, CALLBACK_SPEECH_RETRY)]
    )
```

В `bot/handlers/circle.py` заменить тело `on_my_double` на:

```python
@router.callback_query(F.data == CALLBACK_MY_DOUBLE)
async def on_my_double(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    donors = count_donors(db_path, telegram_id)
    profile = get_voice_profile(db_path, telegram_id)
    face = get_face(db_path, telegram_id)
    active_look = get_active_look(db_path, telegram_id)
    looks_count = count_looks(db_path, telegram_id)

    if donors == 0 and profile is None and face is None:
        await callback.message.answer(
            get_string("double_consent_text", language),
            reply_markup=build_consent_keyboard(language),
        )
        await callback.answer()
        return

    await callback.message.answer(
        get_string(
            "double_status_full",
            language,
            face=get_string(
                "double_face_present" if face else "double_face_missing", language
            ),
            looks=looks_count,
            active=active_look.title
            if active_look
            else get_string("double_look_none", language),
        ),
        reply_markup=build_my_double_keyboard(
            language, has_face=face is not None, has_look=active_look is not None
        ),
    )
    await callback.answer()
```

и дописать импорты в этот файл:

```python
from bot.storage.avatar_faces import get_face
from bot.storage.avatar_looks import count_looks, get_active_look
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_keyboards_circle.py tests/test_handlers_circle_donors.py tests/test_handlers_circle_voice.py tests/test_handlers_circle_delete.py -q`
Expected: PASS. Если старый тест ждал прежний текст `double_status_text`, поправить его под новый экран — ключ `double_status_text` больше не используется, но из локалей **не удалять**: его ждёт `test_all_locales_have_identical_keys` в четырёх файлах, а удаление ключа — отдельная уборка, не входящая в эту задачу.

- [ ] **Step 5: Commit**

```bash
git add bot/keyboards/circle.py bot/handlers/circle.py tests/test_keyboards_circle.py tests/test_handlers_circle_donors.py
git commit -m "feat: rebuild the double screen around face, looks and speech"
```

---

### Task 18: Экраны лица и образов

**Files:**
- Create: `bot/handlers/double.py`
- Test: `tests/test_handlers_double.py`

**Interfaces:**
- Consumes: клавиатуры и константы из Task 17, `bot.storage.avatar_faces` (Task 3), `bot.storage.avatar_looks` (Task 4), `bot.services.look_prompt` (Task 7), `bot.services.ai_gateway.edit_image` (Task 8), `bot.services.cost_tracker.image_cost`, `bot.storage.costs.record_cost`.
- Produces: `router` (aiogram Router с именем `double`), `DoubleStates.waiting_face`, `DoubleStates.waiting_look_photo`, `DoubleStates.waiting_look_prompt`, `async show_looks(message, db_path, telegram_id, language) -> None`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_double.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import double
from bot.storage.avatar_faces import get_face, save_face
from bot.storage.avatar_looks import (
    SOURCE_GENERATED,
    SOURCE_UPLOADED,
    add_look,
    get_active_look,
    get_looks,
)
from bot.storage.costs import get_monthly_total
from bot.storage.whitelist import add_user

TELEGRAM_ID = 1101


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    # Платные кнопки закрыты вайтлистом, а он же и есть список подписчиков.
    # Без этой строчки каждый тест ниже проверял бы отказ, а не сценарий.
    add_user(db_path, TELEGRAM_ID)


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _callback(data: str = "") -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.message.answer_photo = AsyncMock()
    callback.message.bot.download = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _photo_message() -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.caption = None
    message.photo = [MagicMock(file_id="photo-small"), MagicMock(file_id="photo-big")]
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock(return_value=_sent_photo())
    message.bot.download = AsyncMock()
    return message


def _text_message(text: str) -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.text = text
    message.photo = None
    message.answer = AsyncMock()
    # Возврат обязан нести настоящую строку: file_id уходит в SQLite, и
    # MagicMock там падает с InterfaceError, а не с понятной ошибкой теста.
    message.answer_photo = AsyncMock(return_value=_sent_photo())
    message.bot.download = AsyncMock()
    return message


def _sent_photo() -> MagicMock:
    return MagicMock(photo=[MagicMock(file_id="look-1")])


@pytest.mark.asyncio
async def test_face_photo_is_stored_at_the_highest_resolution(db_path, state):
    # Telegram присылает лесенку размеров; сходство лица держится на резкости,
    # поэтому берём последний, самый крупный.
    await state.set_state(double.DoubleStates.waiting_face)

    await double.on_face_photo(_photo_message(), db_path=db_path, state=state)

    assert get_face(db_path, TELEGRAM_ID).file_id == "photo-big"
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_non_photo_while_waiting_for_a_face_is_answered_not_swallowed(
    db_path, state
):
    await state.set_state(double.DoubleStates.waiting_face)
    message = _text_message("вот держи")

    await double.on_face_wrong_input(message, db_path=db_path, state=state)

    message.answer.assert_awaited_once()
    assert get_face(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_uploaded_look_is_saved_without_spending_money(db_path, state):
    await state.set_state(double.DoubleStates.waiting_look_photo)

    await double.on_look_photo(_photo_message(), db_path=db_path, state=state)

    looks = get_looks(db_path, TELEGRAM_ID)
    assert len(looks) == 1
    assert looks[0].source == SOURCE_UPLOADED
    assert get_monthly_total(db_path) == 0


@pytest.mark.asyncio
async def test_describing_a_look_without_a_face_refuses_before_paying(
    db_path, state, monkeypatch
):
    edit = AsyncMock(return_value=b"image")
    monkeypatch.setattr(double, "edit_image", edit)
    callback = _callback()

    await double.on_look_add_prompt(callback, db_path=db_path, state=state)

    edit.assert_not_awaited()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_described_look_is_generated_and_charged(db_path, state, monkeypatch):
    save_face(db_path, TELEGRAM_ID, "photo-face")
    monkeypatch.setattr(double, "edit_image", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(double, "_read_bytes", lambda path: b"face-bytes")
    await state.set_state(double.DoubleStates.waiting_look_prompt)

    await double.on_look_prompt(
        _text_message("белая рубашка, тёмный фон"), db_path=db_path, state=state
    )

    looks = get_looks(db_path, TELEGRAM_ID)
    assert looks[0].source == SOURCE_GENERATED
    assert looks[0].prompt == "белая рубашка, тёмный фон"
    # 4 ₽ за образ должны быть видны в /costs.
    assert get_monthly_total(db_path) == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_a_hair_change_is_warned_about_but_still_done(
    db_path, state, monkeypatch
):
    save_face(db_path, TELEGRAM_ID, "photo-face")
    monkeypatch.setattr(double, "edit_image", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(double, "_read_bytes", lambda path: b"face-bytes")
    await state.set_state(double.DoubleStates.waiting_look_prompt)
    message = _text_message("сделай каре")

    await double.on_look_prompt(message, db_path=db_path, state=state)

    warned = [call.args[0] for call in message.answer.await_args_list]
    assert any("причёск" in text.lower() or "модель" in text.lower() for text in warned)
    assert len(get_looks(db_path, TELEGRAM_ID)) == 1


@pytest.mark.asyncio
async def test_failed_generation_does_not_save_a_look(db_path, state, monkeypatch):
    from bot.services.ai_gateway import AIGatewayUnavailableError

    save_face(db_path, TELEGRAM_ID, "photo-face")
    monkeypatch.setattr(
        double, "edit_image", AsyncMock(side_effect=AIGatewayUnavailableError("нет сети"))
    )
    monkeypatch.setattr(double, "_read_bytes", lambda path: b"face-bytes")
    await state.set_state(double.DoubleStates.waiting_look_prompt)

    await double.on_look_prompt(_text_message("студия"), db_path=db_path, state=state)

    assert get_looks(db_path, TELEGRAM_ID) == []


@pytest.mark.asyncio
async def test_picking_a_look_makes_it_active(db_path, state):
    add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    second = add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    await double.on_look_activate(
        _callback(f"double:look_on:{second}"), db_path=db_path, state=state
    )

    assert get_active_look(db_path, TELEGRAM_ID).id == second


@pytest.mark.asyncio
async def test_deleting_a_look_removes_it(db_path, state):
    look_id = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)

    await double.on_look_delete(
        _callback(f"double:look_del:{look_id}"), db_path=db_path, state=state
    )

    assert get_looks(db_path, TELEGRAM_ID) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_double.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.handlers.double'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/handlers/double.py`:

```python
"""Экраны лица и образов двойника.

Отдельно от `circle.py`: тот отвечает за сбор кружков-доноров и голос, и вместе
эти три сценария не помещаются в один читаемый файл.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.handlers.guards import check_whitelist_or_reply
from bot.keyboards.circle import (
    CALLBACK_FACE,
    CALLBACK_LOOK_ACTIVATE_PREFIX,
    CALLBACK_LOOK_ADD_PHOTO,
    CALLBACK_LOOK_ADD_PROMPT,
    CALLBACK_LOOK_DELETE_PREFIX,
    CALLBACK_LOOKS,
    build_look_actions_keyboard,
    build_looks_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import AIGatewayError, edit_image
from bot.services.cost_tracker import image_cost
from bot.services.look_prompt import build_look_prompt, mentions_hair
from bot.storage.avatar_faces import get_face, save_face
from bot.storage.avatar_looks import (
    SOURCE_GENERATED,
    SOURCE_UPLOADED,
    add_look,
    count_looks,
    delete_look,
    get_active_look,
    get_look,
    get_looks,
    set_active_look,
)
from bot.storage.costs import record_cost

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="double")

OPERATION_LOOK = "avatar_look"

# Длинное описание в подписи кнопки не помещается, а короткое — вся навигация
# по образам. Режем по границе, а не по букве.
_TITLE_LIMIT = 40


class DoubleStates(StatesGroup):
    waiting_face = State()
    waiting_look_photo = State()
    waiting_look_prompt = State()


def _read_bytes(path: str) -> bytes:
    # Вынесено функцией, чтобы тесты подменяли чтение диска — тот же приём,
    # что в circle.py.
    return pathlib.Path(path).read_bytes()


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


def _short_title(text: str, fallback: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return fallback
    return cleaned if len(cleaned) <= _TITLE_LIMIT else cleaned[: _TITLE_LIMIT - 1] + "…"


async def _send_looks(message: Message, db_path: str, telegram_id: int, language: str) -> None:
    looks = get_looks(db_path, telegram_id)
    active = get_active_look(db_path, telegram_id)
    await message.answer(
        get_string(
            "looks_title",
            language,
            count=len(looks),
            active=active.title if active else get_string("double_look_none", language),
        ),
        reply_markup=build_looks_keyboard(language, looks),
    )


@router.callback_query(F.data == CALLBACK_FACE)
async def on_face_request(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, callback.from_user.id, callback.from_user.language_code)
    await state.set_state(DoubleStates.waiting_face)
    await callback.message.answer(get_string("face_invite", language))
    await callback.answer()


@router.message(DoubleStates.waiting_face, F.photo)
async def on_face_photo(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    # Последний элемент — самый крупный размер. Сходство лица держится на
    # резкости, брать мелкий превью нельзя.
    save_face(db_path, telegram_id, message.photo[-1].file_id)
    await state.set_state(None)
    await message.answer(get_string("face_saved", language))
    await _send_looks(message, db_path, telegram_id, language)


@router.message(DoubleStates.waiting_face)
async def on_face_wrong_input(message: Message, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, message.from_user.id, message.from_user.language_code)
    await message.answer(get_string("face_expected_photo", language))


@router.callback_query(F.data == CALLBACK_LOOKS)
async def on_looks(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    await state.set_state(None)
    await _send_looks(callback.message, db_path, telegram_id, language)
    await callback.answer()


@router.callback_query(F.data == CALLBACK_LOOK_ADD_PHOTO)
async def on_look_add_photo(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, callback.from_user.id, callback.from_user.language_code)
    await state.set_state(DoubleStates.waiting_look_photo)
    await callback.message.answer(get_string("looks_upload_invite", language))
    await callback.answer()


@router.message(DoubleStates.waiting_look_photo, F.photo)
async def on_look_photo(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    title = _short_title(
        message.caption or "", f"Образ {count_looks(db_path, telegram_id) + 1}"
    )
    add_look(db_path, telegram_id, message.photo[-1].file_id, title, SOURCE_UPLOADED)
    await state.set_state(None)
    await message.answer(get_string("looks_saved", language))
    await _send_looks(message, db_path, telegram_id, language)


@router.message(DoubleStates.waiting_look_photo)
async def on_look_photo_wrong_input(message: Message, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, message.from_user.id, message.from_user.language_code)
    await message.answer(get_string("face_expected_photo", language))


@router.callback_query(F.data == CALLBACK_LOOK_ADD_PROMPT)
async def on_look_add_prompt(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    # WhitelistMiddleware зарегистрирован только на сообщениях (bot/main.py) и
    # для callback_query не срабатывает вовсе. Отсюда уходит платный вызов,
    # поэтому проверка нужна руками — так же, как в остальных хендлерах.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if get_face(db_path, telegram_id) is None:
        # Отказ до денег и до состояния: генерировать образ не из чего.
        await callback.message.answer(get_string("looks_need_face", language))
        await callback.answer()
        return

    await state.set_state(DoubleStates.waiting_look_prompt)
    await callback.message.answer(get_string("looks_prompt_invite", language))
    await callback.answer()


@router.message(DoubleStates.waiting_look_prompt, F.text)
async def on_look_prompt(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)
    description = message.text.strip()

    face = get_face(db_path, telegram_id)
    if face is None:
        await message.answer(get_string("looks_need_face", language))
        await state.set_state(None)
        return

    if mentions_hair(description):
        # Предупреждение, а не запрет: владелец решила эту возможность оставить,
        # но модель на таких просьбах уводит и лицо тоже.
        await message.answer(get_string("looks_hair_warning", language))

    await message.answer(get_string("looks_building", language))

    face_path = _tmp_path(".jpg")
    try:
        await message.bot.download(face.file_id, destination=face_path)
        image_bytes = await edit_image(
            _read_bytes(face_path), build_look_prompt(description)
        )
    except AIGatewayError:
        logger.warning(
            "Look generation failed",
            extra={"user_id": telegram_id, "operation": "handler:double"},
            exc_info=True,
        )
        await message.answer(get_string("looks_failed", language))
        await state.set_state(None)
        return
    finally:
        pathlib.Path(face_path).unlink(missing_ok=True)

    settings = load_settings()
    sent = await message.answer_photo(
        BufferedInputFile(image_bytes, filename="look.jpg")
    )
    add_look(
        db_path,
        telegram_id,
        sent.photo[-1].file_id,
        _short_title(description, f"Образ {count_looks(db_path, telegram_id) + 1}"),
        SOURCE_GENERATED,
        prompt=description,
    )
    record_cost(
        db_path,
        telegram_id,
        OPERATION_LOOK,
        settings.avatar_look_model,
        image_cost(settings.avatar_look_model),
    )

    await state.set_state(None)
    await message.answer(get_string("looks_saved", language))
    await _send_looks(message, db_path, telegram_id, language)


@router.callback_query(F.data.startswith(f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:"))
async def on_look_activate(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    look_id = int(callback.data.rsplit(":", 1)[1])

    set_active_look(db_path, telegram_id, look_id)
    look = get_look(db_path, telegram_id, look_id)
    if look is not None:
        await callback.message.answer_photo(
            look.file_id,
            caption=get_string("looks_activated", language),
            reply_markup=build_look_actions_keyboard(language, look_id, is_active=True),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CALLBACK_LOOK_DELETE_PREFIX}:"))
async def on_look_delete(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    look_id = int(callback.data.rsplit(":", 1)[1])

    delete_look(db_path, telegram_id, look_id)
    await callback.message.answer(get_string("look_deleted", language))
    await _send_looks(callback.message, db_path, telegram_id, language)
    await callback.answer()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handlers_double.py -q`
Expected: PASS, 9 тестов.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/double.py tests/test_handlers_double.py
git commit -m "feat: add the face and looks screens"
```

---

### Task 19: Экраны речи

**Files:**
- Create: `bot/handlers/speech.py`
- Test: `tests/test_handlers_speech.py`

**Interfaces:**
- Consumes: клавиатуры Task 17, `speech_pipeline` (Task 13), `speech_jobs` (Task 5), `voice_gateway.synthesize` (Task 10), `content_generator.generate_spoken_script` (Task 15), `avatar_looks`, `avatar_faces`.
- Produces: `router` (Router с именем `speech`), `SpeechStates.waiting_input`.

- [ ] **Step 1: Write the failing test**

Создать `tests/test_handlers_speech.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import speech
from bot.storage.avatar_faces import save_face
from bot.storage.avatar_looks import SOURCE_UPLOADED, add_look
from bot.storage.render_usage import add_usage
from bot.storage.speech_jobs import (
    STATUS_RENDERING,
    STATUS_VOICED,
    create_job,
    get_active_job,
    get_job,
    update_job,
)
from bot.storage.voice_profiles import save_voice_profile
from bot.storage.whitelist import add_user

TELEGRAM_ID = 1201


@pytest.fixture(autouse=True)
def _avatar_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TMP_MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("AVATAR_MONTHLY_SECONDS_LIMIT", "300")
    monkeypatch.setenv("AVATAR_MAX_SECONDS", "60")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


@pytest.fixture
def ready_double(db_path) -> int:
    save_face(db_path, TELEGRAM_ID, "photo-face")
    return add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)


def _callback(data: str = "") -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.message.answer_voice = AsyncMock()
    callback.message.bot.download = AsyncMock()
    callback.message.bot.send_video_note = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _text_message(text: str) -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.text = text
    message.voice = None
    message.answer = AsyncMock()
    message.answer_voice = AsyncMock()
    message.bot.download = AsyncMock()
    return message


def _voice_message() -> MagicMock:
    message = _text_message("")
    message.text = None
    message.voice = MagicMock(file_id="voice-1", duration=30)
    return message


@pytest.mark.asyncio
async def test_speak_refuses_without_a_face(db_path, state):
    callback = _callback()

    await speech.on_speak(callback, db_path=db_path, state=state)

    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_written_text_creates_a_draft_job(db_path, state, ready_double):
    await state.set_state(speech.SpeechStates.waiting_input)

    await speech.on_text(_text_message("Расскажу про запуск"), db_path=db_path, state=state)

    job = get_active_job(db_path, TELEGRAM_ID)
    assert job is not None
    assert job.source_text == "Расскажу про запуск"


@pytest.mark.asyncio
async def test_voice_message_becomes_the_audio_itself(
    db_path, state, ready_double, monkeypatch
):
    # Голосовое — это готовая озвучка настоящим голосом, а не сырьё для
    # пересинтеза. Это самый дешёвый путь и он работает без ElevenLabs.
    attach = AsyncMock(return_value=30.0)
    monkeypatch.setattr(speech, "attach_audio", attach)
    monkeypatch.setattr(speech, "transcribe", AsyncMock(return_value="расшифровка"))
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"voice-bytes")
    await state.set_state(speech.SpeechStates.waiting_input)

    await speech.on_voice(_voice_message(), db_path=db_path, state=state)

    attach.assert_awaited_once()
    assert get_active_job(db_path, TELEGRAM_ID).source_text == "расшифровка"


@pytest.mark.asyncio
async def test_written_text_without_synthesis_gets_a_prompter_and_costs_nothing(
    db_path, state, ready_double, monkeypatch
):
    synthesize = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(speech, "synthesize", synthesize)
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "0")
    job_id = create_job(db_path, TELEGRAM_ID, "Расскажу про запуск")
    await state.update_data(job_id=job_id)

    await speech.on_voice_as_is(_callback(), db_path=db_path, state=state)

    synthesize.assert_not_awaited()
    assert get_job(db_path, job_id).status == "draft"


@pytest.mark.asyncio
async def test_synthesis_uses_the_existing_cloned_voice(
    db_path, state, ready_double, monkeypatch
):
    # Голос уже создан этапом 1 — новый двойник ради речи не создаётся.
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", "2026-08-01")
    synthesize = AsyncMock(return_value=b"mp3")
    monkeypatch.setattr(speech, "synthesize", synthesize)
    monkeypatch.setattr(speech, "attach_audio", AsyncMock(return_value=28.0))
    monkeypatch.setenv("AVATAR_VOICE_SYNTHESIS_ENABLED", "1")
    job_id = create_job(db_path, TELEGRAM_ID, "Расскажу про запуск")
    await state.update_data(job_id=job_id)

    await speech.on_voice_as_is(_callback(), db_path=db_path, state=state)

    assert synthesize.await_args.args == ("Расскажу про запуск", "voice-abc")


@pytest.mark.asyncio
async def test_script_button_rewrites_the_text_without_touching_the_original(
    db_path, state, ready_double, monkeypatch
):
    monkeypatch.setattr(
        speech, "generate_spoken_script", AsyncMock(return_value="Устный вариант")
    )
    job_id = create_job(db_path, TELEGRAM_ID, "Исходный текст")
    await state.update_data(job_id=job_id)

    await speech.on_script(_callback(), db_path=db_path, state=state)

    job = get_job(db_path, job_id)
    assert job.script == "Устный вариант"
    assert job.source_text == "Исходный текст"


@pytest.mark.asyncio
async def test_render_is_refused_when_the_monthly_limit_is_out(
    db_path, state, ready_double, monkeypatch
):
    start = AsyncMock(return_value="task-1")
    monkeypatch.setattr(speech, "start_render", start)
    add_usage(db_path, TELEGRAM_ID, 300, 1350.0)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_render(callback, db_path=db_path, state=state)

    start.assert_not_awaited()
    assert get_job(db_path, job_id).status == STATUS_VOICED
    assert "секунды" in callback.message.answer.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_render_starts_and_reports_the_wait(
    db_path, state, ready_double, monkeypatch
):
    monkeypatch.setattr(speech, "request_render", AsyncMock())
    monkeypatch.setattr(speech, "_read_bytes", lambda path: b"image-bytes")
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_render(callback, db_path=db_path, state=state)

    speech.request_render.assert_awaited_once()
    callback.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_publishing_reuses_the_cached_file_id(
    db_path, state, ready_double, monkeypatch
):
    # Второй рендер ради публикации — это второй платёж за один и тот же ролик.
    from bot.storage.users import set_channel_id

    set_channel_id(db_path, TELEGRAM_ID, -100500)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(db_path, job_id, status="ready", result_file_id="note-1")
    await state.update_data(job_id=job_id)
    callback = _callback()

    await speech.on_publish(callback, db_path=db_path, state=state)

    callback.message.bot.send_video_note.assert_awaited_once()
    assert callback.message.bot.send_video_note.await_args.args[1] == "note-1"
    assert get_job(db_path, job_id).status == "published"


@pytest.mark.asyncio
async def test_cancel_closes_the_job_with_no_spend(db_path, state, ready_double):
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    await state.update_data(job_id=job_id)

    await speech.on_cancel(_callback(), db_path=db_path, state=state)

    assert get_active_job(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_a_user_outside_the_whitelist_never_reaches_the_paid_call(
    db_path, state, ready_double, monkeypatch
):
    # Подписки в боте нет, её роль играет вайтлист. Для callback_query
    # middleware не срабатывает — если забыть проверку, кружки станут
    # бесплатными для любого, кто нажмёт кнопку.
    from bot.storage.whitelist import remove_user

    remove_user(db_path, TELEGRAM_ID)
    request = AsyncMock()
    monkeypatch.setattr(speech, "request_render", request)
    job_id = create_job(db_path, TELEGRAM_ID, "текст")
    update_job(
        db_path, job_id, status=STATUS_VOICED, audio_path="/tmp/a.mp3", audio_duration_sec=30.0
    )
    await state.update_data(job_id=job_id)

    await speech.on_render(_callback(), db_path=db_path, state=state)

    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_input_while_waiting_is_answered(db_path, state, ready_double):
    await state.set_state(speech.SpeechStates.waiting_input)
    message = _text_message("")
    message.text = None

    await speech.on_wrong_input(message, db_path=db_path, state=state)

    message.answer.assert_awaited_once()
```

Проверить в `bot/storage/users.py` фактическое имя функции для канала (`set_channel_id` или иное) и использовать его.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handlers_speech.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.handlers.speech'`.

- [ ] **Step 3: Write minimal implementation**

Создать `bot/handlers/speech.py`:

```python
"""Экраны речи: текст или голос → озвучка → образ → кружок.

Платит только последний шаг. Между приёмом речи и оплатой человек стоит
дважды — послушать звук и посмотреть образ бесплатно. Это главная
оптимизация расходов: платим не за ролик, а за неоплату брака.
"""

from __future__ import annotations

import logging
import pathlib
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.handlers.guards import check_whitelist_or_reply
from bot.keyboards.circle import (
    CALLBACK_SPEAK,
    CALLBACK_SPEECH_BACK_TO_TEXT,
    CALLBACK_SPEECH_CANCEL,
    CALLBACK_SPEECH_DROP,
    CALLBACK_SPEECH_OTHER_LOOK,
    CALLBACK_SPEECH_PUBLISH,
    CALLBACK_SPEECH_RENDER,
    CALLBACK_SPEECH_RETRY,
    CALLBACK_SPEECH_REVOICE,
    CALLBACK_SPEECH_REWRITE,
    CALLBACK_SPEECH_SCRIPT,
    CALLBACK_SPEECH_TO_LOOK,
    CALLBACK_SPEECH_VOICE_AS_IS,
    build_looks_keyboard,
    build_speech_failed_keyboard,
    build_speech_look_keyboard,
    build_speech_ready_keyboard,
    build_speech_text_keyboard,
    build_speech_voiced_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services.ai_gateway import TranscriptionError, transcribe
from bot.services.avatar_gateway import AvatarGatewayError, start_render
from bot.services.content_generator import generate_spoken_script
from bot.services.speech_pipeline import (
    REASON_LIMIT,
    RenderRefused,
    attach_audio,
    request_render,
)
from bot.services.voice_gateway import VoiceGatewayError, synthesize
from bot.storage.avatar_faces import get_face
from bot.storage.avatar_looks import count_looks, get_active_look, get_looks
from bot.storage.speech_jobs import (
    STATUS_FAILED,
    STATUS_PUBLISHED,
    STATUS_READY,
    create_job,
    get_active_job,
    get_job,
    update_job,
)
from bot.storage.style_examples import KIND_SPOKEN, get_style_examples
from bot.storage.users import get_channel_id
from bot.storage.voice_profiles import get_voice_profile

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="speech")


class SpeechStates(StatesGroup):
    waiting_input = State()


def _read_bytes(path: str) -> bytes:
    return pathlib.Path(path).read_bytes()


def _tmp_path(suffix: str) -> str:
    directory = pathlib.Path(load_settings().tmp_media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / f"{uuid.uuid4().hex}{suffix}")


async def _current_job(db_path: str, state: FSMContext, telegram_id: int):
    """Задание этого разговора.

    Сначала из состояния диалога, потом из базы: после рестарта бота состояние
    пусто, а оплаченное задание никуда не делось.
    """
    data = await state.get_data()
    job_id = data.get("job_id")
    job = get_job(db_path, job_id) if job_id else None
    return job or get_active_job(db_path, telegram_id)


async def _show_text_screen(message: Message, language: str, text: str) -> None:
    await message.answer(
        get_string("speech_text_received", language, text=text),
        reply_markup=build_speech_text_keyboard(language),
    )


async def _show_look_screen(message: Message, db_path: str, telegram_id: int, language: str) -> None:
    active = get_active_look(db_path, telegram_id)
    await message.answer(
        get_string("speech_look_screen", language, title=active.title),
        reply_markup=build_speech_look_keyboard(
            language, has_other_looks=count_looks(db_path, telegram_id) > 1
        ),
    )


@router.callback_query(F.data == CALLBACK_SPEAK)
async def on_speak(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    # Вайтлист — он же список купивших подписку. Для callback_query
    # middleware не срабатывает, проверяем руками.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    if get_face(db_path, telegram_id) is None:
        await callback.message.answer(get_string("speech_need_face", language))
        await callback.answer()
        return
    if get_active_look(db_path, telegram_id) is None:
        await callback.message.answer(get_string("speech_need_look", language))
        await callback.answer()
        return

    await state.set_state(SpeechStates.waiting_input)
    await callback.message.answer(get_string("speech_invite", language))
    await callback.answer()


@router.message(SpeechStates.waiting_input, F.text)
async def on_text(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    job_id = create_job(db_path, telegram_id, message.text.strip())
    await state.set_state(None)
    await state.update_data(job_id=job_id)
    await _show_text_screen(message, language, message.text.strip())


@router.message(SpeechStates.waiting_input, F.voice)
async def on_voice(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    audio_path = _tmp_path(".ogg")
    try:
        await message.bot.download(message.voice.file_id, destination=audio_path)
        audio_bytes = _read_bytes(audio_path)
    finally:
        pathlib.Path(audio_path).unlink(missing_ok=True)

    transcript = ""
    try:
        transcript = await transcribe(audio_bytes)
    except TranscriptionError:
        # Расшифровка нужна только чтобы было что переписывать текстом.
        # Сам кружок снимется и без неё — звук уже есть.
        logger.warning(
            "Speech transcription failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )

    job_id = create_job(db_path, telegram_id, transcript)
    await state.set_state(None)
    await state.update_data(job_id=job_id)

    try:
        duration = await attach_audio(db_path, job_id, audio_bytes)
    except RenderRefused as refusal:
        await message.answer(
            get_string("speech_too_long", language, limit=refusal.detail)
        )
        return

    await message.answer(
        get_string("speech_voiced", language, seconds=int(round(duration))),
        reply_markup=build_speech_voiced_keyboard(language),
    )


@router.message(SpeechStates.waiting_input)
async def on_wrong_input(message: Message, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, message.from_user.id, message.from_user.language_code)
    await message.answer(get_string("speech_expected_input", language))


@router.callback_query(F.data == CALLBACK_SPEECH_SCRIPT)
async def on_script(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    job = await _current_job(db_path, state, telegram_id)
    if job is None:
        await callback.answer()
        return

    settings = load_settings()
    # get_style_examples возвращает список строк, а не объектов.
    examples = get_style_examples(db_path, telegram_id, kind=KIND_SPOKEN)
    try:
        script = await generate_spoken_script(
            job.source_text,
            target_seconds=settings.avatar_target_seconds,
            spoken_examples=examples,
        )
    except Exception:
        logger.warning(
            "Spoken script generation failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )
        await callback.message.answer(get_string("speech_script_failed", language))
        await callback.answer()
        return

    # Исходный текст не затирается: с него начинается «Переписать».
    update_job(db_path, job.id, script=script)
    await _show_text_screen(callback.message, language, script)
    await callback.answer()


@router.callback_query(F.data == CALLBACK_SPEECH_VOICE_AS_IS)
async def on_voice_as_is(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    job = await _current_job(db_path, state, telegram_id)
    if job is None:
        await callback.answer()
        return

    text = job.script or job.source_text
    settings = load_settings()
    profile = get_voice_profile(db_path, telegram_id)

    if not settings.avatar_voice_synthesis_enabled or profile is None:
        # Клона ещё нет — отдаём суфлёр. Это выход, а не отказ: пользователь
        # наговорит тот же текст сам, и кружок всё равно получится.
        await callback.message.answer(
            get_string("speech_prompter", language, text=text)
        )
        await state.set_state(SpeechStates.waiting_input)
        await callback.answer()
        return

    try:
        audio_bytes = await synthesize(text, profile.external_voice_id)
    except VoiceGatewayError:
        logger.warning(
            "Speech synthesis failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )
        await callback.message.answer(get_string("speech_voice_failed", language))
        await callback.answer()
        return

    try:
        duration = await attach_audio(db_path, job.id, audio_bytes)
    except RenderRefused as refusal:
        await callback.message.answer(
            get_string("speech_too_long", language, limit=refusal.detail)
        )
        await callback.answer()
        return

    await callback.message.answer_voice(
        BufferedInputFile(audio_bytes, filename="speech.mp3")
    )
    await callback.message.answer(
        get_string("speech_voiced", language, seconds=int(round(duration))),
        reply_markup=build_speech_voiced_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data.in_({CALLBACK_SPEECH_REWRITE, CALLBACK_SPEECH_BACK_TO_TEXT, CALLBACK_SPEECH_REVOICE}))
async def on_back_to_input(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    language = _resolve_language(db_path, callback.from_user.id, callback.from_user.language_code)
    await state.set_state(SpeechStates.waiting_input)
    await callback.message.answer(get_string("speech_invite", language))
    await callback.answer()


@router.callback_query(F.data == CALLBACK_SPEECH_TO_LOOK)
async def on_to_look(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    await _show_look_screen(callback.message, db_path, telegram_id, language)
    await callback.answer()


@router.callback_query(F.data == CALLBACK_SPEECH_OTHER_LOOK)
async def on_other_look(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    active = get_active_look(db_path, telegram_id)
    await callback.message.answer(
        get_string(
            "looks_title",
            language,
            count=count_looks(db_path, telegram_id),
            # Активного может не быть: последний образ мог быть удалён уже
            # после того, как эта клавиатура была нарисована.
            active=active.title if active else get_string("double_look_none", language),
        ),
        reply_markup=build_looks_keyboard(language, get_looks(db_path, telegram_id)),
    )
    await callback.answer()


@router.callback_query(F.data.in_({CALLBACK_SPEECH_RENDER, CALLBACK_SPEECH_RETRY}))
async def on_render(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    # Самый дорогой вызов во всём боте — проверка обязана стоять и здесь,
    # а не только на входе в сценарий: до этой кнопки можно дойти по старой
    # клавиатуре, оставшейся в чате с прошлого раза.
    if not await check_whitelist_or_reply(callback, db_path, language):
        return

    job = await _current_job(db_path, state, telegram_id)
    look = get_active_look(db_path, telegram_id)
    if job is None or look is None:
        await callback.message.answer(get_string("speech_need_look", language))
        await callback.answer()
        return

    look_path = _tmp_path(".jpg")
    try:
        await callback.message.bot.download(look.file_id, destination=look_path)
        image_bytes = _read_bytes(look_path)
    finally:
        pathlib.Path(look_path).unlink(missing_ok=True)

    try:
        await request_render(db_path, job.id, image_bytes, look_id=look.id)
    except RenderRefused as refusal:
        if refusal.reason == REASON_LIMIT:
            await callback.message.answer(
                get_string("speech_limit_exceeded", language, left=refusal.detail)
            )
        else:
            await callback.message.answer(
                get_string("speech_too_long", language, limit=refusal.detail)
            )
        await callback.answer()
        return
    except AvatarGatewayError:
        logger.error(
            "Render start failed",
            extra={"user_id": telegram_id, "operation": "handler:speech"},
            exc_info=True,
        )
        update_job(db_path, job.id, status=STATUS_FAILED, error="запуск рендера не удался")
        await callback.message.answer(
            get_string("speech_failed", language),
            reply_markup=build_speech_failed_keyboard(language),
        )
        await callback.answer()
        return

    await callback.message.answer(get_string("speech_rendering", language))
    await callback.answer()


@router.callback_query(F.data == CALLBACK_SPEECH_PUBLISH)
async def on_publish(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    job = await _current_job(db_path, state, telegram_id)
    channel_id = get_channel_id(db_path, telegram_id)
    if job is None or job.result_file_id is None or channel_id is None:
        await callback.answer()
        return

    # Публикация по file_id: рендер уже оплачен, второй раз платить не за что.
    await callback.message.bot.send_video_note(channel_id, job.result_file_id)
    update_job(db_path, job.id, status=STATUS_PUBLISHED)
    await callback.message.answer(get_string("publish_success", language))
    await callback.answer()


@router.callback_query(F.data.in_({CALLBACK_SPEECH_CANCEL, CALLBACK_SPEECH_DROP}))
async def on_cancel(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)
    job = await _current_job(db_path, state, telegram_id)
    if job is not None:
        # Закрытое задание перестаёт быть активным — следующая речь начнётся
        # с чистого листа. Отдельного статуса «отменено» не заводим: для всей
        # остальной логики отменённое и несостоявшееся ведут себя одинаково.
        update_job(db_path, job.id, status=STATUS_FAILED, error="отменено пользователем")
    await state.set_state(None)
    await state.update_data(job_id=None)
    await callback.message.answer(get_string("speech_cancelled", language))
    await callback.answer()
```

В `bot/handlers/double.py` в конец `on_look_activate` дописать возврат к экрану образа, если речь уже озвучена:

```python
    # Если человек пришёл сюда из сценария речи по кнопке «Другой образ»,
    # вернём его туда же, а не оставим в галерее.
    from bot.storage.speech_jobs import STATUS_READY, STATUS_VOICED, get_active_job

    job = get_active_job(db_path, telegram_id)
    if job is not None and job.status in {STATUS_VOICED, STATUS_READY}:
        from bot.handlers.speech import _show_look_screen

        await _show_look_screen(callback.message, db_path, telegram_id, language)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handlers_speech.py tests/test_handlers_double.py -q`
Expected: PASS, оба файла.

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/speech.py bot/handlers/double.py tests/test_handlers_speech.py
git commit -m "feat: add the speech screens from text to a published circle"
```

---

### Task 20: Проводка и документация

**Files:**
- Modify: `bot/main.py`, `tests/conftest.py`, `.env.example`, `deploy/README-deploy.md`, `docs/manual-checklist.md`
- Test: `tests/test_main_site_api_wiring.py`

**Interfaces:**
- Consumes: `double.router`, `speech.router`, `build_speech_scheduler` (Task 14).
- Produces: рабочий бот.

- [ ] **Step 1: Write the failing test**

Дописать в `tests/test_main_site_api_wiring.py`:

```python
def test_speech_routers_are_wired_before_the_catch_all():
    # content_router ловит любое сообщение вне сценария. Если он окажется
    # раньше, экраны лица, образов и речи просто не получат управление.
    dispatcher = build_dispatcher()
    names = [router.name for router in dispatcher.sub_routers]

    assert "double" in names
    assert "speech" in names
    assert names.index("double") < names.index("content")
    assert names.index("speech") < names.index("content")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main_site_api_wiring.py -q`
Expected: FAIL — `AssertionError: assert 'double' in [...]`.

- [ ] **Step 3: Write minimal implementation**

В `bot/main.py` добавить импорты:

```python
from bot.handlers.double import router as double_router
from bot.handlers.speech import router as speech_router
from bot.services.speech_worker import build_speech_scheduler
```

В `build_dispatcher()` сразу после `dispatcher.include_router(circle_router)`:

```python
    # Рядом с circle_router и по той же причине: оба перехватывают сообщения
    # в своих состояниях, а content_router ловит всё подряд по StateFilter(None).
    dispatcher.include_router(double_router)
    dispatcher.include_router(speech_router)
```

В `run()` после запуска `balance_scheduler`:

```python
    speech_scheduler = build_speech_scheduler(
        bot, settings.db_path, settings.avatar_poll_interval_seconds
    )
    speech_scheduler.start()
```

В `tests/conftest.py` добавить импорты и вписать оба роутера в `_SINGLETON_ROUTERS`:

```python
from bot.handlers.double import router as double_router
from bot.handlers.speech import router as speech_router
```

```python
    circle_router,
    double_router,
    speech_router,
    content_router,
```

В `.env.example` в конец добавить:

```bash
# --- Говорящий двойник -------------------------------------------------
# Движок говорящего видео. Замеры 2026-08-06: klingai:avatar@2.0-standard —
# 270 ₽/мин, утверждён владельцем. Альтернативы и их цены — в
# docs/reference-video-avatar-engines.md.
AVATAR_PROVIDER=runware
AVATAR_MODEL=klingai:avatar@2.0-standard
# Модель правки образа по фотографии лица, 4 ₽ за картинку.
AVATAR_LOOK_MODEL=google:4@1
# Целевая длина кружка и жёсткий предел формата video note.
AVATAR_TARGET_SECONDS=30
AVATAR_MAX_SECONDS=60
# Потолок расхода на пользователя в секундах рендера за календарный месяц.
# 300 секунд — 10 кружков по 30 секунд, около 1350 ₽.
AVATAR_MONTHLY_SECONDS_LIMIT=300
# Как часто воркер опрашивает провайдера о готовности рендера.
AVATAR_POLL_INTERVAL_SECONDS=20
# Синтез речи клонированным голосом. Пока ключа ElevenLabs нет, оставить
# выключенным: написанный текст будет отдаваться суфлёром.
AVATAR_VOICE_SYNTHESIS_ENABLED=0
```

В `deploy/README-deploy.md` в раздел про переменные окружения добавить:

```markdown
### Говорящий двойник

Восемь переменных `AVATAR_*` (см. `.env.example`). Обязательных среди них нет:
без них бот работает на значениях по умолчанию, замеренных 2026-08-06.

Что стоит проверить на проде:

- `RUNWARE_API_KEY` заполнен и на балансе есть деньги — один кружок в
  30 секунд стоит около 135 ₽ плюс 4 ₽ за образ;
- `ffmpeg` и `ffprobe` доступны в `PATH` (уже стоят);
- `TMP_MEDIA_DIR` существует и на разделе есть место: во время рендера
  там лежат озвучка и скачанное видео, после доставки они удаляются;
- `AVATAR_VOICE_SYNTHESIS_ENABLED=1` включать **только** после того, как
  куплена подписка ElevenLabs Starter и `ELEVENLABS_API_KEY` заполнен.
```

В `docs/manual-checklist.md` добавить раздел:

```markdown
## Говорящий двойник

Проверяется глазами владельца, автотестами не заменяется:

- [ ] лицо на сгенерированном образе — своё, а не «похожее»;
- [ ] описание причёски не увело лицо (если причёску меняли);
- [ ] кадр образа крупный: голова и плечи во весь кадр;
- [ ] кружок не читается как подделка;
- [ ] губы попадают в звук на всей длине, а не только в начале;
- [ ] клонированный голос похож на настоящий (когда ключ появится);
- [ ] замерено фактическое время рендера 30 секунд — цифры до сих пор нет,
      на пяти секундах было 213–520 с.
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS, весь набор тестов проекта.

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/conftest.py tests/test_main_site_api_wiring.py .env.example deploy/README-deploy.md docs/manual-checklist.md
git commit -m "feat: wire the talking double into the bot and document its settings"
```

---

## Первый живой прогон

После Task 20 код готов, но три цифры и одно качество проверяются только живьём.
Порядок — от бесплатного к платному:

1. **Перенести лицо и готовый образ в бота.** У владельца они уже есть:
   «Мой двойник» → «Заменить лицо» (фотография), затем «Образы» → «Прислать
   картинку» (утверждённый образ). Ноль расхода.
2. **Наговорить речь голосовым** на 25–30 секунд. Ноль расхода: голосовое
   идёт в кружок как есть.
3. **Снять кружок** — около 135 ₽. Замерить время рендера от «Снимаю» до
   прихода кружка и записать в `docs/reference-video-avatar-engines.md`
   рядом с замерами на пяти секундах.
4. **Сверить payload** `avatar_gateway.start_render` с `/root/avatar_live_test.py`,
   если провайдер ответит ошибкой валидации.
5. Пройти чек-лист из `docs/manual-checklist.md`.

Только после этого имеет смысл покупать ElevenLabs Starter и включать
`AVATAR_VOICE_SYNTHESIS_ENABLED=1`: путь «написал текст — получил видео»
опирается на всё то же самое, что проверяется шагами выше.
