# `bots/` — Bot definitions

Loads bots from the database and validates every row against `BotDefinition` (see `contracts/`). A bot's identity and room-setup details live in `bots`; what it says and how it behaves lives in append-only `bot_versions`, and the loader always takes each bot's latest version.

**Owns:** the query for current bot versions, turning rows into validated definitions, and clear errors naming the bot and every problem when a stored definition is invalid.

**Does not own:** whether a user may start a call with these bots (`dispatch/`), or the schema (`supabase/migrations/`).

**Spec:** ARCHITECTURE.md → "Database schema"; [ADR 0007](../../../docs/adr/0007-bots-are-versioned-database-rows.md), [ADR 0008](../../../docs/adr/0008-models-per-role-belong-to-the-region-profile.md).

**Status:** implemented (S1.2).
