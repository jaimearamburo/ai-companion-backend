# 0008. Models per role belong to the region profile; bots have a voice per TTS preset

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** AR-01, AR-04, RG-01
- **Plan decisions:** D40
- **Amends:** [0007](0007-bots-are-versioned-database-rows.md)

## Context

[ADR 0007](0007-bots-are-versioned-database-rows.md) listed "a model per role" among a bot's fields. One scriptwriter request voices every bot in the call, so bots in the same call can't use different scriptwriter or safety models. Text to speech differs: each bot has its own voice, and each TTS vendor has its own voice IDs, while the TTS vendor is chosen per region.

## Decision

A bot definition carries a voice per TTS preset (for example `fish_s21_hosted` → a Fish voice ID), not a model per role. The scriptwriter, safety and extraction models are set in the region profile and pinned by the release manifest.

## Alternatives considered

- **A model per role on each bot.** Rejected: one request can only use one model, so per-bot models would conflict whenever two bots share a call.
- **A single voice ID per bot.** Rejected: voice IDs are vendor-specific, and the TTS vendor can differ by region.

## Consequences

The bots migration stores voices as a map from TTS preset to voice ID. A region profile can only use a TTS preset that every active bot has a voice for; startup checks this.
