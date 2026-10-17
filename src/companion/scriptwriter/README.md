# `scriptwriter/` — Scriptwriter

Builds the scriptwriter prompt (personas, cheat sheet, rolling buffer, transcript), calls the LLM, and parses its output into typed per-bot script segments with non-verbal tags and banter interrupt points. Also chooses which bot(s) speak (the "conductor" role).

**Owns:** the prompt, the typed script schema, and the hard limits on which bot may speak. Tool calls go through the agent runtime's tool loop to the MCP server.

**Does not own:** the memory search itself (`memory/`), or turning script segments into audio (`audio/`).

**Spec:** ARCHITECTURE.md → "Layers" (Scriptwriter LLM), "Memory".

**Status:** not yet implemented.
