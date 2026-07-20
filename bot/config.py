from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_DAILY_LIMIT = 20
DEFAULT_MONTHLY_LIMIT = 300
DEFAULT_DB_PATH = "bot.db"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_AI_PROXY_BASE_URL = "https://api.vsegpt.ru/v1"
DEFAULT_AI_GATEWAY_PROVIDER = "vsegpt"
DEFAULT_AI_GATEWAY_TEXT_MODEL = "openai/gpt-4o-mini"
DEFAULT_AI_GATEWAY_TRANSCRIPTION_MODEL = "stt-openai/whisper-1"
DEFAULT_AI_GATEWAY_MAX_RETRIES = 2
DEFAULT_AI_GATEWAY_TIMEOUT_SECONDS = 30.0
DEFAULT_CONTENT_VARIANTS_COUNT = 2


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
    ai_gateway_max_retries: int
    ai_gateway_timeout_seconds: float
    content_variants_count: int
    owner_chat_id: int
    daily_limit: int
    monthly_limit: int
    db_path: str
    log_level: str


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
    except ValueError as exc:
        raise ConfigError("DAILY_LIMIT и MONTHLY_LIMIT должны быть целыми числами.") from exc

    db_path = os.environ.get("DB_PATH", DEFAULT_DB_PATH)
    log_level = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)

    ai_proxy_base_url = os.environ.get("AI_PROXY_BASE_URL", DEFAULT_AI_PROXY_BASE_URL)
    ai_gateway_provider = os.environ.get("AI_GATEWAY_PROVIDER", DEFAULT_AI_GATEWAY_PROVIDER)
    ai_gateway_text_model = os.environ.get("AI_GATEWAY_TEXT_MODEL", DEFAULT_AI_GATEWAY_TEXT_MODEL)
    ai_gateway_transcription_model = os.environ.get(
        "AI_GATEWAY_TRANSCRIPTION_MODEL", DEFAULT_AI_GATEWAY_TRANSCRIPTION_MODEL
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

    return Settings(
        bot_token=bot_token,
        ai_proxy_api_key=ai_proxy_api_key,
        ai_proxy_base_url=ai_proxy_base_url,
        ai_gateway_provider=ai_gateway_provider,
        ai_gateway_text_model=ai_gateway_text_model,
        ai_gateway_transcription_model=ai_gateway_transcription_model,
        ai_gateway_max_retries=ai_gateway_max_retries,
        ai_gateway_timeout_seconds=ai_gateway_timeout_seconds,
        content_variants_count=content_variants_count,
        owner_chat_id=owner_chat_id,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        db_path=db_path,
        log_level=log_level,
    )
