"""What each AI call costs, in rubles.

Covers both proxies the bot can be pointed at. openrouter.ai prices are in
dollars and were measured against a live account on 2026-07-31 (see
dengi.md); they are stored here already converted at `_USD_RUB`, which is the
same rough constant the balance check uses. Model slugs differ between the
two — openrouter.ai has no `stt-` prefix — so the tables never collide and a
single lookup serves whichever provider is configured.

Prices are taken from the live vsegpt.ru catalog (`GET /v1/models`, checked
2026-07-30 — see dengi.md for the readings and the reasoning). Two things
about that catalog matter here:

* Speech-to-text is billed as "1 token = 1 second of audio", and the catalog
  price is per 1000 tokens — so `stt-openai/gpt-4o-mini-transcribe` at 16.00
  means 0.96 ₽ per minute.
* Image models are billed per image, and the catalog number is that
  per-image price directly.

Only image generation and transcription are itemised. Post text is billed per
token and comes to roughly 0.25 ₽ per generation cycle — under 5% of the
total, and it would need token counts plumbed out of every AI Gateway call to
record exactly. Deliberate omission, not an oversight: the numbers here exist
to keep the balance from draining, and it drains through pictures.

Prices are a snapshot: vsegpt.ru can change them at any time, and an unknown
model falls back to a conservative estimate rather than to zero, so a new
model never silently reports as free.
"""

from __future__ import annotations

_USD_RUB = 92.0

# ₽ per 1000 seconds of audio (the catalog's own unit for STT models).
_STT_RUB_PER_1000_SECONDS = {
    # vsegpt.ru
    "stt-openai/gpt-4o-mini-transcribe": 16.00,
    "stt-openai/whisper-1": 20.00,
    "stt-openai/whisper-1-diarize": 30.00,
    "stt-openai/gpt-4o-transcribe": 32.00,
    "stt-deepgram/nova-3": 20.00,
    "stt-deepgram/nova-3-diarize": 30.00,
    # openrouter.ai — measured: whisper-1 billed $0.0001 per second, i.e.
    # $0.006/min, which is 0.55 ₽/min against 1.20 ₽/min at vsegpt.ru.
    "openai/whisper-1": 0.0001 * 1000 * _USD_RUB,
    "openai/gpt-4o-mini-transcribe": 0.00005 * 1000 * _USD_RUB,
    "openai/gpt-4o-transcribe": 0.0001 * 1000 * _USD_RUB,
}
_STT_FALLBACK_RUB_PER_1000_SECONDS = 32.00

# ₽ per generated image.
_IMAGE_RUB_PER_IMAGE = {
    # vsegpt.ru
    "img-flux/flux-2-klein-4b": 3.90,
    "img-flux/flux-2-klein-9b": 10.00,
    "img-flux/pro1.1": 10.00,
    # openrouter.ai — measured on a real 1024x1024 generation: $0.0085 for
    # gpt-5-image-mini, five times cheaper than the vsegpt.ru budget model.
    # The rest are scaled from their per-image-token catalog prices.
    "openai/gpt-5-image-mini": 0.0085 * _USD_RUB,
    "openai/gpt-5-image": 0.042 * _USD_RUB,
    "google/gemini-2.5-flash-image": 0.032 * _USD_RUB,
    "google/gemini-3.1-flash-image": 0.063 * _USD_RUB,
}
_IMAGE_FALLBACK_RUB_PER_IMAGE = 15.00


def transcription_cost(model: str, duration_seconds: float) -> float:
    """Cost of transcribing `duration_seconds` of audio with `model`."""
    rate = _STT_RUB_PER_1000_SECONDS.get(model, _STT_FALLBACK_RUB_PER_1000_SECONDS)
    return rate * duration_seconds / 1000


def image_cost(model: str) -> float:
    """Cost of one generated image from `model`."""
    return _IMAGE_RUB_PER_IMAGE.get(model, _IMAGE_FALLBACK_RUB_PER_IMAGE)


def images_affordable(balance_rub: float, model: str) -> int:
    """How many images of `model` a given balance still buys."""
    if balance_rub <= 0:
        return 0
    return int(balance_rub // image_cost(model))


def voice_minutes_affordable(balance_rub: float, model: str) -> int:
    """How many whole minutes of audio a given balance still transcribes."""
    if balance_rub <= 0:
        return 0
    cost_per_minute = transcription_cost(model, 60)
    return int(balance_rub // cost_per_minute)
