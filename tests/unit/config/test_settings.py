"""Tests for loading and validating settings from environment variables."""

from pathlib import Path

import pytest

from companion.config import (
    ConfigurationError,
    Environment,
    LogFormat,
    LogLevel,
    load_settings,
)

# The required variables, plus the vendor keys most tests use. Values are obviously fake.
REQUIRED_ENV = {
    "LIVEKIT_URL": "wss://example.livekit.cloud",
    "LIVEKIT_API_KEY": "lk-key",
    "LIVEKIT_API_SECRET": "lk-secret-value",
    "REDIS_URL": "rediss://default:redis-password@example.upstash.io:6379",
    "SUPABASE_DB_URL": "postgresql://postgres:db-password@example.supabase.com:5432/postgres",
}
VENDOR_ENV = {
    "DEEPGRAM_API_KEY": "deepgram-key",
    "FISH_API_KEY": "fish-key",
    "GROQ_API_KEY": "groq-key",
    "BEDROCK_API_KEY": "bedrock-key",
}
VALID_ENV = {**REQUIRED_ENV, **VENDOR_ENV}

SETTINGS_VARIABLES = [
    *VALID_ENV,
    "INWORLD_API_KEY",
    "BEDROCK_REGION",
    "WORKER_REGION",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "LOG_FORMAT",
]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with none of our variables set.

    ``autouse`` applies this to every test in the file automatically, so a
    variable set on the developer's machine can't change a test's outcome.
    monkeypatch undoes all changes when each test finishes.
    """
    for name in SETTINGS_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set the valid baseline plus any per-test overrides."""
    for name, value in {**VALID_ENV, **overrides}.items():
        monkeypatch.setenv(name, value)


def test_loads_valid_settings_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)

    settings = load_settings(env_file=None)

    assert settings.livekit_url == "wss://example.livekit.cloud"
    assert settings.api_key("groq") is not None
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.worker_region == "au"
    assert settings.log_level is LogLevel.INFO
    assert settings.log_format is LogFormat.AUTO
    assert settings.bedrock_region == "ap-southeast-2"
    assert settings.inworld_api_key is None


def test_secrets_are_hidden_when_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)

    settings = load_settings(env_file=None)

    printed = repr(settings) + str(settings)
    secrets = (
        "lk-secret-value",
        "groq-key",
        "bedrock-key",
        "fish-key",
        "redis-password",
        "db-password",
    )
    for secret in secrets:
        assert secret not in printed


def test_missing_required_variables_are_all_named(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch)
    monkeypatch.delenv("LIVEKIT_API_KEY")
    monkeypatch.delenv("REDIS_URL")

    with pytest.raises(ConfigurationError) as caught:
        load_settings(env_file=None)

    message = str(caught.value)
    assert "LIVEKIT_API_KEY: is not set" in message
    assert "REDIS_URL: is not set" in message


def test_empty_value_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # A blank line copied from .env.example ("LIVEKIT_API_SECRET=") must not pass as "".
    set_env(monkeypatch, LIVEKIT_API_SECRET="")

    with pytest.raises(ConfigurationError, match="LIVEKIT_API_SECRET: is not set"):
        load_settings(env_file=None)


def test_vendor_keys_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    # Which vendor keys a worker needs depends on its region profile, checked by the
    # provider registry, so none are required here.
    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GROQ_API_KEY", "")

    settings = load_settings(env_file=None)

    for credential in ("deepgram", "fish", "groq", "bedrock", "inworld"):
        assert settings.api_key(credential) is None


def test_api_key_returns_each_vendor_key(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, INWORLD_API_KEY="inworld-key")
    settings = load_settings(env_file=None)

    keys = {c: settings.api_key(c) for c in ("deepgram", "fish", "groq", "bedrock", "inworld")}

    assert {c: k.get_secret_value() if k else None for c, k in keys.items()} == {
        "deepgram": "deepgram-key",
        "fish": "fish-key",
        "groq": "groq-key",
        "bedrock": "bedrock-key",
        "inworld": "inworld-key",
    }


def test_worker_region_accepts_any_casing_and_rejects_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_env(monkeypatch, WORKER_REGION="US")
    assert load_settings(env_file=None).worker_region == "us"

    set_env(monkeypatch, WORKER_REGION="eu")
    with pytest.raises(ConfigurationError, match="WORKER_REGION"):
        load_settings(env_file=None)


@pytest.mark.parametrize(
    ("variable", "bad_value"),
    [
        ("LIVEKIT_URL", "https://example.livekit.cloud"),
        ("REDIS_URL", "http://default:redis-password@example.upstash.io"),
        ("SUPABASE_DB_URL", "mysql://postgres:db-password@example.com/db"),
        ("ENVIRONMENT", "staging"),
        ("LOG_LEVEL", "LOUD"),
        ("BEDROCK_REGION", "Sydney"),
    ],
)
def test_invalid_values_are_rejected_without_echoing_them(
    monkeypatch: pytest.MonkeyPatch, variable: str, bad_value: str
) -> None:
    set_env(monkeypatch, **{variable: bad_value})

    with pytest.raises(ConfigurationError) as caught:
        load_settings(env_file=None)

    message = str(caught.value)
    assert f"{variable}:" in message
    # The rejected value may be a secret, so it must never appear in the error.
    assert bad_value not in message
    # The original pydantic error (which does include values) isn't chained on.
    assert caught.value.__cause__ is None


def test_debug_logging_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, ENVIRONMENT="production", LOG_LEVEL="DEBUG")

    with pytest.raises(ConfigurationError, match="not allowed when ENVIRONMENT=production"):
        load_settings(env_file=None)


def test_accepts_any_casing_for_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, ENVIRONMENT="Production", LOG_LEVEL="warning", LOG_FORMAT="JSON")

    settings = load_settings(env_file=None)

    assert settings.environment is Environment.PRODUCTION
    assert settings.log_level is LogLevel.WARNING
    assert settings.log_format is LogFormat.JSON


@pytest.mark.parametrize(
    ("environment", "log_format", "expected_json"),
    [
        ("development", "auto", False),
        ("production", "auto", True),
        ("development", "json", True),
        ("production", "console", False),
    ],
)
def test_json_log_resolution(
    monkeypatch: pytest.MonkeyPatch, environment: str, log_format: str, expected_json: bool
) -> None:
    set_env(monkeypatch, ENVIRONMENT=environment, LOG_FORMAT=log_format)

    assert load_settings(env_file=None).use_json_logs is expected_json


def test_reads_env_file_and_real_variables_win(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(f"{name}={value}" for name, value in VALID_ENV.items())
        + "\nGROQ_API_KEY=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPGRAM_API_KEY", "from-environment")

    settings = load_settings(env_file=env_file)

    groq, deepgram = settings.api_key("groq"), settings.api_key("deepgram")
    assert groq is not None
    assert groq.get_secret_value() == "from-file"
    assert deepgram is not None
    assert deepgram.get_secret_value() == "from-environment"


def test_missing_env_file_is_fine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Deployed servers have no .env; settings come from real variables alone.
    set_env(monkeypatch)

    settings = load_settings(env_file=tmp_path / "does-not-exist.env")

    assert settings.livekit_url == "wss://example.livekit.cloud"
