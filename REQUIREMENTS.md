# Project: Voice Companion — Backend (LiveKit Agents, Python)

This is the **backend repo**. It owns the real-time voice pipeline: LiveKit Agents worker, provider registry (STT/TTS/LLM), safety gate, memory tiers, bot-to-bot interruption scheduling, and the Supabase database schema.

This file is standing context for every Claude Code session in this repo. Read it in full before writing any code. `ARCHITECTURE.md` in this same directory is the source-of-truth spec — read that too before touching the pipeline, and treat anything here that conflicts with it as a bug in this file, not in the spec.

There is a **separate `frontend` repo** (Next.js/TypeScript — room-setup UI, dropdowns for provider presets, calling this backend's agent-dispatch API). You will not see that repo's code from here. It shares this repo's `ARCHITECTURE.md` (kept in sync manually — flag it to me if something you're building here seems to require a frontend change I haven't mentioned) and it shares the same Supabase database — see the Database schema section below and in `ARCHITECTURE.md` for exactly how that split works.

## What this is

A real-time voice companion app: one user talking with 1 or 2 AI bot companions. **Group size is user-chosen, not fixed:** the user picks 1 or 2 bots from a predefined roster via a room-setup UI (built in the frontend repo) before starting the call. A user + 1 bot (1-to-1) is a supported, intentional mode — it is not a minimum-2 system. 2 bots is the maximum for regular users; admin users (developers) can add any number for testing. Write the pipeline generically over N bots — never hardcode 2 — and re-check the limit against the user's role at session start. Figures in `ARCHITECTURE.md` that assume plural "bots" (cost model, token budgets) are sized for 2 bots.

Targets: the first audible sound within 300ms of the user's turn ending (p50; 500ms at p95), the first word of the real reply within 1.0s (p50; 1.2s at p95), measured from each region, and under 3¢ per call-minute. Built for Australia first, with US infrastructure for users in the Americas and Europe. The design, cost model, sequence diagram and reasoning are in `ARCHITECTURE.md`; decisions are in PLAN.md section 3 and `docs/adr/`. Don't re-derive decisions already made; if you think one is wrong, say so and stop, don't silently change it.

Stack summary (ARCHITECTURE.md is authoritative if this drifts):
- Transport: LiveKit Cloud, unpinned; each user reaches the nearest edge (`aus` or `us`)
- Orchestration: LiveKit Agents plus our agent runtime (`CompanionAgent`), Python, self-hosted in AWS Sydney and the US, started on demand — **this repo**
- Tools: a standalone MCP server in Sydney holds the memory and reminder tools and enforces user scoping
- Vendors: none is fixed for any layer; each is chosen by measured latency from both regions when that layer is built
- Safety: a separate safety model screens user input in parallel with the draft and fails closed; bot-output screening is pluggable and off
- Memory: cheat sheet loaded from the MCP server at call start and held in the worker; Postgres + pgvector in Sydney searched on demand via `recall_memory`; rolling buffer; post-call extraction job
- Scriptwriter LLM: one pass, reasoning always on, chooses which bot speaks and writes every bot's lines, within hard limits checked in code
- Multi-bot output: one AgentSession, one agent participant, one audio track per bot — pending prototype
- Frontend: Next.js/TypeScript — **other repo**, not built here
## Database schema — this repo owns it

Per `ARCHITECTURE.md`'s "Database schema" section: the actual Supabase Postgres schema and its migrations live in and are applied from **this repo**, at `supabase/migrations/`, even though the frontend repo also reads/writes this same database (user accounts, room/session history, anything user-facing). This backend uses it for Tier 2 pgvector memory and anything pipeline-internal.

We use standard Python PostgreSQL tools to read our tables and vectors.

Concretely:
- `supabase/migrations/` here is the single source of truth. Never apply a schema change from anywhere else. Migrations are applied manually in the Supabase SQL editor; CI first applies them all to a throwaway Postgres and runs behavioural checks (`supabase/ci/`) — see `supabase/README.md`.
- After any schema change, regenerate and note that the frontend needs `supabase gen types typescript` re-run on its side — tell me explicitly when this happens so I can pass it along, since I can't push that update into the frontend repo myself.
- If a frontend need surfaces a table/column that doesn't exist yet (I'll relay this from the other repo's Claude Code session, or the developer will tell you directly), draft the migration here — don't assume the shape, ask if it's not obvious from `ARCHITECTURE.md`.
- Users, accounts, bots and bot versions, sessions, messages and user–bot relationships are migrated; the memory and reminder tables are designed in `ARCHITECTURE.md`'s Database schema section. Schema changes go into that section first, then become a migration here.
## How I want you to work

1. **Read `ARCHITECTURE.md` and this file before writing code in a new session.** Don't start from assumptions about what the stack is — the spec has already resolved a lot of vendor/design tradeoffs with sourced reasoning. If something in the spec looks wrong or has gone stale, flag it to me in your response rather than quietly working around it.
2. **I am supervising, not pair-programming in real time.** I will often be away or working on something else. Write code for a defined task, then stop and summarize what you did and what's left — don't keep going into adjacent work I didn't ask for.
3. **Ask when you need something from me, don't guess and move on.** Stop and ask explicitly when:
   - You need a real credential/API key/secret that isn't in the environment (never invent a placeholder and silently continue as if it works — stub it clearly and tell me).
   - A product or UX decision isn't settled in the spec (e.g. "should bot-to-bot interruption be allowed during a safety-sensitive topic?" — that's my call, not yours).
   - Two parts of the spec appear to conflict, or a number/assumption looks wrong.
   - You're about to do something expensive, destructive, or hard to reverse (schema migration on real data, deleting anything, a paid API call at volume).
   - A vendor claim you're building against turns out to be unconfirmed or wrong once you actually check it (region availability, a rate limit, an SDK method that doesn't exist) — tell me, don't paper over it.
   - A change here would require something from the frontend repo (a new API contract, a dispatch-metadata field, a type regeneration) — tell me explicitly what the other repo needs, since I move that context across manually.
4. **Don't mark something done if it isn't.** If tests are failing, if you had to stub something out, if you're not sure an integration actually works end-to-end — say so plainly. I'd rather hear "this compiles but I haven't verified it against the real API" than a confident "done."
## Engineering bar: production/enterprise-grade from the first commit

This code will be shown to potential buyers, so treat code quality as part of the product from day one, not something to clean up later. Concretely, that means:

**Structure & types**
- Python: type hints everywhere, `mypy --strict` clean. No bare `dict`/`Any` where a `TypedDict`, `dataclass`, or `pydantic` model would do — especially for the LLM script schema, provider registry configs, dispatch metadata parsing, and anything crossing a network boundary.
- Module boundaries follow the architecture: the provider registry (STT/TTS/LLM swapping), the pipeline orchestration, memory tiers, the safety gate, and the interruption scheduler are separate, independently testable units — not one large agent file.
**Error handling — this matters more than usual here**
This system's hot path depends on several external vendor APIs (LiveKit, STT, TTS, the scriptwriter and safety LLM hosts, the MCP server and its database) that will occasionally be slow, rate-limited, or down. Handle that as a first-class concern, not an afterthought:
- Every external call gets a timeout and an explicit failure path — never let one slow vendor call hang the turn indefinitely.
- The safety gate fails closed: if the safety check errors, times out, or returns something unparseable, treat it as "unclear" and play the safe disclaimer — never silently fall through to the real script on an ambiguous or failed safety result.
- Retries where they make sense (idempotent reads), not where they don't (don't retry a TTS call that partially streamed audio).
- Structured logging (not `print`), with enough context (session id, turn id, which provider preset was active) to reconstruct what happened in a failed call after the fact.
**Testing**
- Unit tests for anything with real logic: the transcript-stabilization rule layer, the provider registry resolution, the cost/latency-sensitive scheduling code for bot interruptions.
- Integration tests that exercise the pipeline against recorded/mocked vendor responses, not just happy-path unit tests.
- Don't chase 100% coverage on glue code; do cover anything that decides behavior (safety gating, turn-taking, provider selection, interrupt scheduling).
**Secrets & config**
- No credentials in code, ever, including "temporary" hardcoding while testing. Env vars locally, a real secrets manager in any deployed environment.
- The provider-preset registry (see ARCHITECTURE.md's "Pluggable providers") is the only place vendor config lives — no STT/TTS/LLM vendor specifics leaking into orchestration logic.
**Process**
- Small, reviewable commits with messages that say *why*, not just *what*.
- Lint + type-check + test as a CI gate before anything merges, even solo — set this up early, not after there's a backlog of violations.
- README per major module explaining what it owns and why, kept current as you go — not written retroactively.
## What "done" looks like for a task

Not "it runs once on my machine." A task is done when: it has tests, it handles the failure modes above, it's typed, and you've told me plainly what you didn't get to or couldn't verify.
