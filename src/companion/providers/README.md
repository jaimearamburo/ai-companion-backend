# `providers/` — Provider registry

The only place vendor details live. Everything else depends on the interfaces here, never on a vendor directly.

- **Interfaces** (`interfaces.py`): `ChatModel` (a streaming chat LLM with tool calls) and `SafetyClassifier`. Speech to text and text to speech get theirs with the voice pipeline, where LiveKit's plugin types are the natural boundary.
- **Fakes** (`fakes.py`): `FakeChatModel` replays scripted replies and records every request; `FakeSafetyClassifier` returns scripted verdicts, fails or runs slowly on demand. Tests, evals and the text CLI use them.
- **Preset catalogue** (`presets.toml`): every preset with its vendor, model, endpoint, the credential it needs and, for speech to text, whether it reports end of turn or emits preflight transcripts. These are candidates; each layer's vendor is chosen by comparing cost and measured latency (PLAN.md D22).
- **Region profiles** (`regions.toml`): the default preset for each live-call layer per region, a fallback for the scriptwriter and safety roles, the agent name and AWS region of the region's workers, and the AWS region of the shared services (Sydney for every region).
- **Rules** (`catalog.py`): both files are validated together when loaded, so an unknown preset, a preset of the wrong kind or an incompatible default fails at startup. `check_region_ready` requires the worker's profile keys; `resolve_providers` checks a call's chosen presets at session start (kinds, `stt_native` only with an STT that reports end of turn, every needed key set), resolves the `auto` trigger, and picks fallbacks from the profile.

**Does not own:** calling vendors (the adapters arrive with the shared client wrapper), or which presets a call asks for (the dispatch metadata).

**Spec:** ARCHITECTURE.md → "Pluggable providers", "Regions".

**Status:** interfaces, fakes, catalogue, region profiles and session rules implemented (S2.1); vendor adapters next (S2.2).
