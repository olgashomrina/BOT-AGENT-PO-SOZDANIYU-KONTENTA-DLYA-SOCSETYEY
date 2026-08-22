from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS whitelist (
    telegram_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    interface_language TEXT,
    content_language TEXT,
    channel_id INTEGER,
    pending_media_file_id TEXT,
    pending_media_type TEXT,
    onboarding_shown INTEGER,
    digest_topic TEXT,
    post_length TEXT
);

CREATE TABLE IF NOT EXISTS usage_log (
    telegram_id INTEGER NOT NULL,
    usage_date TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (telegram_id, usage_date)
);

-- Separate from usage_log on purpose: an AI image costs 3.90–15 ₽ against
-- ~0.25 ₽ for a post's text (see dengi.md), so it needs its own, much
-- tighter daily budget rather than sharing the general request quota.
CREATE TABLE IF NOT EXISTS image_usage_log (
    telegram_id INTEGER NOT NULL,
    usage_date TEXT NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (telegram_id, usage_date)
);

-- What each billed AI call actually cost, so the owner can see the real
-- per-user cost of running the bot before pricing a subscription (dengi.md).
-- Only images and transcription are recorded — see bot/services/cost_tracker.py
-- for why post text is left out.
CREATE TABLE IF NOT EXISTS cost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    cost_rub REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS style_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    example_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'written'
);

CREATE TABLE IF NOT EXISTS site_content (
    page TEXT NOT NULL,
    block_id TEXT NOT NULL,
    text TEXT,
    photo_file_id TEXT,
    photo_static_path TEXT,
    updated_at TEXT,
    PRIMARY KEY (page, block_id)
);

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

CREATE TABLE IF NOT EXISTS image_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (chat_id, message_id)
);

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

-- One row per user, keyed on telegram_id rather than an autoincrement id: a
-- user has exactly one current style profile, so INSERT OR REPLACE gives
-- overwrite semantics for free — unlike style_examples, which keeps a history.
CREATE TABLE IF NOT EXISTS style_profiles (
    telegram_id INTEGER PRIMARY KEY,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

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
"""


def _ensure_channel_id_column(connection: sqlite3.Connection) -> None:
    # Phase 12 added this column after Phase 0-9 were already deployed in
    # production (Plan.md "Фаза 12"). CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "channel_id" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN channel_id INTEGER")


def _ensure_pending_media_columns(connection: sqlite3.Connection) -> None:
    # Phase 13 added these columns after Phases 0-12 were already deployed in
    # production (Plan.md "Фаза 13"). CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "pending_media_file_id" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN pending_media_file_id TEXT")
    if "pending_media_type" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN pending_media_type TEXT")


def _ensure_onboarding_shown_column(connection: sqlite3.Connection) -> None:
    # Phase 15 added this column after Phases 0-14 were already deployed in
    # production (Plan.md "Фаза 15"). CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "onboarding_shown" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN onboarding_shown INTEGER")


def _ensure_digest_topic_column(connection: sqlite3.Connection) -> None:
    # This feature (Plan.md-adjacent digest work, docs/superpowers/specs/
    # 2026-07-28-topic-digest-design.md) shipped after Phases 0-16 were
    # already deployed in production. CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "digest_topic" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN digest_topic TEXT")


def _ensure_post_length_column(connection: sqlite3.Connection) -> None:
    # Настройка объёма поста (docs/superpowers/specs/
    # 2026-08-05-post-length-budget-design.md) появилась, когда бот уже был
    # развёрнут. CREATE TABLE IF NOT EXISTS покрывает только чистые установки —
    # уже существующей базе нужна явная миграция, иначе бот упадёт на первом
    # же запросе после выката.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "post_length" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN post_length TEXT")


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


def init_db(db_path: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA)
        _ensure_channel_id_column(connection)
        _ensure_pending_media_columns(connection)
        _ensure_onboarding_shown_column(connection)
        _ensure_digest_topic_column(connection)
        _ensure_post_length_column(connection)
        _ensure_style_example_kind_column(connection)
        connection.commit()
    finally:
        connection.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path)
