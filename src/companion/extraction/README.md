# `extraction/` — Extraction

Runs after each call ends: reads the transcript, asks a cheap LLM for atomic core facts (with importance scores) and a session summary, deduplicates against existing facts (ADD / UPDATE / SKIP), embeds them and stores them with their witness bots.

**Owns:** the extraction prompt and its typed output schema, deduplication, and making the job safe to retry (idempotent per session).

**Spec:** ARCHITECTURE.md → "Memory" → "Writing memory: post-call extraction".

**Status:** not yet implemented.
