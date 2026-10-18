"""Application settings, loaded once at startup from environment variables.

Every setting the worker needs lives on one typed, immutable ``Settings`` object.
Values come from real environment variables, or from a local ``.env`` file during
development (real environment variables always win over the file). Deployed
servers have no ``.env``; their values come from a secrets manager.

Required settings are the ones every call needs. If any is missing or malformed,
``load_settings`` raises ``ConfigurationError`` naming the offending variables, so
the worker refuses to start instead of failing halfway through a call. Keys that
only some provider presets use (e.g. ``INWORLD_API_KEY``) are optional here; the
provider registry checks them when a call selects a preset that needs them.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from companion.contracts.dispatch import Region

DEFAULT_ENV_FILE = Path(".env")

# Vendors whose API key a provider preset may need.
type Credential = Literal["deepgram", "fish", "groq", "bedrock", "inworld"]


class Environment(StrEnum):
    """Where the worker is running. Drives log format and privacy rules."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Minimum severity of log lines that get written."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogFormat(StrEnum):
    """How log lines are rendered."""

    # Readable console output in development, JSON in production.
    AUTO = "auto"
    CONSOLE = "console"
    JSON = "json"


class ConfigurationError(Exception):
    """Raised when required settings are missing or invalid.

    The message lists environment variable names and what is wrong with each,
    but never the values themselves, because many of them are secrets.
    """


class Settings(BaseSettings):
    """All configuration for the worker. Build it with ``load_settings()``."""

    # An empty ``KEY=`` copied from .env.example counts as missing rather than "",
    # so it fails fast. Unrelated variables (e.g. experiment-only keys) are ignored,
    # and settings are immutable once loaded. load_settings chooses the .env path.
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    # --- Runtime behaviour -------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.AUTO

    # --- Required: every call needs these ------------------------------------
    # Secrets are SecretStr so they never appear in logs, reprs or errors.
    livekit_url: str
    livekit_api_key: SecretStr
    livekit_api_secret: SecretStr
    # Connection URLs usually embed a password, so they're treated as secrets too.
    redis_url: SecretStr
    supabase_db_url: SecretStr

    # The region profile this worker serves (ARCHITECTURE.md -> Regions).
    worker_region: Region = "au"

    # --- Vendor keys -------------------------------------------------------------
    # Optional here: no vendor is fixed, so the provider registry requires only the
    # keys the worker's region profile uses, and rejects a call whose presets need
    # a key that isn't set.
    deepgram_api_key: SecretStr | None = None
    fish_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    bedrock_api_key: SecretStr | None = None
    inworld_api_key: SecretStr | None = None
    # Bedrock presets carry their own region; this one is for the latency probe.
    bedrock_region: str = "ap-southeast-2"

    # Accept any casing in the environment (LOG_LEVEL=info, ENVIRONMENT=Production).
    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("environment", "log_format", "worker_region", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("livekit_url")
    @classmethod
    def _check_livekit_url(cls, value: str) -> str:
        if not value.startswith(("wss://", "ws://")):
            raise ValueError("must be a WebSocket URL starting with wss:// or ws://")
        return value

    @field_validator("bedrock_region")
    @classmethod
    def _check_bedrock_region(cls, value: str) -> str:
        # AWS region codes look like "ap-southeast-2": letters, dashes, a final digit.
        if not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", value):
            raise ValueError("must be an AWS region code such as ap-southeast-2")
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("must start with redis:// or rediss://")
        return value

    @field_validator("supabase_db_url")
    @classmethod
    def _check_supabase_db_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("postgresql://", "postgres://")):
            raise ValueError("must be a Postgres connection string starting with postgresql://")
        return value

    @model_validator(mode="after")
    def _no_debug_logging_in_production(self) -> Self:
        # DEBUG is the only level allowed to include what users said, so it is
        # refused in production: personal information must never reach
        # production logs.
        if self.environment is Environment.PRODUCTION and self.log_level is LogLevel.DEBUG:
            raise ValueError("LOG_LEVEL=DEBUG is not allowed when ENVIRONMENT=production")
        return self

    def api_key(self, credential: Credential) -> SecretStr | None:
        """The configured key for a vendor credential, or None if it isn't set."""
        keys: dict[Credential, SecretStr | None] = {
            "deepgram": self.deepgram_api_key,
            "fish": self.fish_api_key,
            "groq": self.groq_api_key,
            "bedrock": self.bedrock_api_key,
            "inworld": self.inworld_api_key,
        }
        return keys[credential]

    @property
    def use_json_logs(self) -> bool:
        """Whether logs should be rendered as JSON (resolves ``LogFormat.AUTO``)."""
        if self.log_format is LogFormat.AUTO:
            return self.environment is Environment.PRODUCTION
        return self.log_format is LogFormat.JSON


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Load and validate settings, or raise ``ConfigurationError``.

    Args:
        env_file: Local ``.env`` file to read if it exists. ``None`` reads real
            environment variables only (tests use this so a developer's own
            ``.env`` can't leak into them).
    """
    try:
        # Values come from the environment, not arguments. mypy's pydantic plugin
        # understands that; pyright (the editor's checker) doesn't, so it's told here.
        return Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        raise ConfigurationError(_describe(error)) from None


def _describe(error: ValidationError) -> str:
    """Turn pydantic's error into a readable list, without echoing any values.

    pydantic's own message includes the rejected input, which could be a
    secret, so only the variable name and the reason are kept. ``from None``
    above also stops the original error (and its values) being chained on.
    """
    lines = ["Invalid configuration:"]
    for item in error.errors(include_input=False, include_url=False):
        # pydantic prefixes messages from our own validators with "Value error, ".
        reason = item["msg"].removeprefix("Value error, ")
        if item["type"] == "missing":
            reason = "is not set"
        if item["loc"]:
            # loc holds the field name; the environment variable is its uppercase form.
            lines.append(f"  - {str(item['loc'][0]).upper()}: {reason}")
        else:
            # Rules spanning several fields (model validators) have no single field.
            lines.append(f"  - {reason}")
    return "\n".join(lines)
