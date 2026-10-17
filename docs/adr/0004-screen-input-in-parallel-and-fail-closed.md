# 0004. Screen user input in parallel with the draft, and fail closed

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** SF-01, SF-02, SF-03, SF-04 (retired), AR-05
- **Plan decisions:** D7, D14, D29

## Context

A separate safety model must check what users say so that self-harm and medical-advice requests get a safe, fixed response. A network call to a safety model takes tens to hundreds of milliseconds, which would add directly to response time if it ran in front of the reply.

## Decision

The safety model screens each user turn in parallel with the speculative reply draft; the verdict only has to arrive before the user's turn is committed. If the check errors, times out or returns something unparseable, the result is treated as unsafe and approved fixed text is spoken instead of the draft. Screening of the bots' own replies is built as a stage that can be switched on by configuration but is off by default, to protect latency. There is no second, supervisor check on sensitive turns.

## Alternatives considered

- **Screen before drafting.** Rejected: adds the full safety round trip to every turn.
- **Screen every bot sentence now.** Deferred: adds latency on every reply; the pluggable stage keeps the option open.
- **A supervisor model on distress, health and money turns.** Rejected for now: a second model call on the slowest, most sensitive turns.

## Consequences

Tests must force a safety timeout, a garbage verdict and a slow verdict, and check that the exact fixed text is spoken. A category-to-action table is written when the gate is built. Bot replies are not independently screened until the output stage is switched on.
