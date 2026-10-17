# `dispatch/` — Dispatch

Turns the JSON the frontend sends at call start (`ctx.job.metadata`) into a validated, typed object: user's id, selected bots, and preset names.

**Owns:** the backend side of the dispatch-metadata contract; rejecting malformed metadata; the bot-count check against the user's role (max 2 for regular users).

**Does not own:** resolving preset names into real providers (`providers/`).

**Spec:** ARCHITECTURE.md → "Frontend contract", "Pluggable providers".

**Status:** not yet implemented.
