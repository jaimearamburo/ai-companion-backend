# `providers/` — Providers

The config-driven registry that maps preset names (e.g. `inworld_stt1`, `livekit_v1`) to actual LiveKit plugin instances with their auth, model and region parameters.

**Owns:** every vendor-specific detail in the codebase; preset compatibility rules (e.g. `stt_native` only with STTs that report end-of-turn); resolving the `auto` speculative-trigger preset.

**Rule:** no other module mentions a vendor by name. If you need Inworld- or Deepgram-specific behaviour elsewhere, it belongs here behind a preset.

**Spec:** ARCHITECTURE.md → "Design requirement: pluggable providers".

**Status:** not yet implemented.
