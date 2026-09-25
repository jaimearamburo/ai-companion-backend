# `config/` — Config

Loads every setting the backend needs (API keys, URLs, tunable thresholds) from environment variables into one typed, validated settings object.

**Owns:** reading and validating configuration at startup; failing fast with a clear error if a required variable is missing.

**Does not own:** vendor-specific provider settings (those live in `providers/`), or per-call choices (those arrive in dispatch metadata, see `dispatch/`).

**Spec:** REQUIREMENTS.md → "Secrets & config".

**Status:** not yet implemented.
