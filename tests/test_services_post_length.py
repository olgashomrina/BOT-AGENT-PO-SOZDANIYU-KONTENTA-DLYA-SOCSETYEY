from __future__ import annotations

from bot.services import post_length


def test_measure_counts_ascii_like_len():
    assert post_length.measure("hello") == 5


def test_measure_counts_cyrillic_as_one_unit_each():
    assert post_length.measure("привет") == 6


def test_measure_counts_emoji_as_two_units():
    assert post_length.measure("🙂") == 2
    assert post_length.measure("привет 🙂") == 9


def test_fits_uses_utf16_units_not_python_len():
    text = "🙂" * 300

    assert len(text) == 300
    assert not post_length.fits(text, 500)
    assert post_length.fits(text, 600)


def test_no_preset_exceeds_the_telegram_caption_limit():
    for preset in post_length.PRESETS.values():
        assert preset.max_units <= post_length.TELEGRAM_CAPTION_LIMIT


def test_every_preset_targets_less_than_its_own_ceiling():
    for preset in post_length.PRESETS.values():
        assert preset.target_chars < preset.max_units


def test_default_preset_is_a_known_preset():
    assert post_length.DEFAULT_PRESET in post_length.PRESETS


def test_get_preset_falls_back_to_default_for_unknown_or_missing_key():
    assert post_length.get_preset("bogus").key == post_length.DEFAULT_PRESET
    assert post_length.get_preset(None).key == post_length.DEFAULT_PRESET


def test_next_shorter_walks_down_the_ladder():
    assert post_length.next_shorter("expanded") == "medium"
    assert post_length.next_shorter("medium") == "short"
    assert post_length.next_shorter("short") is None


def test_next_shorter_treats_an_unknown_key_as_the_default():
    assert post_length.next_shorter("bogus") == post_length.next_shorter(
        post_length.DEFAULT_PRESET
    )


def test_trim_returns_text_unchanged_when_it_fits():
    text = "Короткий пост. Заходите!"

    assert post_length.trim(text, 100) == text


def test_trim_cuts_on_a_sentence_boundary():
    text = "Первое предложение. Второе предложение. Третье предложение."

    result = post_length.trim(text, 40)

    assert result == "Первое предложение. Второе предложение."
    assert post_length.measure(result) <= 40


def test_trim_keeps_the_hashtag_line():
    body = "Первое предложение. Второе предложение. Третье предложение."
    text = f"{body}\n\n#кофе #утро"

    result = post_length.trim(text, 60)

    assert result.endswith("#кофе #утро")
    assert post_length.measure(result) <= 60


def test_trim_does_not_mistake_a_hashtag_inside_a_sentence_for_the_tag_line():
    text = "Первое предложение. Пишите в #комментариях что думаете об этом."

    result = post_length.trim(text, 25)

    assert result == "Первое предложение."


def test_trim_falls_back_to_a_word_boundary_without_sentence_ends():
    text = "слово " * 20

    result = post_length.trim(text, 50)

    assert result.endswith("…")
    assert post_length.measure(result) <= 50


def test_trim_never_returns_an_empty_string():
    text = "оченьдлинноесловобезпробеловипунктуации" * 3

    result = post_length.trim(text, 20)

    assert result
    assert post_length.measure(result) <= 20


def test_trim_does_not_split_an_emoji_in_half():
    text = "🙂" * 30

    result = post_length.trim(text, 22)

    assert "�" not in result
    assert post_length.measure(result) <= 22


def test_trim_returns_nothing_for_a_zero_budget():
    assert post_length.trim("Длинный текст, который не влезает.", 0) == ""


def test_trim_returns_nothing_for_a_negative_budget():
    # Регрессия: срез encode()[: units * 2] при отрицательном units — это
    # питоновский срез с конца, который оставлял почти весь текст.
    assert post_length.trim("Длинный текст, который не влезает.", -1) == ""


def test_budget_instruction_names_the_target_number():
    preset = post_length.get_preset("short")

    assert str(preset.target_chars) in post_length.build_budget_instruction(preset)


def test_budget_instruction_mentions_urls_and_the_call_to_action():
    instruction = post_length.build_budget_instruction(post_length.get_preset("medium"))

    assert "URL" in instruction
    assert "call-to-action" in instruction


def test_retry_instruction_asks_for_less_than_the_first_attempt():
    preset = post_length.get_preset("medium")

    assert preset.retry_target_chars < preset.target_chars
    assert str(preset.retry_target_chars) in post_length.build_retry_instruction(preset)
