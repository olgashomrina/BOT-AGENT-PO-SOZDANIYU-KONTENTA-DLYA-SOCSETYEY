from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_DAILY_LIMIT = 20
DEFAULT_MONTHLY_LIMIT = 300
DEFAULT_DIGEST_SEND_HOUR = 9
DEFAULT_DB_PATH = "bot.db"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_AI_PROXY_BASE_URL = "https://api.vsegpt.ru/v1"
DEFAULT_AI_GATEWAY_PROVIDER = "vsegpt"
DEFAULT_AI_GATEWAY_TEXT_MODEL = "openai/gpt-4o-mini"
# vsegpt.ru тарифицирует распознавание речи как "1 токен = 1 секунда аудио",
# цена в каталоге указана за 1000 токенов. По живому каталогу на 2026-07-30:
# stt-openai/whisper-1 — 20.00 (1.20 ₽/мин), gpt-4o-mini-transcribe — 16.00
# (0.96 ₽/мин), gpt-4o-transcribe — 32.00 (1.92 ₽/мин). Дефолт — самый дешёвый
# из пригодных для русского (см. dengi.md, запись от 2026-07-30).
DEFAULT_AI_GATEWAY_TRANSCRIPTION_MODEL = "stt-openai/gpt-4o-mini-transcribe"
# Ограничение длины голосового: до него бот вообще не скачивает файл и не
# платит за расшифровку. Без лимита одно 10-минутное голосовое стоит ~10 ₽.
DEFAULT_MAX_VOICE_DURATION_SECONDS = 180
# Картинки — 70–90% себестоимости цикла (3.90 ₽ за flux-2-klein-4b, ~10–15 ₽
# за img-flux/pro1.1 против ~0.25 ₽ за текст). Дневной лимит на пользователя —
# единственная мера, которая реально удерживает баланс.
DEFAULT_DAILY_IMAGE_LIMIT = 3
# Порог в рублях, ниже которого бот предупреждает владельца о балансе
# AI-прокси, и период проверки.
DEFAULT_BALANCE_ALERT_THRESHOLD_RUB = 50.0
DEFAULT_BALANCE_CHECK_INTERVAL_SECONDS = 3600
# openrouter.ai bills in dollars, but every budget in this project — the alert
# threshold, the /costs report, the "this buys N more pictures" estimates — is
# in rubles, because that is what the owner budgets in. A rough constant is
# deliberate: it feeds warnings and estimates, never an actual charge, and a
# live FX lookup would add a dependency and a failure mode for no real gain.
DEFAULT_USD_RUB_RATE = 92.0
# dall-e-3 (vsegpt.ru's own docs example) is currently rejected by their
# proxy with "Temporarily disabled due to OpenAI blocking" (confirmed via a
# live request, 2026-07-20) — not a vsegpt.ru catalog-naming mismatch this
# time, an actual upstream OpenAI-side block. Flux 2 [klein] is the budget
# default. img-flux/pro1.1 gives noticeably more photorealistic output but
# costs ~15 rubles/image against a separate pay-per-use balance — tried as
# default 2026-07-25, reverted 2026-07-29 after it silently drained the
# account balance faster than expected (the vsegpt.ru "Профессиональный"
# tariff only lifts the per-request rate limit, it does NOT prepay usage).
# Set AI_GATEWAY_IMAGE_MODEL=img-flux/pro1.1 to opt back in deliberately.
DEFAULT_AI_GATEWAY_IMAGE_MODEL = "img-flux/flux-2-klein-4b"
DEFAULT_AI_GATEWAY_IMAGE_SIZE = "1024x1024"
# Separate from AI_GATEWAY_IMAGE_MODEL so the "Сделать реалистичнее" upgrade
# button (bot/handlers/refine.py::on_image_upgrade) keeps working regardless
# of which model the default (cheap) generation is pinned to.
DEFAULT_AI_GATEWAY_PREMIUM_IMAGE_MODEL = "img-flux/pro1.1"
DEFAULT_AI_GATEWAY_MAX_RETRIES = 2
DEFAULT_AI_GATEWAY_TIMEOUT_SECONDS = 30.0
DEFAULT_CONTENT_VARIANTS_COUNT = 2
DEFAULT_MINI_APP_URL = ""
DEFAULT_SITE_API_HOST = "0.0.0.0"
DEFAULT_SITE_API_PORT = 8080
DEFAULT_SITE_MEDIA_DIR = "site_media"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    ai_proxy_api_key: str
    ai_proxy_base_url: str
    ai_gateway_provider: str
    ai_gateway_text_model: str
    ai_gateway_transcription_model: str
    ai_gateway_image_model: str
    ai_gateway_image_size: str
    ai_gateway_premium_image_model: str
    ai_gateway_max_retries: int
    ai_gateway_timeout_seconds: float
    content_variants_count: int
    owner_chat_id: int
    daily_limit: int
    monthly_limit: int
    max_voice_duration_seconds: int
    daily_image_limit: int
    balance_alert_threshold_rub: float
    balance_check_interval_seconds: int
    usd_rub_rate: float
    digest_send_hour: int
    db_path: str
    log_level: str
    mini_app_url: str
    site_api_host: str
    site_api_port: int
    site_media_dir: str


def _require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ConfigError(
            f"Обязательная переменная окружения {key} не задана. "
            f"Проверьте, что файл .env заполнен (см. .env.example)."
        )
    return value


def load_settings(env_file: str | None = None) -> Settings:
    load_dotenv(dotenv_path=env_file, override=False)

    bot_token = _require("BOT_TOKEN")
    ai_proxy_api_key = _require("AI_PROXY_API_KEY")
    owner_chat_id_raw = _require("OWNER_CHAT_ID")

    try:
        owner_chat_id = int(owner_chat_id_raw)
    except ValueError as exc:
        raise ConfigError(
            "OWNER_CHAT_ID должен быть числом (Telegram chat id владельца)."
        ) from exc

    try:
        daily_limit = int(os.environ.get("DAILY_LIMIT", DEFAULT_DAILY_LIMIT))
        monthly_limit = int(os.environ.get("MONTHLY_LIMIT", DEFAULT_MONTHLY_LIMIT))
        digest_send_hour = int(os.environ.get("DIGEST_SEND_HOUR", DEFAULT_DIGEST_SEND_HOUR))
    except ValueError as exc:
        raise ConfigError(
            "DAILY_LIMIT, MONTHLY_LIMIT и DIGEST_SEND_HOUR должны быть целыми числами."
        ) from exc

    try:
        max_voice_duration_seconds = int(
            os.environ.get("MAX_VOICE_DURATION_SECONDS", DEFAULT_MAX_VOICE_DURATION_SECONDS)
        )
        daily_image_limit = int(os.environ.get("DAILY_IMAGE_LIMIT", DEFAULT_DAILY_IMAGE_LIMIT))
        balance_check_interval_seconds = int(
            os.environ.get(
                "BALANCE_CHECK_INTERVAL_SECONDS", DEFAULT_BALANCE_CHECK_INTERVAL_SECONDS
            )
        )
    except ValueError as exc:
        raise ConfigError(
            "MAX_VOICE_DURATION_SECONDS, DAILY_IMAGE_LIMIT и "
            "BALANCE_CHECK_INTERVAL_SECONDS должны быть целыми числами."
        ) from exc

    try:
        balance_alert_threshold_rub = float(
            os.environ.get("BALANCE_ALERT_THRESHOLD_RUB", DEFAULT_BALANCE_ALERT_THRESHOLD_RUB)
        )
        usd_rub_rate = float(os.environ.get("USD_RUB_RATE", DEFAULT_USD_RUB_RATE))
    except ValueError as exc:
        raise ConfigError(
            "BALANCE_ALERT_THRESHOLD_RUB и USD_RUB_RATE должны быть числами."
        ) from exc

    db_path = os.environ.get("DB_PATH", DEFAULT_DB_PATH)
    log_level = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)

    ai_proxy_base_url = os.environ.get("AI_PROXY_BASE_URL", DEFAULT_AI_PROXY_BASE_URL)
    ai_gateway_provider = os.environ.get("AI_GATEWAY_PROVIDER", DEFAULT_AI_GATEWAY_PROVIDER)
    ai_gateway_text_model = os.environ.get("AI_GATEWAY_TEXT_MODEL", DEFAULT_AI_GATEWAY_TEXT_MODEL)
    ai_gateway_transcription_model = os.environ.get(
        "AI_GATEWAY_TRANSCRIPTION_MODEL", DEFAULT_AI_GATEWAY_TRANSCRIPTION_MODEL
    )
    ai_gateway_image_model = os.environ.get("AI_GATEWAY_IMAGE_MODEL", DEFAULT_AI_GATEWAY_IMAGE_MODEL)
    ai_gateway_image_size = os.environ.get("AI_GATEWAY_IMAGE_SIZE", DEFAULT_AI_GATEWAY_IMAGE_SIZE)
    ai_gateway_premium_image_model = os.environ.get(
        "AI_GATEWAY_PREMIUM_IMAGE_MODEL", DEFAULT_AI_GATEWAY_PREMIUM_IMAGE_MODEL
    )

    try:
        ai_gateway_max_retries = int(
            os.environ.get("AI_GATEWAY_MAX_RETRIES", DEFAULT_AI_GATEWAY_MAX_RETRIES)
        )
        ai_gateway_timeout_seconds = float(
            os.environ.get("AI_GATEWAY_TIMEOUT_SECONDS", DEFAULT_AI_GATEWAY_TIMEOUT_SECONDS)
        )
    except ValueError as exc:
        raise ConfigError(
            "AI_GATEWAY_MAX_RETRIES должен быть целым числом, "
            "AI_GATEWAY_TIMEOUT_SECONDS — числом (секунды)."
        ) from exc

    try:
        content_variants_count = int(
            os.environ.get("CONTENT_VARIANTS_COUNT", DEFAULT_CONTENT_VARIANTS_COUNT)
        )
    except ValueError as exc:
        raise ConfigError("CONTENT_VARIANTS_COUNT должен быть целым числом.") from exc

    mini_app_url = os.environ.get("MINI_APP_URL", DEFAULT_MINI_APP_URL)
    site_api_host = os.environ.get("SITE_API_HOST", DEFAULT_SITE_API_HOST)
    site_media_dir = os.environ.get("SITE_MEDIA_DIR", DEFAULT_SITE_MEDIA_DIR)

    try:
        site_api_port = int(os.environ.get("SITE_API_PORT", DEFAULT_SITE_API_PORT))
    except ValueError as exc:
        raise ConfigError("SITE_API_PORT должен быть целым числом.") from exc

    return Settings(
        bot_token=bot_token,
        ai_proxy_api_key=ai_proxy_api_key,
        ai_proxy_base_url=ai_proxy_base_url,
        ai_gateway_provider=ai_gateway_provider,
        ai_gateway_text_model=ai_gateway_text_model,
        ai_gateway_transcription_model=ai_gateway_transcription_model,
        ai_gateway_image_model=ai_gateway_image_model,
        ai_gateway_image_size=ai_gateway_image_size,
        ai_gateway_premium_image_model=ai_gateway_premium_image_model,
        ai_gateway_max_retries=ai_gateway_max_retries,
        ai_gateway_timeout_seconds=ai_gateway_timeout_seconds,
        content_variants_count=content_variants_count,
        owner_chat_id=owner_chat_id,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        max_voice_duration_seconds=max_voice_duration_seconds,
        daily_image_limit=daily_image_limit,
        balance_alert_threshold_rub=balance_alert_threshold_rub,
        balance_check_interval_seconds=balance_check_interval_seconds,
        usd_rub_rate=usd_rub_rate,
        digest_send_hour=digest_send_hour,
        db_path=db_path,
        log_level=log_level,
        mini_app_url=mini_app_url,
        site_api_host=site_api_host,
        site_api_port=site_api_port,
        site_media_dir=site_media_dir,
    )
