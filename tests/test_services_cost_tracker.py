from __future__ import annotations

import pytest

from bot.services import cost_tracker


def test_transcription_cost_matches_catalog_price_per_minute():
    # 16.00 ₽ per 1000 seconds == 0.96 ₽ per minute (dengi.md, 2026-07-30).
    cost = cost_tracker.transcription_cost("stt-openai/gpt-4o-mini-transcribe", 60)

    assert cost == pytest.approx(0.96)


def test_transcription_cost_of_whisper_is_higher_than_the_default_model():
    default_model_cost = cost_tracker.transcription_cost(
        "stt-openai/gpt-4o-mini-transcribe", 60
    )
    whisper_cost = cost_tracker.transcription_cost("stt-openai/whisper-1", 60)

    assert whisper_cost == pytest.approx(1.20)
    assert whisper_cost > default_model_cost


def test_transcription_cost_scales_with_duration():
    assert cost_tracker.transcription_cost("stt-openai/whisper-1", 30) == pytest.approx(0.60)
    assert cost_tracker.transcription_cost("stt-openai/whisper-1", 600) == pytest.approx(12.00)


def test_transcription_cost_of_zero_length_audio_is_zero():
    assert cost_tracker.transcription_cost("stt-openai/whisper-1", 0) == 0


def test_unknown_stt_model_is_not_free():
    # A model missing from the snapshot must never look free, or an unnoticed
    # config change would silently stop showing up in the spend numbers.
    assert cost_tracker.transcription_cost("stt-vendor/brand-new", 60) > 0


def test_image_cost_uses_catalog_prices():
    assert cost_tracker.image_cost("img-flux/flux-2-klein-4b") == pytest.approx(3.90)
    assert cost_tracker.image_cost("img-flux/pro1.1") == pytest.approx(10.00)


def test_unknown_image_model_falls_back_to_a_conservative_price():
    assert cost_tracker.image_cost("img-vendor/brand-new") >= 10.00


def test_images_affordable_counts_whole_images_only():
    assert cost_tracker.images_affordable(10.0, "img-flux/flux-2-klein-4b") == 2


def test_images_affordable_is_zero_for_empty_or_negative_balance():
    assert cost_tracker.images_affordable(0.0, "img-flux/pro1.1") == 0
    assert cost_tracker.images_affordable(-5.0, "img-flux/pro1.1") == 0


def test_voice_minutes_affordable_counts_whole_minutes():
    # 50 ₽ at 0.96 ₽/min buys 52 whole minutes.
    assert cost_tracker.voice_minutes_affordable(
        50.0, "stt-openai/gpt-4o-mini-transcribe"
    ) == 52


def test_voice_minutes_affordable_is_zero_for_empty_balance():
    assert cost_tracker.voice_minutes_affordable(0.0, "stt-openai/whisper-1") == 0


def test_runware_image_models_are_priced_from_live_measurements():
    """Иначе картинка Runware считалась бы по запасной цене 15 ₽ вместо 0.06 ₽.

    Отчёт `/costs` и оценка «на остаток хватит на N картинок» берут цену
    отсюда, и промах в 250 раз сделал бы обе бесполезными.
    """
    assert cost_tracker.image_cost("runware:100@1") == pytest.approx(0.0006 * 92.0)
    assert cost_tracker.image_cost("runware:101@1") == pytest.approx(0.0013 * 92.0)


def test_local_transcription_is_free():
    """Своя модель на своём сервере не стоит за минуту ничего.

    Без этого `/costs` списывал бы на расшифровку цену vsegpt, которой на
    самом деле никто не платит, и отчёт врал бы тем сильнее, чем больше
    голосовых наговорили.
    """
    assert cost_tracker.transcription_cost("local-whisper-small", 600) == 0.0


def test_transcription_model_label_names_the_local_model():
    """В отчёте должно быть видно, чем именно расшифровано."""
    assert cost_tracker.transcription_model_label("local", "small", "stt-openai/x") == (
        "local-whisper-small"
    )
    assert cost_tracker.transcription_model_label("vsegpt", "small", "stt-openai/x") == (
        "stt-openai/x"
    )
