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
