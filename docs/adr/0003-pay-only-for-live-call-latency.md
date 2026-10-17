# 0003. Pay only for live-call latency; run everything else on demand in Sydney

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** AR-09, RG-03, RG-04
- **Plan decisions:** D12, D21, D27, D35

## Context

Paid tiers can make a call faster, but most of the system is not on the live path: memory lookups (covered by a spoken filler), post-call memory extraction, embeddings, evals, tracing and CI. Running servers around the clock in two regions would cost money even with no calls.

## Decision

Paid services are considered only for the live-call layers: transport, worker compute, speech to text, turn detection, the scriptwriter and safety models, and text to speech. Everything else runs in Sydney on free or self-hosted options where possible, including the memory server, the database and the cache, for sessions from every region. Per-call state stays in the worker's memory, so nothing per turn crosses the Pacific. Servers start on demand, warmed up when the user opens the room-setup screen, and scale to zero after a set idle time.

## Alternatives considered

- **Paid tiers everywhere.** Rejected: spends money where a filler already hides the wait.
- **Duplicate memory and data in the US.** Rejected: adds cost and moves personal data abroad to save a wait the filler already covers.
- **Always-on servers.** Rejected: idle cost during development; a short wait on the first visit is acceptable.

## Consequences

US calls pay one cross-Pacific round trip per memory lookup and at call start. The first call after an idle period may wait for servers to start. Cost per conversation must be reported (OB-02) so the rule can be checked against real spend. The list of paid services and the latency each buys is added to this record as vendors are chosen.
