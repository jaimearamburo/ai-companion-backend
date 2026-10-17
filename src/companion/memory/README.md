# `memory/` — Memory

Everything about reading the user's memories during a call.

**Owns:** building the profile cheat sheet at call start (served through the MCP server and held in the worker for the call), the `recall_memory` search (scoped to the bots that witnessed each memory; other bots' memories only after the user agrees), the self-hosted embedding model, the rolling buffer, and the SQL queries for memory tables.

**Does not own:** creating new memories after a call (`extraction/`).

**Spec:** ARCHITECTURE.md → "Memory", "Database schema".

**Status:** not yet implemented.
