from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection

# Plan.md Phase 14: "лимит на количество (старые вытесняются)" — keep only
# the most recent MAX_EXAMPLES_PER_USER examples per user, evicting older
# ones on every insert.
#
# Raised 5 -> 10 for the authored-post flow, which requires at least 5
# examples before it will write anything: a cap of exactly 5 would leave
# the user no room to add a better example without losing an existing one.
MAX_EXAMPLES_PER_USER = 10


def add_style_example(db_path: str, telegram_id: int, text: str) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO style_examples (telegram_id, example_text, created_at) "
            "VALUES (?, ?, ?)",
            (telegram_id, text, created_at),
        )
        # Eviction keyed on id (insertion order), not created_at: sqlite's
        # TEXT timestamp column can't disambiguate two inserts within the
        # same wall-clock resolution, but AUTOINCREMENT id always does.
        connection.execute(
            "DELETE FROM style_examples WHERE telegram_id = ? AND id NOT IN ("
            "SELECT id FROM style_examples WHERE telegram_id = ? "
            "ORDER BY id DESC LIMIT ?)",
            (telegram_id, telegram_id, MAX_EXAMPLES_PER_USER),
        )
        connection.commit()
    finally:
        connection.close()


def get_style_examples(
    db_path: str, telegram_id: int, limit: int = MAX_EXAMPLES_PER_USER
) -> list[str]:
    # Most-recent-first (id DESC): the newest examples are the most likely
    # to still reflect the user's current voice, and this is also the order
    # they get quoted into the generation prompt (content_generator.py).
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT example_text FROM style_examples WHERE telegram_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (telegram_id, limit),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        connection.close()


def clear_style_examples(db_path: str, telegram_id: int) -> None:
    # Used by the authored-post flow's "загрузить новые образцы" branch:
    # without a wipe, new examples would merge with the old ones under the
    # same cap, and the user would get a voice blended from two eras of
    # their writing instead of the one they just supplied.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM style_examples WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
