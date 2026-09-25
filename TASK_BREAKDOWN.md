# Voice Companion Backend — Task Breakdown

**Stack:** Python 3.13, LiveKit Agents (self-hosted, AWS Sydney), Inworld STT/TTS, Groq (GPT-OSS-20B scriptwriter, Safeguard-20B safety), Redis, Supabase Postgres + pgvector (Sydney), self-hosted embedding model. Full spec: [ARCHITECTURE.md](ARCHITECTURE.md).

Tasks are grouped into phases and roughly ordered by dependency. Each subtask is numbered `phase.subtask` (e.g. `6.3`) as a local reference ID for this document only. Tasks marked **(frontend)** need a matching change in the frontend repo — relay those across. Tasks marked **(decision)** need your call before work starts.

**Commit messages:** if these tasks are tracked as GitHub Issues, the issue numbers will not match the `phase.subtask` IDs here. Look up (or ask for) the real issue number before writing `closes #N`; the `phase.subtask` ID can still appear in the message text.

**Definition of done** (from REQUIREMENTS.md): tested, handles its failure modes (timeouts, fail-closed where relevant), `mypy --strict` clean, module README current, and anything unverified stated plainly.

---

## Phase 0 — Project Setup & Foundations
- [x] **0.1** Create the project structure: `pyproject.toml`, `src/companion/` module packages with READMEs, `tests/`, `supabase/migrations/`, CI workflow, `.env.example`, `.gitignore`
- [x] **0.2** Install uv; run `uv sync` to generate `uv.lock`; confirm lint, format, type check and tests all pass locally
- [x] **0.3** Initialise Git and make the first commit (manual)
- [x] **0.4** Push to GitHub; confirm the CI workflow runs green
- [ ] **0.5** Create `.env` with real credentials: LiveKit Cloud (AU project), Inworld, Groq, Redis (Sydney), Supabase DB connection string
- [x] **0.6** ~~Install the Supabase CLI and link it to the Sydney Supabase project~~ — **Not needed:** migrations are applied manually in the Supabase dashboard SQL editor
- [ ] **0.7** `config/`: typed settings object loaded from env vars, failing fast on missing values; tests
- [ ] **0.8** `observability/`: structured JSON logging with session/turn/preset context; tests

## Phase 1 — Database Schema
*(Schema changes go into ARCHITECTURE.md's Database schema section first, then become a migration file here. Each migration file is transaction-wrapped and applied **manually** by pasting it into the Supabase dashboard SQL editor, in file order. After each applied migration, the frontend must regenerate Supabase types.)*
- [x] **1.1** ~~Choose the Auth.js database adapter~~ — **Decided:** custom adapter in the frontend on `supabase-js`, snake_case tables, no ORM (see ARCHITECTURE.md → Database schema → Auth tables)
- [ ] **1.2** `users` + `accounts` migration from the ARCHITECTURE.md draft (including the `updated_at` trigger and RLS) — once applied, tell the frontend so it can regenerate types and build its Auth.js adapter
- [ ] **1.3** Design and document `bots` (roster), `sessions` (calls: bots present, presets used, start/end), `messages` (transcripts, heard text per speaker)
- [ ] **1.4** `memories` + `memory_witnesses` migration (hash-partitioned by user, `halfvec`), per the draft in ARCHITECTURE.md
- [ ] **1.5** RLS: enable on every table; define policies (memories and transcripts are backend-only)
- [x] **1.6** ~~How to test migrations before they touch the real database~~ — **Decided:** applied directly to the Sydney project while it holds no real data; revisit a separate test database before real users use it
- [ ] **1.7** Run each migration manually in the Supabase SQL editor (Jaime); **(frontend)** regenerate types
- [ ] **1.8** Seed data: the bot roster, an admin user
- [ ] **1.9** Benchmark exact vector search on a realistic per-user history size (confirms "no HNSW" decision)

## Phase 2 — Multi-bot Routing Prototype (de-risking spike)
*(Throwaway prototype code, kept outside `src/`. Answers whether one `AgentSession` can drive per-bot tracks before the real pipeline is built on that assumption.)*
- [ ] **2.1** Minimal worker joins a LiveKit Cloud room and speaks a fixed line through Inworld TTS
- [ ] **2.2** Verify an audio frame's `userdata` tag survives from the TTS step to a custom audio output
- [ ] **2.3** Custom audio output publishes one track per bot (`bot:<bot_id>`), two voices
- [ ] **2.4** Barge-in: user speaking stops all bot tracks
- [ ] **2.5** Send `bot_speaking` data messages from the router
- [ ] **2.6** Write up findings; update ARCHITECTURE.md ("pending prototype" → confirmed or redesigned)

## Phase 3 — Dispatch & Provider Registry
- [ ] **3.1** `dispatch/`: typed dispatch-metadata model and validation; tests
- [ ] **3.2** Bot-count check against the user's role (max 2 for regular users); tests
- [ ] **3.3** `providers/`: registry mapping preset names to STT, TTS and LLM instances; tests
- [ ] **3.4** Turn-detector presets (`livekit_v1`, `livekit_v1_mini`, `stt_native`)
- [ ] **3.5** Compatibility rules and `auto` speculative-trigger resolution; tests
- [ ] **3.6** **(frontend)** Confirm the final preset list and dispatch-metadata shape; update ARCHITECTURE.md → Frontend contract

## Phase 4 — Core Voice Pipeline (single bot)
- [ ] **4.1** `pipeline/`: build an `AgentSession` for a call from dispatch metadata + registry
- [ ] **4.2** `scriptwriter/`: typed script output schema (speaker, segments, tags)
- [ ] **4.3** Scriptwriter `llm_node` for one bot, persona prompt, output parsed into the schema
- [ ] **4.4** Filler audio cache and playback at turn commit
- [ ] **4.5** End-to-end call from the frontend or LiveKit playground
- [ ] **4.6** Measure baseline latency (turn commit → first audible sound) from Sydney

## Phase 5 — Safety Gate
- [ ] **5.1** Safety classifier call with timeout, through the registry
- [ ] **5.2** Verdict parsing; fail closed on error, timeout or unparseable output
- [ ] **5.3** Pre-cached disclaimer audio
- [ ] **5.4** Gate at turn commit: release script vs. play disclaimer
- [ ] **5.5** Tests covering timeouts, garbage responses and slow verdicts

## Phase 6 — Turn-taking & Speculative Bets
- [ ] **6.1** Measure Inworld STT from Sydney: round-trip latency and interim-result cadence (vs Deepgram Nova-3 / Flux) — decides whether Inworld stays
- [ ] **6.2** Bet manager: one bet in flight, cancel on text change (including stopping the Groq stream), cap 3 per turn + 10s cut-off
- [ ] **6.3** `transcript_rules` strategy with per-language word rules (English, Mandarin, Spanish); tests
- [ ] **6.4** `transcript_debounce_only` and `vad_silence` strategies; tests
- [ ] **6.5** `livekit_preemptive` integration
- [ ] **6.6** "Commit wins the race" path: commit triggers generation when no bet is usable
- [ ] **6.7** Per-turn metrics: bets fired/wasted, bet-to-commit time
- [ ] **6.8** Compare turn detectors from Sydney: `livekit_v1` vs `livekit_v1_mini` vs `stt_native`; confirm v1 pricing for self-hosted agents
- [ ] **6.9** Tune debounce window and endpointing delays on real users' speech

## Phase 7 — Memory: Reading During a Call
- [ ] **7.1** **(decision)** Choose the embedding model after a CPU latency benchmark on the target instance type
- [ ] **7.2** `memory/` embeddings: self-hosted model loaded once per worker; tests
- [ ] **7.3** Memory repository: SQL queries, persistent connection pool, timeouts; tests
- [ ] **7.4** Cheat sheet: built at call start from top-importance facts + recent summaries, per witnessing bot; held in Redis
- [ ] **7.5** `recall_memory` tool: own-memories scope by default; other bot's memories only after the user agrees; `max_tool_steps=1`
- [ ] **7.6** "Thinking" filler when a lookup is still pending at turn commit
- [ ] **7.7** Skip re-running safety on the tool's second LLM request
- [ ] **7.8** Tier 3 rolling buffer (10–15 messages)
- [ ] **7.9** Tests: scoping rules, consent flow, over-call limits

## Phase 8 — Memory: Writing After a Call
- [ ] **8.1** Persist transcripts to `messages` (what was actually heard, including interrupted bot lines)
- [ ] **8.2** **(decision)** Choose the extraction LLM
- [ ] **8.3** Extraction prompt + typed output schema (fact, category, occurred date, importance)
- [ ] **8.4** Deduplication: ADD / UPDATE (superseded_by) / SKIP against existing facts
- [ ] **8.5** Embed and store facts with witness rows; store the session summary
- [ ] **8.6** Trigger at call end; idempotent per session; retries
- [ ] **8.7** **(decision)** Where the job runs (in the worker vs a separate queue)
- [ ] **8.8** Tests against recorded transcripts

## Phase 9 — Multi-bot & Banter
- [ ] **9.1** Production per-bot audio router (from the Phase 2 prototype)
- [ ] **9.2** Scriptwriter chooses speaker(s) across bots (conductor role); multi-persona prompt
- [ ] **9.3** Parallel per-bot TTS with each bot's voice
- [ ] **9.4** Banter scheduler: pre-synthesised interrupt audio, triggered by playback position
- [ ] **9.5** `bot_fade` data message; **(frontend)** GainNode fade
- [ ] **9.6** Barge-in during an overlap stops all bots
- [ ] **9.7** N-bot rooms for admins
- [ ] **9.8** Tune the 350ms fade by ear
- [ ] **9.9** Optional: per-bot captions; **(frontend)** caption display

## Phase 10 — Resilience & Quality
- [ ] **10.1** Audit every vendor call: timeout, failure path, retry only where idempotent
- [ ] **10.2** Integration tests: full pipeline against recorded vendor responses
- [ ] **10.3** Load test: concurrent calls per worker, Groq rate limits under speculative-bet load
- [ ] **10.4** Cost check: measured cost per minute vs the ARCHITECTURE.md model (wasted bets, recall turns, extraction)

## Phase 11 — Deployment (AWS Sydney)
- [ ] **11.1** Dockerfile; CI builds the image
- [ ] **11.2** **(decision)** ECS on Fargate vs ECS on EC2 (depends on v1-mini/embedding CPU benchmarks)
- [ ] **11.3** Secrets in AWS Secrets Manager
- [ ] **11.4** ECS service in ap-southeast-2: minimum warm workers, autoscaling, rolling deploys that don't cut live calls
- [ ] **11.5** Move Supabase to a paid tier before real users use it
- [ ] **11.6** Add a Deployment section to ARCHITECTURE.md
- [ ] **11.7** Privacy review by an Australian privacy lawyer (health data, emotional triggers, indefinite transcripts) before launch

## Phase 12 — Documentation
- [ ] **12.1** Keep module READMEs current (ongoing, part of every task)
- [ ] **12.2** Final root README: overview, architecture decisions, local setup, how the two repos connect
- [ ] **12.3** Final pass syncing ARCHITECTURE.md with what was actually built

---

## Misc — Unlisted Tasks
*For tracking work that doesn't fit a phase above. Add entries as `M.n`.*

- [x] **M.1** Proprietary `LICENSE` (all rights reserved) and README license section
- [x] **M.2** Audience-neutral wording across all committed files; audience context moved to a private, git-ignored file
- [x] **M.3** Test coverage reporting (`pytest-cov`, branch coverage, no enforced minimum)
- [x] **M.4** Rename `session/` module to `pipeline/`; remove `py.typed`
- [ ] **M.5** Update CI actions to Node 24 versions; skip CI for docs-only changes — awaiting commit, push and a green run
