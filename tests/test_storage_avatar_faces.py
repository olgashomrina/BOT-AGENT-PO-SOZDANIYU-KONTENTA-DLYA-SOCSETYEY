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
