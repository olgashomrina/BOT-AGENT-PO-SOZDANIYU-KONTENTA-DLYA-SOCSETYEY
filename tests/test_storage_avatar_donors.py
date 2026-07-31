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
