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
