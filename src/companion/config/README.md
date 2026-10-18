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
- **Required** (the worker won't start without them): `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `REDIS_URL`, `SUPABASE_DB_URL`.
- **Worker region:** `WORKER_REGION` (`au` or `us`, default `au`) picks the region profile this worker serves.
- **Vendor keys are optional here:** `DEEPGRAM_API_KEY`, `FISH_API_KEY`, `GROQ_API_KEY`, `BEDROCK_API_KEY`, `INWORLD_API_KEY`. No vendor is fixed, so the provider registry (`providers/`) requires only the keys the worker's region profile uses, and rejects a call whose presets need a key that isn't set. `Settings.api_key(...)` returns a key by vendor.
- **`BEDROCK_REGION`** (default `ap-southeast-2`) is used only by the latency probe; Bedrock presets carry their own region.
- **Secrets** are `SecretStr` — hidden when printed or logged. Connection URLs are secrets too (they embed passwords).
- **Error messages** name the variable and the problem, never the value.
- **Runtime behaviour:** `ENVIRONMENT` (`development` | `production`), `LOG_LEVEL` (`DEBUG` | `INFO` | `WARNING` | `ERROR`), `LOG_FORMAT` (`auto` | `console` | `json`; `auto` = console in development, JSON in production). `LOG_LEVEL=DEBUG` is refused in production, because DEBUG is the only level allowed to contain what users said.

Tunable pipeline numbers (bet cap, timeouts, fade length, …) are added here as the features that use them are built.

**Spec:** REQUIREMENTS.md → "Secrets & config".

**Status:** implemented.
