# 0007. Bot definitions are validated database rows with immutable versions

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** AR-01, AR-07, AR-08
- **Plan decisions:** D1, D32

## Context

Each bot has a persona, a voice, a model per role, a memory policy, allowed tools and safety rules. The frontend already reads the roster from the `bots` table. A release must pin exactly which bot definitions it runs, so that a rollback restores the same personas.

## Decision

Bot definitions stay in the database. Every row is validated by a strict typed model when it is loaded, and an invalid row stops the bot from loading with a clear error. Editing a bot creates a new immutable row in `bot_versions`; the old version is never changed. A release manifest pins bot version IDs.

## Alternatives considered

- **One configuration file per bot in the repository.** Rejected: the database is already the source the frontend reads, and two sources would drift.
- **Editable rows without versions.** Rejected: a release could not be rolled back to the exact persona it shipped with.

## Consequences

A migration adds the missing bot fields and the versions table. Tests feed malformed rows to the loader. Releases and rollback (AR-07) depend on version IDs.
