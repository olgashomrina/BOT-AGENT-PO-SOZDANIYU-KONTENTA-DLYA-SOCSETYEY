from __future__ import annotations

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import content as content_module
from bot.handlers.content import (
    VoiceConfirmStates,
    cmd_clear_media,
    detect_input_type,
    on_transcript_confirm,
    on_transcript_edit_request,
    on_transcript_edited_text,
    route_content,
)
from bot.locales.loader import get_string
from bot.services import content_generator, input_processor, output_formatter
from bot.services.ai_gateway import AIGatewayTimeoutError, TranscriptionError
from bot.storage.refine_context import get_refine_context
from bot.storage.style_examples import add_style_example
from bot.storage.users import (
    get_pending_media,
    set_content_language,
    set_interface_language,
    set_pending_media,
)

TELEGRAM_ID = 111
CHAT_ID = 222

# send_variants (bot/handlers/content.py) now records a refine_contexts row
# keyed on the sent message's real id, so every AsyncMock standing in for
# Message.answer here must return something with a genuine int message_id
# (sqlite rejects binding a MagicMock) — a shared counter keeps every
# generated id unique across a test's several sent messages.
_sent_message_ids = itertools.count(1000)


def _make_sent_message():
    return SimpleNamespace(message_id=next(_sent_message_ids))


@pytest.fixture(autouse=True)
def _ai_gateway_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _mock_generate_variants(monkeypatch, telegram_variants=None, vk_variants=None):
    telegram_variants = telegram_variants or ["TG вариант 1", "TG вариант 2"]
    vk_variants = vk_variants or ["VK вариант 1", "VK вариант 2"]
    mock = AsyncMock(side_effect=[telegram_variants, vk_variants])
    monkeypatch.setattr(content_generator, "generate_variants", mock)
    return mock


def _make_message(
    telegram_id: int = TELEGRAM_ID,
    text: str | None = None,
    voice=None,
    audio=None,
    entities=None,
    caption=None,
    caption_entities=None,
    photo=None,
    video=None,
):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.chat = SimpleNamespace(id=telegram_id)
    message.answer = AsyncMock(side_effect=lambda *args, **kwargs: _make_sent_message())
    message.text = text
    message.voice = voice
    message.audio = audio
    message.entities = entities
    message.caption = caption
    message.caption_entities = caption_entities
    message.photo = photo
    message.video = video
    return message


def _make_voice(duration: int = 5, file_id: str = "abc"):
    # Real aiogram Voice/Audio objects always carry a duration, and the
    # handler now reads it to reject overlong recordings before paying for
    # transcription — so the stand-ins must carry one too.
    return SimpleNamespace(file_id=file_id, duration=duration)


def _make_bot(audio_bytes: bytes = b"fake-bytes"):
    import io

    bot = AsyncMock()
    bot.download = AsyncMock(return_value=io.BytesIO(audio_bytes))
    return bot


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = ""):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    callback.message.chat = SimpleNamespace(id=telegram_id)
    callback.message.answer = AsyncMock(side_effect=lambda *args, **kwargs: _make_sent_message())
    return callback


def test_detects_link_from_plain_url_in_text():
    message = _make_message(text="Посмотри вот это: https://example.com/article")

    assert detect_input_type(message) == "link"


def test_detects_link_from_url_entity():
    entity = SimpleNamespace(type="url")
    message = _make_message(text="example.com/article", entities=[entity])

    assert detect_input_type(message) == "link"


def test_detects_voice():
    message = _make_message(voice=_make_voice())

    assert detect_input_type(message) == "voice"


def test_detects_audio():
    message = _make_message(audio=SimpleNamespace(file_id="abc"))

    assert detect_input_type(message) == "voice"


def test_detects_plain_text():
    message = _make_message(text="Просто текст без ссылок и голоса")

    assert detect_input_type(message) == "text"


@pytest.mark.asyncio
async def test_route_content_text_generates_variants_for_both_platforms(db_path, monkeypatch):
    """Phase 9 happy path: plain text in -> generation (mocked AI, no network)
    -> user receives formatted variants with refine buttons for both platforms."""
    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    assert mock_generate_variants.await_count == 2
    telegram_call, vk_call = mock_generate_variants.await_args_list
    assert telegram_call.args[0] == "Просто текст"
    assert telegram_call.args[1] == "telegram"
    assert vk_call.args[1] == "vk"

    assert message.answer.await_count == 4
    expected = [
        ("telegram", "TG вариант 1", 1),
        ("telegram", "TG вариант 2", 2),
        ("vk", "VK вариант 1", 1),
        ("vk", "VK вариант 2", 2),
    ]
    for call, (platform, text, index) in zip(message.answer.call_args_list, expected):
        assert call.args[0] == output_formatter.format_variant(text)
        assert call.kwargs["parse_mode"] == output_formatter.PARSE_MODE
        keyboard = call.kwargs["reply_markup"]
        row = keyboard.inline_keyboard[0]
        assert row[0].callback_data == f"refine:more:{platform}:{index}"
        assert row[1].callback_data == f"refine:shorten:{platform}:{index}"
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_route_content_link_success_generates_variants_for_both_platforms(db_path, monkeypatch):
    message = _make_message(text="https://example.com/article")
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "extract_from_link", lambda url: "Извлечённый текст статьи."
    )
    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    telegram_call, vk_call = mock_generate_variants.await_args_list
    assert telegram_call.args[0] == "Извлечённый текст статьи."
    assert vk_call.args[0] == "Извлечённый текст статьи."

    assert message.answer.await_count == 4
    sent_texts = [call.args[0] for call in message.answer.call_args_list]
    for variant in ["TG вариант 1", "VK вариант 1"]:
        assert output_formatter.format_variant(variant) in sent_texts


@pytest.mark.asyncio
async def test_route_content_link_failure_replies_with_friendly_error(db_path, monkeypatch):
    message = _make_message(text="https://example.com/blocked")
    bot = _make_bot()
    state = _make_state()

    def _raise(url):
        raise input_processor.LinkExtractionError("trafilatura returned None")

    monkeypatch.setattr(input_processor, "extract_from_link", _raise)

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_link_extraction", "ru"))


@pytest.mark.asyncio
async def test_route_content_voice_shows_transcript_for_confirmation(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Расшифрованный текст.")
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("transcript_preview", "ru", text="Расшифрованный текст.")
    assert "reply_markup" in kwargs

    assert await state.get_state() == VoiceConfirmStates.waiting_for_confirmation.state
    data = await state.get_data()
    assert data["transcript"] == "Расшифрованный текст."


@pytest.mark.asyncio
async def test_route_content_rejects_voice_longer_than_limit_without_transcribing(
    db_path, monkeypatch
):
    monkeypatch.setenv("MAX_VOICE_DURATION_SECONDS", "180")
    message = _make_message(voice=_make_voice(duration=181))
    bot = _make_bot()
    state = _make_state()

    transcribe_mock = AsyncMock(return_value="Не должно вызваться.")
    monkeypatch.setattr(input_processor, "handle_voice", transcribe_mock)

    await route_content(message, db_path, bot, state)

    transcribe_mock.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        get_string("error_voice_too_long", "ru", limit_minutes=3)
    )
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_route_content_accepts_voice_exactly_at_limit(db_path, monkeypatch):
    monkeypatch.setenv("MAX_VOICE_DURATION_SECONDS", "180")
    message = _make_message(voice=_make_voice(duration=180))
    bot = _make_bot()
    state = _make_state()

    transcribe_mock = AsyncMock(return_value="Расшифрованный текст.")
    monkeypatch.setattr(input_processor, "handle_voice", transcribe_mock)

    await route_content(message, db_path, bot, state)

    transcribe_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_content_rejects_long_audio_file_too(db_path, monkeypatch):
    monkeypatch.setenv("MAX_VOICE_DURATION_SECONDS", "60")
    message = _make_message(audio=_make_voice(duration=600, file_id="xyz"))
    bot = _make_bot()
    state = _make_state()

    transcribe_mock = AsyncMock(return_value="Не должно вызваться.")
    monkeypatch.setattr(input_processor, "handle_voice", transcribe_mock)

    await route_content(message, db_path, bot, state)

    transcribe_mock.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        get_string("error_voice_too_long", "ru", limit_minutes=1)
    )


@pytest.mark.asyncio
async def test_voice_confirm_flow_generates_variants_for_both_platforms(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Расшифрованный текст.")
    )
    await route_content(message, db_path, bot, state)

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    callback = _make_callback()
    await on_transcript_confirm(callback, state, db_path)

    telegram_call, vk_call = mock_generate_variants.await_args_list
    assert telegram_call.args[0] == "Расшифрованный текст."

    assert callback.message.answer.await_count == 4
    sent_texts = [call.args[0] for call in callback.message.answer.call_args_list]
    for variant in ["TG вариант 1", "VK вариант 1"]:
        assert output_formatter.format_variant(variant) in sent_texts
    callback.answer.assert_awaited_once()
    assert await state.get_state() is None
    data = await state.get_data()
    assert data["source_text"] == "Расшифрованный текст."
    assert data["content_language"] == "ru"
    assert data["language"] == "ru"


@pytest.mark.asyncio
async def test_voice_edit_flow_shows_edited_text_for_reconfirmation(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Неверно распознанный текст.")
    )
    await route_content(message, db_path, bot, state)

    edit_callback = _make_callback()
    await on_transcript_edit_request(edit_callback, state)

    edit_callback.message.answer.assert_awaited_once_with(
        get_string("transcript_edit_prompt", "ru")
    )
    assert await state.get_state() == VoiceConfirmStates.waiting_for_edit.state

    edited_message = _make_message(text="Правильный текст, который я имел в виду.")
    await on_transcript_edited_text(edited_message, state)

    edited_message.answer.assert_awaited_once()
    args, kwargs = edited_message.answer.call_args
    assert args[0] == get_string(
        "transcript_preview", "ru", text="Правильный текст, который я имел в виду."
    )
    assert "reply_markup" in kwargs

    assert await state.get_state() == VoiceConfirmStates.waiting_for_confirmation.state
    data = await state.get_data()
    assert data["transcript"] == "Правильный текст, который я имел в виду."
    assert "source_text" not in data


@pytest.mark.asyncio
async def test_voice_edit_then_confirm_generates_variants_with_edited_text(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Неверно распознанный текст.")
    )
    await route_content(message, db_path, bot, state)

    edit_callback = _make_callback()
    await on_transcript_edit_request(edit_callback, state)

    edited_message = _make_message(text="Правильный текст, который я имел в виду.")
    await on_transcript_edited_text(edited_message, state)

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    confirm_callback = _make_callback()
    await on_transcript_confirm(confirm_callback, state, db_path)

    telegram_call, _ = mock_generate_variants.await_args_list
    assert telegram_call.args[0] == "Правильный текст, который я имел в виду."
    assert confirm_callback.message.answer.await_count == 4
    assert await state.get_state() is None
    assert (await state.get_data())["source_text"] == "Правильный текст, который я имел в виду."


@pytest.mark.asyncio
async def test_voice_edit_can_loop_multiple_times_before_confirming(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Первая версия.")
    )
    await route_content(message, db_path, bot, state)

    await on_transcript_edit_request(_make_callback(), state)
    await on_transcript_edited_text(_make_message(text="Вторая версия."), state)
    assert await state.get_state() == VoiceConfirmStates.waiting_for_confirmation.state

    await on_transcript_edit_request(_make_callback(), state)
    await on_transcript_edited_text(_make_message(text="Третья версия."), state)
    assert await state.get_state() == VoiceConfirmStates.waiting_for_confirmation.state
    assert (await state.get_data())["transcript"] == "Третья версия."

    _mock_generate_variants(monkeypatch)
    confirm_callback = _make_callback()
    await on_transcript_confirm(confirm_callback, state, db_path)

    assert (await state.get_data())["source_text"] == "Третья версия."


@pytest.mark.asyncio
async def test_non_text_input_during_edit_reprompts_without_finishing(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Расшифрованный текст.")
    )
    await route_content(message, db_path, bot, state)
    await on_transcript_edit_request(_make_callback(), state)

    stray_voice_message = _make_message(voice=SimpleNamespace(file_id="xyz"))
    await on_transcript_edited_text(stray_voice_message, state)

    stray_voice_message.answer.assert_awaited_once_with(
        get_string("transcript_edit_prompt", "ru")
    )
    assert await state.get_state() == VoiceConfirmStates.waiting_for_edit.state
    data = await state.get_data()
    assert "source_text" not in data
    assert data["transcript"] == "Расшифрованный текст."


@pytest.mark.asyncio
async def test_route_content_voice_transcription_error_replies_friendly_message(
    db_path, monkeypatch
):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=TranscriptionError("empty transcript from provider")),
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_transcription", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_route_content_voice_ai_gateway_error_replies_friendly_message(db_path, monkeypatch):
    message = _make_message(voice=_make_voice())
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=AIGatewayTimeoutError("timed out after retries")),
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_route_content_text_generation_error_replies_friendly_message(db_path, monkeypatch):
    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        content_generator,
        "generate_variants",
        AsyncMock(side_effect=AIGatewayTimeoutError("timed out after retries")),
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_generation_uses_content_language_not_interface_language(db_path, monkeypatch):
    set_interface_language(db_path, TELEGRAM_ID, "ru")
    set_content_language(db_path, TELEGRAM_ID, "en")

    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    telegram_call, vk_call = mock_generate_variants.await_args_list
    assert telegram_call.args[2] == "en"
    assert vk_call.args[2] == "en"


@pytest.mark.asyncio
async def test_generation_forwards_stored_style_examples(db_path, monkeypatch):
    add_style_example(db_path, TELEGRAM_ID, "Мой старый пост.")
    add_style_example(db_path, TELEGRAM_ID, "Ещё один старый пост.")

    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    telegram_call, vk_call = mock_generate_variants.await_args_list
    expected_examples = ["Ещё один старый пост.", "Мой старый пост."]
    assert telegram_call.kwargs["style_examples"] == expected_examples
    assert vk_call.kwargs["style_examples"] == expected_examples


@pytest.mark.asyncio
async def test_generation_without_stored_style_examples_is_unchanged(db_path, monkeypatch):
    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    telegram_call, vk_call = mock_generate_variants.await_args_list
    assert telegram_call.kwargs["style_examples"] == []
    assert vk_call.kwargs["style_examples"] == []


@pytest.mark.asyncio
async def test_receiving_photo_sets_pending_media_and_confirms(db_path, monkeypatch):
    photo_sizes = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="largest")]
    message = _make_message(photo=photo_sizes)
    bot = _make_bot()
    state = _make_state()

    await route_content(message, db_path, bot, state)

    assert get_pending_media(db_path, TELEGRAM_ID) == ("largest", "photo")
    message.answer.assert_awaited_once_with(get_string("media_attached_confirmation", "ru"))


@pytest.mark.asyncio
async def test_receiving_video_sets_pending_media_and_confirms(db_path, monkeypatch):
    message = _make_message(video=SimpleNamespace(file_id="video-file"))
    bot = _make_bot()
    state = _make_state()

    await route_content(message, db_path, bot, state)

    assert get_pending_media(db_path, TELEGRAM_ID) == ("video-file", "video")
    message.answer.assert_awaited_once_with(get_string("media_attached_confirmation", "ru"))


@pytest.mark.asyncio
async def test_photo_with_caption_is_not_routed_as_content(db_path, monkeypatch):
    photo_sizes = [SimpleNamespace(file_id="only-size")]
    message = _make_message(photo=photo_sizes, caption="https://example.com/should-not-matter")
    bot = _make_bot()
    state = _make_state()

    mock_generate_variants = _mock_generate_variants(monkeypatch)

    await route_content(message, db_path, bot, state)

    mock_generate_variants.assert_not_awaited()
    assert get_pending_media(db_path, TELEGRAM_ID) == ("only-size", "photo")
    message.answer.assert_awaited_once_with(get_string("media_attached_confirmation", "ru"))


@pytest.mark.asyncio
async def test_clear_media_command_clears_existing_attachment(db_path):
    set_pending_media(db_path, TELEGRAM_ID, "file-id", "photo")
    message = _make_message()

    await cmd_clear_media(message, db_path)

    assert get_pending_media(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("media_cleared_confirmation", "ru"))


@pytest.mark.asyncio
async def test_clear_media_command_with_nothing_pending(db_path):
    message = _make_message()

    await cmd_clear_media(message, db_path)

    assert get_pending_media(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("media_nothing_to_clear", "ru"))


@pytest.mark.asyncio
async def test_normal_generation_records_context_without_hashtags(db_path, monkeypatch):
    # The anti-leak guarantee: an ordinary post must never inherit hashtags
    # from an authored-post run earlier in the same chat. This used to be
    # enforced by resetting a shared FSM flag; it is now structural, because
    # each sent variant carries its own row. Simulate the leftovers anyway —
    # a stale FSM flag must not be able to influence the recorded context.
    state = _make_state()
    await state.update_data(with_hashtags=True)
    _mock_generate_variants(monkeypatch)
    message = _make_message(text="Исходный текст")
    message.chat = SimpleNamespace(id=CHAT_ID)
    sent_ids = iter(range(201, 220))
    message.answer = AsyncMock(
        side_effect=lambda *args, **kwargs: SimpleNamespace(message_id=next(sent_ids))
    )

    await route_content(message, db_path, _make_bot(), state)

    recorded = [
        get_refine_context(db_path, CHAT_ID, message_id) for message_id in range(201, 207)
    ]
    assert [context for context in recorded if context is not None], "no context rows were recorded"
    for context in recorded:
        if context is not None:
            assert context["with_hashtags"] is False
            assert context["source_text"] == "Исходный текст"


@pytest.mark.asyncio
async def test_send_variants_sends_one_message_per_variant_with_refine_keyboard(db_path):
    message = _make_message()
    sent = [SimpleNamespace(message_id=201), SimpleNamespace(message_id=202)]
    message.answer = AsyncMock(side_effect=sent)
    message.chat = SimpleNamespace(id=CHAT_ID)
    # Deliberately contain HTML-special characters so that format_variant's
    # escaping is a non-trivial transform: an identity-transform input would
    # let a "drop format_variant" mutation slip through undetected.
    variants = [
        "Первый <b>вариант</b> & <i>текст</i>",
        "Второй <script>alert(1)</script> & больше",
    ]
    # Expected output written as a literal (NOT recomputed via
    # output_formatter.format_variant) so the test actually pins down what
    # format_variant is supposed to produce, per bot/services/output_formatter.py:
    # & -> &amp;, then < -> &lt;, then > -> &gt; (in that order).
    expected_escaped = [
        "Первый &lt;b&gt;вариант&lt;/b&gt; &amp; &lt;i&gt;текст&lt;/i&gt;",
        "Второй &lt;script&gt;alert(1)&lt;/script&gt; &amp; больше",
    ]

    await content_module.send_variants(
        message,
        "ru",
        "telegram",
        variants,
        db_path=db_path,
        source_text="Исходник",
        content_language="ru",
        with_hashtags=False,
    )

    assert message.answer.await_count == 2
    for call, expected_text, index in zip(
        message.answer.await_args_list, expected_escaped, [1, 2], strict=True
    ):
        assert call.args[0] == expected_text
        assert call.kwargs["parse_mode"] == output_formatter.PARSE_MODE
        keyboard = call.kwargs["reply_markup"]
        # Inspect actual callback_data contents (not just "is not None") so a
        # language/platform swap in send_variants's signature, or a broken
        # per-call index, makes this assertion fail. build_refine_keyboard's
        # first row is [more_button, shorten_button]; callback_data format is
        # "<prefix>:<platform>:<variant_index>" per bot/keyboards/refine.py.
        more_button, shorten_button = keyboard.inline_keyboard[0]
        assert more_button.callback_data == f"refine:more:telegram:{index}"
        assert shorten_button.callback_data == f"refine:shorten:telegram:{index}"


@pytest.mark.asyncio
async def test_send_variants_records_context_for_each_sent_message(db_path):
    message = _make_message()
    sent = [SimpleNamespace(message_id=101), SimpleNamespace(message_id=102)]
    message.answer = AsyncMock(side_effect=sent)
    message.chat = SimpleNamespace(id=CHAT_ID)

    await content_module.send_variants(
        message,
        "ru",
        "telegram",
        ["Первый", "Второй"],
        db_path=db_path,
        source_text="Исходник",
        content_language="ru",
        with_hashtags=True,
    )

    for message_id in (101, 102):
        context = get_refine_context(db_path, CHAT_ID, message_id)
        assert context["source_text"] == "Исходник"
        assert context["with_hashtags"] is True
        assert context["platform"] == "telegram"
