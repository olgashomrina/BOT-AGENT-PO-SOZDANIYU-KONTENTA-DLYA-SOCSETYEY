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
    # runware.ai — measured on real 1024x1024 generations on 2026-08-04, with
    # `includeCost` in the request, so these are the amounts actually billed
    # rather than list prices. Two orders of magnitude below vsegpt.ru.
    "runware:100@1": 0.0006 * _USD_RUB,  # FLUX.1 Schnell — 0.06 ₽
    "runware:101@1": 0.0013 * _USD_RUB,  # FLUX.1 Dev — 0.12 ₽
    # runware.ai, Nano Banana — правка образа по фотографии лица. Замер
    # 2026-08-06 живым прогоном: 4 ₽ за картинку.
    "google:4@1": 4.0,
}
_IMAGE_FALLBACK_RUB_PER_IMAGE = 15.00


# Recognition running on our own server costs nothing per minute — the server
# is paid for either way. Matched by prefix rather than by exact name so that
# switching the local model (small → medium) doesn't silently start charging
# the fallback rate to the report.
_LOCAL_MODEL_PREFIX = "local-whisper"


def transcription_model_label(
    provider: str, local_model: str, remote_model: str
) -> str:
    """What to write into the cost log as the transcription model.

    The report is read by a human deciding where the money goes, so it has to
    name what actually did the work, not what the remote provider would have
    used if it had been asked.
    """
    if provider.lower() == "local":
        return f"{_LOCAL_MODEL_PREFIX}-{local_model}"
    return remote_model


def transcription_cost(model: str, duration_seconds: float) -> float:
    """Cost of transcribing `duration_seconds` of audio with `model`."""
    if model.startswith(_LOCAL_MODEL_PREFIX):
        return 0.0
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


# ₽ за секунду готового видео. Замерено живыми оплаченными прогонами
# 2026-08-06 (docs/reference-video-avatar-engines.md), а не взято из прайса:
# у klingai:7@1 документация разошлась с фактом в 7,4 раза.
_VIDEO_RUB_PER_SECOND = {
    "pixverse:lipsync@1": 0.0136 * _USD_RUB,
    "prunaai:p-video@avatar": 0.0245 * _USD_RUB,
    "sync:lipsync-2@1": 0.0443 * _USD_RUB,
    "klingai:avatar@2.0-standard": 0.0446 * _USD_RUB,
    "klingai:7@1": 0.0684 * _USD_RUB,
    "klingai:avatar@2.0-pro": 0.0881 * _USD_RUB,
    "heygen:avatar@4": 0.0977 * _USD_RUB,
    "bytedance:5@2": 0.1200 * _USD_RUB,
}
# Незнакомая модель считается по самому дорогому из замеренных движков:
# отчёт должен пугать, а не убаюкивать.
_VIDEO_FALLBACK_RUB_PER_SECOND = 0.1200 * _USD_RUB


def video_cost(model: str, seconds: float) -> float:
    """Оценка стоимости `seconds` секунд готового видео у `model`.

    Это оценка «до факта»: показать цену и проверить лимит. Списывается
    всегда фактическая цена из ответа провайдера, если он её вернул.
    """
    rate = _VIDEO_RUB_PER_SECOND.get(model, _VIDEO_FALLBACK_RUB_PER_SECOND)
    return rate * seconds
