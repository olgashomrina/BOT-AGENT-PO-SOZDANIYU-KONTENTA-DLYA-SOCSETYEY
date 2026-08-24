from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_MY_DOUBLE = "menu:my_double"
CALLBACK_CONSENT_ACCEPT = "circle:consent_ok"
CALLBACK_DONORS_DONE = "circle:donors_done"
CALLBACK_ADD_DONORS = "circle:add_donors"
CALLBACK_DELETE = "circle:delete"
CALLBACK_DELETE_CONFIRM = "circle:delete_confirm"

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
