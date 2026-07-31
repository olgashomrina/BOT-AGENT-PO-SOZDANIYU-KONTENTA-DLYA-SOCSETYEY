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
