# `scriptwriter/` — Scriptwriter

Builds the scriptwriter prompt (personas, cheat sheet, rolling buffer, transcript), calls the LLM, and parses its output into typed per-bot script segments with non-verbal tags and banter interrupt points. Also chooses which bot(s) speak (the "conductor" role).

**Owns:** the prompt, the typed script schema, the replacement for LiveKit's `llm_node`, and registering the `recall_memory` tool.

**Does not own:** the memory search itself (`memory/`), or turning script segments into audio (`audio/`).

**Spec:** ARCHITECTURE.md → "Full stack" (Scriptwriter LLM), "Memory".

**Status:** not yet implemented.
