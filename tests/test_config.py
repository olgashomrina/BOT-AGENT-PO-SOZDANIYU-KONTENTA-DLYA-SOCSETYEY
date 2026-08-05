from __future__ import annotations

import pytest

from bot.config import ConfigError, load_settings

REQUIRED_ENV = {
    "BOT_TOKEN": "123456:test-token",
    "AI_PROXY_API_KEY": "test-ai-key",
    "OWNER_CHAT_ID": "42",
}


def _set_required_env(monkeypatch, overrides=None):
    values = dict(REQUIRED_ENV)
    if overrides:
        values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _missing_env_file(tmp_path):
    return str(tmp_path / "no-such-file.env")


def test_load_settings_reads_required_fields(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("DAILY_LIMIT", raising=False)
    monkeypatch.delenv("MONTHLY_LIMIT", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.bot_token == "123456:test-token"
    assert settings.ai_proxy_api_key == "test-ai-key"
    assert settings.owner_chat_id == 42
    assert settings.daily_limit > 0
    assert settings.monthly_limit > 0
    assert settings.db_path
    assert settings.log_level


def test_load_settings_reads_optional_overrides(monkeypatch, tmp_path):
    _set_required_env(
        monkeypatch,
        {
            "DAILY_LIMIT": "10",
            "MONTHLY_LIMIT": "200",
            "DB_PATH": "custom.db",
            "LOG_LEVEL": "DEBUG",
        },
    )

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.daily_limit == 10
    assert settings.monthly_limit == 200
    assert settings.db_path == "custom.db"
    assert settings.log_level == "DEBUG"


def test_load_settings_transcription_model_defaults_to_cheapest_stt(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("AI_GATEWAY_TRANSCRIPTION_MODEL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    # 0.96 ₽/мин против 1.20 ₽/мин у stt-openai/whisper-1 (см. dengi.md).
    assert settings.ai_gateway_transcription_model == "stt-openai/gpt-4o-mini-transcribe"


def test_load_settings_spend_guards_have_defaults(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    for key in (
        "MAX_VOICE_DURATION_SECONDS",
        "DAILY_IMAGE_LIMIT",
        "BALANCE_ALERT_THRESHOLD_RUB",
        "BALANCE_CHECK_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.max_voice_duration_seconds == 180
    assert settings.daily_image_limit == 3
    assert settings.balance_alert_threshold_rub == 50.0
    assert settings.balance_check_interval_seconds == 3600


def test_load_settings_reads_spend_guard_overrides(monkeypatch, tmp_path):
    _set_required_env(
        monkeypatch,
        {
            "MAX_VOICE_DURATION_SECONDS": "60",
            "DAILY_IMAGE_LIMIT": "1",
            "BALANCE_ALERT_THRESHOLD_RUB": "12.5",
            "BALANCE_CHECK_INTERVAL_SECONDS": "600",
        },
    )

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.max_voice_duration_seconds == 60
    assert settings.daily_image_limit == 1
    assert settings.balance_alert_threshold_rub == 12.5
    assert settings.balance_check_interval_seconds == 600


def test_load_settings_raises_when_daily_image_limit_not_numeric(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"DAILY_IMAGE_LIMIT": "три"})

    with pytest.raises(ConfigError):
        load_settings(env_file=_missing_env_file(tmp_path))


def test_load_settings_raises_when_balance_threshold_not_numeric(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"BALANCE_ALERT_THRESHOLD_RUB": "мало"})

    with pytest.raises(ConfigError):
        load_settings(env_file=_missing_env_file(tmp_path))


def test_load_settings_premium_image_model_defaults_to_flux_pro(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("AI_GATEWAY_PREMIUM_IMAGE_MODEL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.ai_gateway_premium_image_model == "img-flux/pro1.1"


def test_load_settings_premium_image_model_reads_from_env(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"AI_GATEWAY_PREMIUM_IMAGE_MODEL": "img-flux/kontext-max"})

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.ai_gateway_premium_image_model == "img-flux/kontext-max"


def test_load_settings_raises_when_bot_token_missing(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(ConfigError):
        load_settings(env_file=_missing_env_file(tmp_path))


def test_load_settings_raises_when_owner_chat_id_not_numeric(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"OWNER_CHAT_ID": "not-a-number"})

    with pytest.raises(ConfigError):
        load_settings(env_file=_missing_env_file(tmp_path))


def test_load_settings_content_variants_count_default(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("CONTENT_VARIANTS_COUNT", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.content_variants_count == 2


def test_load_settings_content_variants_count_override(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"CONTENT_VARIANTS_COUNT": "5"})

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.content_variants_count == 5


def test_load_settings_mini_app_url_defaults_to_empty(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("MINI_APP_URL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.mini_app_url == ""


def test_load_settings_site_api_defaults(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("SITE_API_HOST", raising=False)
    monkeypatch.delenv("SITE_API_PORT", raising=False)
    monkeypatch.delenv("SITE_MEDIA_DIR", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.site_api_host == "0.0.0.0"
    assert settings.site_api_port == 8080
    assert settings.site_media_dir == "site_media"


def test_load_settings_reads_site_api_overrides(monkeypatch, tmp_path):
    _set_required_env(
        monkeypatch,
        {
            "MINI_APP_URL": "https://olgashomrina.github.io/my-lending-test/",
            "SITE_API_HOST": "127.0.0.1",
            "SITE_API_PORT": "9090",
            "SITE_MEDIA_DIR": "custom_media",
        },
    )

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.mini_app_url == "https://olgashomrina.github.io/my-lending-test/"
    assert settings.site_api_host == "127.0.0.1"
    assert settings.site_api_port == 9090
    assert settings.site_media_dir == "custom_media"


def test_load_settings_raises_when_site_api_port_not_numeric(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"SITE_API_PORT": "not-a-number"})

    with pytest.raises(ConfigError):
        load_settings(env_file=_missing_env_file(tmp_path))


def test_digest_send_hour_defaults_to_9(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("DIGEST_SEND_HOUR", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.digest_send_hour == 9


def test_digest_send_hour_reads_from_env(monkeypatch, tmp_path):
    _set_required_env(monkeypatch, {"DIGEST_SEND_HOUR": "14"})

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.digest_send_hour == 14


def test_image_provider_defaults_to_the_general_provider(monkeypatch, tmp_path):
    """Без отдельной настройки картинки идут туда же, куда всё остальное."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "vsegpt")
    monkeypatch.delenv("IMAGE_PROVIDER", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.image_provider == "vsegpt"


def test_runware_endpoint_has_defaults(monkeypatch, tmp_path):
    """Адрес и модель Runware заданы по умолчанию, ключ — пустой до настройки."""
    _set_required_env(monkeypatch)
    for key in ("RUNWARE_API_KEY", "RUNWARE_BASE_URL", "RUNWARE_IMAGE_MODEL"):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.runware_api_key == ""
    assert settings.runware_base_url == "https://api.runware.ai/v1"
    assert settings.runware_image_model == "runware:100@1"


def test_runware_settings_read_from_env(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-key")
    monkeypatch.setenv("RUNWARE_BASE_URL", "https://runware.test/v1")
    monkeypatch.setenv("RUNWARE_IMAGE_MODEL", "runware:101@1")

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.runware_api_key == "rw-key"
    assert settings.runware_base_url == "https://runware.test/v1"
    assert settings.runware_image_model == "runware:101@1"


def test_text_provider_defaults_to_the_general_provider(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "vsegpt")
    monkeypatch.delenv("TEXT_PROVIDER", raising=False)
    monkeypatch.delenv("RUNWARE_TEXT_MODEL", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.text_provider == "vsegpt"
    assert settings.runware_text_model == "deepseek-v4-flash"


def test_empty_values_mean_unset_not_empty(monkeypatch, tmp_path):
    """`.env.example` предлагает оставлять эти строки пустыми.

    `os.environ.get` вернул бы для них пустую строку, а не значение по
    умолчанию: пустой RUNWARE_BASE_URL — это сломанный адрес запроса, а
    пустой IMAGE_PROVIDER — провайдер, который не совпадает ни с чем.
    """
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "vsegpt")
    for key in (
        "IMAGE_PROVIDER",
        "TEXT_PROVIDER",
        "RUNWARE_BASE_URL",
        "RUNWARE_IMAGE_MODEL",
        "RUNWARE_PREMIUM_IMAGE_MODEL",
        "RUNWARE_TEXT_MODEL",
    ):
        monkeypatch.setenv(key, "")

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.image_provider == "vsegpt"
    assert settings.text_provider == "vsegpt"
    assert settings.runware_base_url == "https://api.runware.ai/v1"
    assert settings.runware_image_model == "runware:100@1"
    assert settings.runware_premium_image_model == "runware:101@1"
    assert settings.runware_text_model == "deepseek-v4-flash"


def test_transcription_provider_defaults_and_local_model(monkeypatch, tmp_path):
    """Расшифровка тоже выбирается на операцию, но по умолчанию не меняется."""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "vsegpt")
    for key in ("TRANSCRIPTION_PROVIDER", "LOCAL_WHISPER_MODEL", "LOCAL_WHISPER_COMPUTE_TYPE"):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.transcription_provider == "vsegpt"
    # `base` на живой записи владельца превратила "Создай мне пост" в
    # "Создание пуст" — по умолчанию только `small` (замер 05.08.2026).
    assert settings.local_whisper_model == "small"
    assert settings.local_whisper_compute_type == "int8"


def test_balance_provider_defaults_to_the_general_provider(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("AI_GATEWAY_PROVIDER", "vsegpt")
    monkeypatch.delenv("BALANCE_PROVIDER", raising=False)

    settings = load_settings(env_file=_missing_env_file(tmp_path))

    assert settings.balance_provider == "vsegpt"
