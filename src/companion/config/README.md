# `config/` — Config

Loads every setting the backend needs (API keys, URLs, runtime behaviour) from environment variables into one typed, validated, read-only `Settings` object.

**Owns:** reading and validating configuration at startup; failing fast with a clear error if a required variable is missing or malformed.

**Does not own:** vendor-specific provider settings (those live in `providers/`), or per-call choices (those arrive in dispatch metadata, see `dispatch/`).

## Usage

```python
from companion.config import load_settings

settings = load_settings()  # raises ConfigurationError if invalid
settings.groq_api_key.get_secret_value()
```

Call `load_settings()` once at worker startup and pass the object (or the values a module needs) down — there is no global settings instance, which keeps modules testable.

## Rules

- **Sources:** real environment variables, plus a local `.env` file if present (development only). Real environment variables win over the file. `KEY=` with no value counts as not set.
- **Required** (the worker won't start without them): `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DEEPGRAM_API_KEY`, `GROQ_API_KEY`, `BEDROCK_API_KEY`, `BEDROCK_REGION` (validated as an AWS region code), `REDIS_URL`, `SUPABASE_DB_URL`. Groq and Bedrock are both required because either can host the LLMs, selected per call.
- **Optional, checked per preset:** keys only some provider presets use (currently `INWORLD_API_KEY`) may be unset here; the provider registry rejects a call that selects a preset needing a missing key.
- **Secrets** are `SecretStr` — hidden when printed or logged. Connection URLs are secrets too (they embed passwords).
- **Error messages** name the variable and the problem, never the value.
- **Runtime behaviour:** `ENVIRONMENT` (`development` | `production`), `LOG_LEVEL` (`DEBUG` | `INFO` | `WARNING` | `ERROR`), `LOG_FORMAT` (`auto` | `console` | `json`; `auto` = console in development, JSON in production). `LOG_LEVEL=DEBUG` is refused in production, because DEBUG is the only level allowed to contain what users said.

Tunable pipeline numbers (bet cap, timeouts, fade length, …) are added here as the features that use them are built.

**Spec:** REQUIREMENTS.md → "Secrets & config".

**Status:** implemented (task 0.7).
