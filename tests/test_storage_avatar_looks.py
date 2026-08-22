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


def test_set_active_with_missing_look_id_leaves_state_untouched(db_path):
    # Пользователь мог нажать инлайн-кнопку под давно устаревшей клавиатурой,
    # когда образ уже удалён. Это не должно оставить пользователя вовсе без
    # активного образа.
    first = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    set_active_look(db_path, TELEGRAM_ID, 999999)

    assert get_active_look(db_path, TELEGRAM_ID).id == first
    assert [look.is_active for look in get_looks(db_path, TELEGRAM_ID)].count(True) == 1


def test_set_active_with_foreign_look_id_leaves_both_users_untouched(db_path):
    other_id = 602
    mine = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    theirs = add_look(db_path, other_id, "img-theirs", "улица", SOURCE_UPLOADED)

    set_active_look(db_path, TELEGRAM_ID, theirs)

    assert get_active_look(db_path, TELEGRAM_ID).id == mine
    assert [look.is_active for look in get_looks(db_path, TELEGRAM_ID)].count(True) == 1
    assert get_active_look(db_path, other_id).id == theirs
    assert [look.is_active for look in get_looks(db_path, other_id)].count(True) == 1


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
