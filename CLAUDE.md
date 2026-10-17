@REQUIREMENTS.md
@ARCHITECTURE.md
@PLAN.md
@docs/DESIGN_CHECKLIST.md
@docs/DEVELOPMENT.md

# Working rules for Claude Code

PLAN.md is the only plan for this repo; work through its steps in order, one batch at a time. The definition of done is docs/DESIGN_CHECKLIST.md, where every item has a stable ID (AR, VO, MT, SF, RL, EV, OB, EN, RG).

On every change:

1. Before coding, list the checklist IDs the change touches.
2. Design the change so it meets those items. If it would break or weaken any item, stop and explain why before proceeding.
3. After coding, run `make lint`, `make test` and `make eval` (once they exist) and report the results.
4. Finish with a short checklist report: IDs newly met (with evidence: file, test, ADR), IDs regressed, and open IDs this change makes easier.
5. Update the "Met by" lines under each affected ID in docs/DESIGN_CHECKLIST.md. Never renumber IDs.
6. Never mark an item met unless a test or runnable command proves it.
7. Commit only when the maintainer explicitly approves that specific commit, and never push unless asked. Each batch is one GitHub issue (ticket IDs like `S3.1` match PLAN.md steps); end it with a suggested commit message that starts with the ticket ID and checklist IDs, says why, and ends with `Closes #N`.
8. Comments explain intent and non-obvious decisions, not what the language or a library does.
9. Record each decision in PLAN.md section 3 before acting on it, and update ARCHITECTURE.md in the same batch so the two never disagree. ARCHITECTURE.md describes how the system works; PLAN.md holds decisions and the order of work. No other document describes future work.
10. Never commit anything under `docs/private/`.
