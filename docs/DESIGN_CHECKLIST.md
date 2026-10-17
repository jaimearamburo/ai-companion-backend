# Design Checklist: Voice-First Multi-Bot Companion

This file is the project's definition of done. Every item has a permanent ID, a requirement, and the evidence that proves it. When the project is finished, every box is ticked and every item points to code, a test or a decision record (ADR).

## How to use this checklist

- **IDs never change.** Add new items at the end of a section; retire old ones with a note rather than renumbering.
- **Evidence lives in the repo.** Under each ID, add a `Met by:` line linking the module, test and ADR that satisfy it.
- **Commits and pull requests start with IDs** (for example, `MT-05: validate tool arguments`), so the history shows when each item was met. The maintainer makes every commit by hand.
- The standing rules for Claude Code live in `CLAUDE.md` at the repo root.

## Background: practices this checklist adapts

| Practice | What it means in this project |
| --- | --- |
| Declarative goals + deterministic guardrails | Bots declare what they are for; hard rules the LLM cannot cross are enforced in code |
| Composable skills | Behaviour is built from reusable, separately tested pieces with deterministic API interactions |
| Selective LLM bypass | Fixed, approved text for wording that must never vary |
| Immutable releases | Each release snapshots code, prompts, bot versions and model IDs; rollback is instant |
| Conversations become regression tests | Logged conversations are replayed against mocked tools before every release |
| End-state scoring + pass^k | Simulated conversations are scored on the resulting state, not the wording; pass^k is success on all k repeat runs |
| Voice under realistic audio | Evals add noise, accents, phone-quality compression and interruptions |
| Fast + slow voice | A real-time layer keeps talking while slower reasoning or lookups finish |
| Memory that compounds | Each conversation adds to what the bots know, with corrections replacing old facts |
| Spend follows latency | Paid services only for the live-call layers; everything else in one home region on free or self-hosted options |

## AR: Architecture and configuration

- [ ] **AR-01 Bots are data, not code.** Each bot is one row in the `bots` table: persona, a voice per TTS preset, memory policy, allowed tools and safety settings. Models per role belong to the region profile, because one scriptwriter request voices every bot in the call. Every row is validated by a strict model when it is loaded, and a change creates a new immutable bot version instead of editing the old one. *Evidence:* adding a bot requires only a new row; an invalid row fails loudly with a clear error.
- [ ] **AR-02 Swappable pipeline stages.** STT, safety, LLM, tools, memory and TTS sit behind typed interfaces, so a provider change is a new adapter plus config. *Evidence:* a second implementation of at least one stage (for example, a fake LLM used in tests).
- [ ] **AR-03 Deterministic prompt assembly.** One prompt builder combines persona, rules, hot memory, retrieved memories and recent turns, in a fixed, documented order with a token budget per part. *Evidence:* snapshot tests of assembled prompts.
- [ ] **AR-04 The right model for each job.** Conversation, safety screening, memory extraction and summarisation each have a configured model, chosen for speed or depth. *Evidence:* an ADR explaining each choice, and cost per conversation by model.
- [ ] **AR-05 Fixed wording where it matters.** Moments that must never vary (crisis responses with helpline details, refusals, consent prompts) bypass the LLM and use approved text. *Evidence:* tests showing the exact text is spoken.
- [ ] **AR-06 Explicit multi-bot rules.** The scriptwriter LLM chooses which bot speaks and writes its lines, seeing every bot's persona and memories. Code enforces the hard limits around that choice (only bots in the call, how many may speak in a turn, when banter is allowed) and rejects any reply that breaks them. *Evidence:* unit tests for the limits and the validator, and eval scenarios that check who spoke.
- [ ] **AR-07 Versioned releases.** A release manifest pins bot versions, prompt templates, model IDs and the embedding model; any release can be rolled back with one command and two releases can run side by side for comparison. *Evidence:* `make release` and `make rollback`, plus eval results per release.
- [ ] **AR-08 Typed boundaries with Pydantic v2.** Every interface uses a Pydantic v2 model: configs, tool inputs and outputs, memory records, bot-to-bot messages, eval scenarios and results. Data is validated at the edge, before it touches a database or a model call, and bad data fails with a clear error. *Evidence:* strict-mode models and tests that feed malformed payloads.
- [ ] **AR-09 Spend follows latency.** Paid services are considered only for the live-call layers: transport, worker compute, speech to text, turn detection, the scriptwriter and safety LLMs, and text to speech. Everything else lives in Sydney on free or self-hosted options where possible: the MCP server and memory lookups (a filler masks their latency), the database and vector search, the cache, embeddings, post-call extraction, evals, tracing and CI. Servers start on demand and scale to zero when no calls are active. *Evidence:* an ADR listing each paid service and the latency it buys, and cost per conversation in OB-02.

## VO: Voice pipeline

- [ ] **VO-01 A written latency budget.** Targets measured from each region: first audible sound (the filler) within 300 ms of turn commit at p50 and 500 ms at p95; first word of the real reply within 1.0 s at p50 and 1.2 s at p95. A budget per stage is derived from these and measured on every eval run. *Evidence:* the latency report in OB-02.
- [ ] **VO-02 Streaming end to end.** Partial transcripts, streamed LLM tokens, and TTS that starts on the first complete sentence. *Evidence:* a trace showing stages overlapping.
- [ ] **VO-03 Fast path during slow work.** When the bot decides to fetch deep memories, it says something natural straight away ("let me think back...") while the lookup runs. *Evidence:* a test where a slow memory lookup still produces audio within budget.
- [ ] **VO-04 Clean interruptions.** When the user talks over the bot, audio stops at once and the history keeps only what was actually spoken. *Evidence:* a simulated interruption test checking the stored transcript.
- [ ] **VO-05 Tuned turn-taking.** End-of-turn detection is tuned, and short backchannels ("mm-hm", "yeah") don't trigger a new reply. *Evidence:* simulation results with backchannels.
- [ ] **VO-06 Speech-ready text.** Numbers, dates, times and abbreviations are normalised before TTS, and spoken replies stay short. *Evidence:* unit tests for the normaliser.
- [ ] **VO-07 Uncertain speech is confirmed.** Low-confidence transcripts of important details (names, dates, places) are confirmed or re-asked before being stored as memories. *Evidence:* a test where a misheard name is corrected before it is saved.
- [ ] **VO-08 Orchestration overhead is measured.** Our own code between vendor calls (prompt assembly, speaker checks, the tool loop, the MCP hop, validation) adds under 10 ms p95 per turn, excluding time spent waiting on vendors and on the tool's own work. *Evidence:* a benchmark test that fails above the budget, and the per-stage spans in OB-01.

## MT: Memory and tool calling

- [ ] **MT-01 Documented memory tiers.** Hot memory (cached, always in the prompt) and deep memory (vector DB, fetched by tool) have written rules for what goes where and when items move between tiers. *Evidence:* an ADR plus tests of promotion and demotion.
- [ ] **MT-02 Typed memory records.** Every memory stores content, type (fact, preference, event), user, bot, source conversation, timestamp and confidence. *Evidence:* a Pydantic model and database schema.
- [ ] **MT-03 Safe memory writes.** Extraction after each conversation, de-duplication, and conflict handling where a newer fact supersedes an older one instead of both being kept. *Evidence:* tests for duplicate and contradicting facts.
- [ ] **MT-04 Measured retrieval.** Retrieval quality is tested against seeded memories (does the right memory come back in the top results?). *Evidence:* a retrieval score in the eval report.
- [ ] **MT-05 Strict tool contracts.** Each tool has a JSON schema; arguments are validated before execution, and invalid calls return a structured error the model can recover from. *Evidence:* tests with malformed tool calls.
- [ ] **MT-06 Bounded tool loops.** A maximum number of tool calls per turn, a timeout per call, and a graceful answer when either limit is hit. *Evidence:* tests that force each limit.
- [ ] **MT-07 Scoping enforced by the server.** The model never supplies user or bot IDs; the server injects them into every memory query, so one user's memories can never leak to another. *Evidence:* a test where the model asks for another user's data and gets nothing.
- [ ] **MT-08 Memories are data, not instructions.** Retrieved memories are clearly delimited in the prompt and can't override rules, even if a stored memory contains instruction-like text. *Evidence:* an injection test using a poisoned memory.
- [ ] **MT-09 User control over memory.** "What do you remember about me" returns a brief LLM-written summary, limited to the user's own active memories that the speaking bot may see. When the call's memory-deletion setting is switched on before the call, "forget that" deactivates specific memories (`is_active = false`), which removes them from every read path; there is no voice command to forget everything, and deleting the account still removes all of the user's data. The retention policy is documented (currently unlimited). *Evidence:* tests proving a deactivated memory never reaches the cheat sheet or recall, and that deletion is refused when the setting is off.
- [ ] **MT-10 Provider-neutral tools.** Tools are defined once, on the MCP server (MT-11), and an adapter translates their schemas into the LLM provider's tool-calling format (whichever host is chosen), so changing model provider doesn't mean rewriting tools. *Evidence:* the adapter and its tests.
- [ ] **MT-11 Tools served over MCP.** Memory tools (for example, `recall_memory`) and any bot actions run on a standalone MCP server. The orchestrator is an MCP client: it discovers tools once at startup, runs the tool loop itself, and calls tools with standard JSON payloads. LiveKit carries the audio and calls into the orchestrator; it does not run the tool loop. Use stdio for local development and tests, and Streamable HTTP for deployed servers, with one long-running server beside each memory database shared by all calls (the older HTTP+SSE transport is deprecated). The library (the official MCP Python SDK or standalone FastMCP) is chosen and pinned in an ADR. *Evidence:* the server, a discovery test, and a test proving user scoping (MT-07) holds across the MCP boundary.
- [ ] **MT-12 A clear embedding and indexing pipeline.** Chunking and embedding are separate from search. The embedding model is pinned and recorded in the release manifest (AR-07), with a re-embedding script for when it changes. The vector store sits behind an interface; the default implementation is pgvector in the existing Postgres database, and another store (for example, Qdrant or Chroma) can be added as a second implementation without changing callers. Memories are stored in the user's home region (RG-04). *Evidence:* the pipeline modules, the interface with at least an in-memory test implementation and the pgvector implementation, the re-embed script and the retrieval score from MT-04.
- [ ] **MT-13 Actions under policy.** Bot actions that change stored state (first: reminders) run as MCP tools with written policies enforced in code: details are read back and confirmed before saving, dates are resolved in the user's time zone, and past dates are rejected. *Evidence:* tests for each policy and eval scenarios scored on the reminders that exist afterwards.

## SF: Safety

- [ ] **SF-01 Every user input is screened; output screening is pluggable.** The separate safety model checks each user turn, with a documented action per category (block, rephrase, or switch to fixed text from AR-05). Screening of bot replies is a stage that can be switched on by configuration; it is off by default to protect latency. *Evidence:* a category-to-action table in an ADR, tests, and a test that plugs in a fake output screener.
- [ ] **SF-02 Fails closed.** If the safety model errors or times out, nothing unchecked is spoken; the bot uses a safe fallback line. *Evidence:* a test that forces a safety timeout.
- [ ] **SF-03 Streaming-aware screening.** Input screening runs in parallel with the draft, so it adds no latency; when output screening is switched on, it checks each sentence while TTS prepares it and holds the audio until the verdict. *Evidence:* an ADR on the trade-off and latency numbers with safety on.
- [x] ~~**SF-04 A supervisor for high-stakes turns.**~~ *Retired 2026-10-18:* no second safety check, to protect latency. The ID is kept so it is never reused.
- [ ] **SF-05 Prompt-injection resistance.** Users can't talk a bot out of its rules, and tool results and memories can't issue instructions. *Evidence:* the red-team set in EV-08.
- [ ] **SF-06 Personal data protection.** Personal details are redacted in logs and traces, and secrets never appear in prompts or logs. *Evidence:* a redaction test on sample logs.

## RL: Reliability

- [ ] **RL-01 Timeouts and retries everywhere.** Every external call (STT, LLM, safety model, vector DB, TTS) has a timeout and retries with backoff. *Evidence:* a shared client wrapper with tests.
- [ ] **RL-02 Provider fallback.** If the primary model is unavailable, a configured fallback takes over. *Evidence:* a test that simulates a provider outage.
- [ ] **RL-03 Graceful spoken errors.** Failures produce a natural spoken line, never silence or a stack trace. *Evidence:* tests per failure type.
- [ ] **RL-04 Safe repeats.** Memory writes are idempotent, so a retry or reconnect never stores the same memory twice, and a dropped connection can resume the conversation. *Evidence:* a reconnect test.
- [ ] **RL-05 Abuse limits.** A maximum call length set by the developer, enforced by the backend and shown to the user as a countdown. Per-user limits are deferred and can be added later as configuration. *Evidence:* a test for the call-length cut-off.
- [ ] **RL-06 Tested under load.** 20 or more simulated conversations run at once with latency and error rates reported. *Evidence:* the load-test report.

## EV: Evals and testing

- [ ] **EV-01 A simulated user.** An LLM plays the user from a script: persona, goals, facts to mention, and questions to ask later. *Evidence:* the simulator module and sample scripts.
- [ ] **EV-02 Scored by end state, not wording.** Each scenario checks verifiable outcomes: which memories exist afterwards, which tools were called with which arguments, and which safety actions fired. *Evidence:* 30 or more scenarios with expected end states.
- [ ] **EV-03 Reliability with pass^k.** Every scenario runs k times (k = 4 to start); the report shows pass^1 and pass^k per scenario and per bot. *Evidence:* the eval report.
- [ ] **EV-04 Multi-session recall.** Session one plants facts; a later session tests whether the bot recalls them correctly, including facts that changed in between. *Evidence:* recall accuracy in the report.
- [ ] **EV-05 A calibrated judge for soft qualities.** A judge model scores persona consistency, warmth and brevity against a written rubric, checked against 20 to 30 hand labels. *Evidence:* the rubric and the agreement rate.
- [ ] **EV-06 Failures become tests.** One command turns any logged conversation into a replayable regression test. *Evidence:* the command and the tests it has produced.
- [ ] **EV-07 Realistic audio.** Voice-mode runs with varied voices, background noise, phone-quality audio and interruptions, reported as clean versus realistic. *Evidence:* the side-by-side results.
- [ ] **EV-08 A red-team set.** Harmful requests, jailbreaks, injection attempts and poisoned memories, each with an expected outcome; the report shows block rate and false-alarm rate. *Evidence:* the set and its results.
- [ ] **EV-09 Evals gate every change.** CI runs a fast subset on each pull request and fails if pass^k drops below the last release. *Evidence:* the CI workflow and a PR comment showing scores.
- [ ] **EV-10 Text mode on the production path, run in parallel.** The orchestrator is transport-agnostic, so evals send text through exactly the code the voice path uses, minus audio. An asyncio runner executes scenarios in parallel with a concurrency limit, records model versions and seeds, and finishes the fast suite in minutes. *Evidence:* runner timings and a test proving voice and text share one orchestrator.

## OB: Observability

- [ ] **OB-01 One trace per conversation.** Spans for STT, each LLM call, each tool call (with arguments and results), safety verdicts, memory reads and writes, and TTS, using OpenTelemetry and a viewer such as Langfuse. *Evidence:* a screenshot of a full trace in the README.
- [ ] **OB-02 Latency and cost report.** p50 and p95 time to first audio, latency per stage, and tokens and cost per conversation and per bot. *Evidence:* the generated report.
- [ ] **OB-03 A review console.** An admin area in the frontend app (React and TypeScript), reusing its login and admin role, to browse conversations, play audio, see the trace and the memories used, annotate problems, and turn a conversation into a test (EV-06). *Evidence:* the admin area and a short screen recording.
- [ ] **OB-04 Structured logs.** JSON logs with a correlation ID that links every log line to its conversation and trace. *Evidence:* a sample log excerpt.

## EN: Engineering hygiene and presentation

- [ ] **EN-01 A clear layout.** Separate modules for bots, the agent runtime, voice, memory, tools, safety, evals and infra, with typed interfaces between them; the review console lives in the frontend repo (OB-03). *Evidence:* the repo tree in the README.
- [x] **EN-02 Modern Python tooling.** uv, ruff, strict type checking (pyright or mypy), pytest and pre-commit hooks. *Evidence:* config files and a clean CI run.
  - *Met by:* `pyproject.toml` and `uv.lock` (uv, ruff, mypy strict, pytest), `.pre-commit-config.yaml`, `Makefile`. Proven by `uv run pre-commit run --all-files` and `make lint test` passing, and by the CI `checks` job (S0.2).
- [ ] **EN-03 One-command run.** Docker Compose plus `make demo`, `make test`, `make lint` and `make eval`. *Evidence:* a fresh clone runs with those commands alone.
- [ ] **EN-04 Continuous integration.** Lint, types, tests and the fast eval subset on every pull request. *Evidence:* the GitHub Actions workflow.
- [ ] **EN-05 Decision records.** A short ADR for each significant choice in `docs/adr/`, linked from the checklist IDs it satisfies. *Evidence:* `docs/adr/`.
- [x] **EN-06 Secrets handled properly.** Keys only in environment variables, with an `.env.example` and no secrets in git history. *Evidence:* a secret-scanning step in CI.
  - *Met by:* `.env.example`, `SecretStr` settings in `src/companion/config/settings.py`, the gitleaks pre-commit hook, and the CI `secret-scan` job, which scans the full history with `.gitleaks.toml`. Proven by `gitleaks git` finding nothing across all commits (S0.2).
- [ ] **EN-07 A README that leads with results.** A 60-to-90-second demo video, an architecture diagram, the eval and latency tables, how to run it, and honest limitations. *Evidence:* the README itself.
- [ ] **EN-08 A write-up.** A short post on how the bots' reliability and memory recall were measured. *Evidence:* the published link.

## RG: Regional latency

The app runs in Australia by default, but many reviewers will open it from the US. A US visitor must get US infrastructure at every layer, chosen automatically.

- [ ] **RG-01 Region profiles in config.** One profile per region (`au` as default, `us`) naming the endpoint or region for every layer: agent worker, STT, LLM, safety model, TTS, MCP server, vector store and cache. Validated at startup (AR-08). *Evidence:* the profiles and a validation test.
- [ ] **RG-02 Region chosen once per session, on the server.** The token server picks the region when it issues the LiveKit token, using the edge the client reached or IP geolocation, with the browser's time zone as a last resort. A testing override (for example, `?region=us`) exists, and every decision is logged. *Evidence:* tests for each signal and for the override.
- [ ] **RG-03 Every layer follows the session's region.** The session is dispatched to the agent worker in that region, and every downstream client is built from that region's profile. The exception is everything off the live-call path (memory, the MCP server, the database, the cache, post-call jobs), which stays in Sydney for every session (AR-09, RG-04). Where a provider offers no regional option, an ADR says so and the latency cost is measured. *Evidence:* a trace with every span served from the chosen region.
- [ ] **RG-04 Memory residency is a decision, not an accident.** Every user's memories live in Sydney, the single home region. An ADR records what happens when they connect from the US: memory reads cross the Pacific and the filler covers the wait. *Evidence:* the ADR and a cross-region test.
- [ ] **RG-05 Regional failover.** If a provider in one region is unhealthy, the session falls back to the other region's profile, and the fallback is logged. *Evidence:* an outage simulation test.
- [ ] **RG-06 Latency proven from both regions.** Synthetic sessions run from Australia and the US, and the latency report (OB-02) shows time to first audio for each. *Evidence:* a two-region latency table in the README.

Checked 2026-10-17 (details and sources in ARCHITECTURE.md → Regions): LiveKit Cloud hosts agents only in the US, Frankfurt and Mumbai, so the Australian worker is self-hosted in AWS Sydney; LiveKit region pinning is per project, so the project stays unpinned and each region gets its own agent name; Deepgram has an Australian endpoint; Groq routes to its nearest data centre automatically; Fish's hosted TTS has no Australian endpoint. These are options, not choices: each layer's vendor is picked by measurement when that layer is built.
