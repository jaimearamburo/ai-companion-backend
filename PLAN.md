# Refactor plan

This plan aligns the backend with established agent-engineering practice: declarative bots with deterministic guardrails, tools behind a standard protocol, evaluation by simulated users scored on end state, versioned releases, tracing, and region-aware latency. The **product does not change**: one user talking with one or two companion bots, in real time, with safety screening and memory that carries across calls.

The definition of done is the design checklist, [docs/DESIGN_CHECKLIST.md](docs/DESIGN_CHECKLIST.md). Each item's status is tracked in its "Met by" line.

**Progress is tracked on GitHub,** not in this file: the [Voice Companion Backend project](https://github.com/users/jaimearamburo/projects/2) and this repo's [milestones](https://github.com/jaimearamburo/ai-companion-backend/milestones). Each batch of a step is one issue whose title starts with its ticket ID (for example `S3.1`), grouped into seven milestones that show percent complete. Commits reference the ticket: `S3.1 AR-03: …` with `Closes #N` in the body.

Prepared 2026-10-17 against commit `08d6ddf`; approved 2026-10-18.

## 1. Principles

1. **Proof before polish.** Steps that let the system demonstrate it works (the text-mode engine, safety, the eval harness, memory correctness) come first. Presentation comes last.
2. **One orchestrator, two transports.** A transport-agnostic agent runtime serves both voice (through LiveKit) and text (evals, CLI). Nothing that decides behaviour lives only in the voice path.
3. **The model decides the conversation; code enforces hard limits.** The scriptwriter LLM chooses which bot speaks and writes its lines. Code enforces what must never vary: which bots are in the call, which tools exist, whose data a tool can see, fixed wording, and how many tool calls a turn may make.
4. **Keep what works.** Settings, logging, the schema and its CI checks, the measured vendor choices, fail-closed safety and the memory design are extended, not rewritten.
5. **Small, shippable steps.** Each step is one reviewable batch, ends with lint, types, tests and (from step 5) evals passing, and updates the checklist's evidence lines. Large steps are split into numbered batches.
6. **Verify vendors before building on them.** Every library or provider API is checked against current official docs at the step that uses it; section 2 records what was checked today.
7. **Pay only for live-call latency.** Paid services are considered only for the live-call layers: transport, worker compute, speech to text, turn detection, the scriptwriter and safety LLMs, and text to speech. Everything else lives in Sydney on free or self-hosted options where possible: the MCP server and memory lookups (a filler masks their latency), the database and vector search, the cache, embeddings, post-call extraction, evals, tracing and CI. Nothing runs around the clock unless it must: servers start on demand and scale to zero when no calls are active (D27, D35).
8. **Vendors are chosen per layer, by measurement, when that layer is built.** No vendor is fixed yet for any layer, because none has yet reached its latency target in testing. Each layer's step measures the candidates from both regions and picks the one that meets the target, preferring vendors with in-region inference in Australia and the US. Names in this plan are candidates, not commitments.

### How the pieces fit after the refactor

LiveKit, the agent runtime and the MCP server are three separate things:

- **LiveKit** is two parts. *LiveKit Cloud* is LiveKit's own media service, which carries the audio. *LiveKit Agents* is a Python library that runs inside our worker and runs the voice loop.
- **The agent runtime** is our Python package. It runs inside the same worker process as LiveKit Agents, and LiveKit's LLM step calls it on every turn. It talks to the LLM and runs the tool loop.
- **The MCP server** is a separate program of ours. It runs beside the memory database, holds the memory tools, and is the only piece that reads or deletes memories during a call.

#### Terms used in this plan

| Term | Meaning |
|---|---|
| **Agent** | The AI system as a whole: the agent runtime, the LLM it calls, its tools, guardrails and memory. It decides who speaks and what to say, calls tools, and works within limits enforced in code. |
| **Agent runtime** | Our Python package `companion/agent/`, main class `CompanionAgent`. It runs the agent for each turn and has no LiveKit imports. |
| **LiveKitBridge** | The small class that connects LiveKit Agents to the agent runtime. Named differently because LiveKit's own base class is called `Agent`. |
| **LiveKit agent / agent participant** | LiveKit's name for any program that joins a call room. Here, the participant that speaks for the bots. Plumbing, not the AI agent. |
| **Worker** | Our server process that waits for LiveKit to send it a call, then runs LiveKit Agents and the agent runtime for that call. |
| **Agent name** | The label LiveKit uses to route a call to the workers in one region, for example `companion-au`. |
| **Bot** | One character in a call. All bots in a call are voiced by the same agent in one LLM request. |
| **MCP server** | Our separate program that holds the agent's tools (today, memory) and enforces whose data each tool may see. |

#### Where each piece runs

| Piece | Runs where | Talks to |
|---|---|---|
| LiveKit Cloud | LiveKit's servers, nearest edge to each user | The browser and our workers |
| Worker process (one per call): LiveKit Agents + agent runtime + audio router | Our servers in AWS, started on demand in the call's region and scaled to zero when idle (D35) | LiveKit Cloud, STT, TTS, LLM and safety vendors, the MCP server; Redis only at call start and end |
| MCP server | Our servers in AWS **Sydney**, started on demand whenever any call is active and shared by all calls (D35) | Postgres. US workers reach it across the Pacific (D12) |
| Extraction job | After each call, in Sydney, started from a queue (D20) | Postgres, an LLM |
| Postgres (Supabase) | Sydney | — |
| Redis | Sydney only, free tier | — |
| Eval runner and text CLI | A developer machine or CI | The agent runtime directly (no LiveKit), the MCP server, the LLM |

In development, everything runs on one machine and the agent runtime starts the MCP server itself over stdio.

#### Who does what

| Job | Done by | Notes |
|---|---|---|
| Carry audio between the browser and the worker | **LiveKit** (Cloud + Agents framework) | WebRTC, nearest edge, one agent participant per call |
| Send each call to the worker in the right region | **LiveKit** dispatch | One agent name per region, chosen when the call starts |
| Voice activity, turn detection, barge-in | **LiveKit** | v1-mini turn detector on the worker CPU |
| Speech to text and text to speech | **LiveKit** plugins | Built from the session's region profile; vendors are called directly |
| Start drafting early and play fillers | **LiveKit** triggers, **agent runtime** drafts | LiveKit says when; the agent runtime produces the draft |
| One audio track per bot | **LiveKit** output + **our audio router** | The router is our code plugged into LiveKit's audio output |
| Load the memory summary (cheat sheet) at call start | **Agent runtime** asks the **MCP server**; result kept in the worker's memory for the call | All memory reads go through the MCP server, so user scoping lives in one place |
| Build the prompt: every bot's persona, memories and the recent conversation | **Agent runtime** | Fixed section order and token budgets |
| Choose which bot speaks and write its lines | **Scriptwriter LLM** (host to be chosen) | One request covers all bots in the call; the LLM acts as the chosen bot |
| Check the LLM's choice | **Agent runtime** | Rejects a reply that names a bot not in the call or breaks a hard limit (D2) |
| Call the LLM, with fallback | **Agent runtime** | Primary and fallback hosts per region chosen by measurement (D8); switch on rate limit, server error or no first token in time; reply streamed back to LiveKit |
| Run the tool loop | **Agent runtime** | Gives the LLM the tool schemas, forwards its tool calls to the MCP server, enforces the per-turn limit and timeouts |
| Screen user input, fixed wording | **Agent runtime** | Fails closed. Output screening is a pluggable stage, off by default (D7) |
| Expose memory tools (recall, list, forget, ask another bot after consent) | **MCP server** | Never talks to the LLM and never decides when a tool is used |
| Decide whose data a tool may see | **MCP server** | Scope comes from the signed session token, never from the model |
| Embed queries and search memories | **MCP server** | Embedding model loaded once; pgvector in Postgres |
| Write new memories after the call | **Extraction job** | Uses the same memory code as the MCP server; not called by the LLM |
| Store memories, transcripts, users and bots | **Postgres** (Supabase) | System of record, including vectors |
| Hold per-call state and the cheat sheet | **Worker process memory** | Each call has its own process, so nothing per-turn crosses the Pacific |
| Shared state: per-user rate limits, the extraction queue | **Redis** in Sydney | Touched only at call start and end, never per turn |

The agent runtime has no LiveKit imports, so the eval runner can call it without a voice session. The tool loop belongs to the agent runtime, not to LiveKit or the MCP server.

### What happens to the code that exists today

Most of this plan is new code, because almost nothing behaviour-deciding exists yet. The code that does exist is kept and extended:

| Existing piece | What changes | Step |
|---|---|---|
| `config/settings.py` | Vendor keys become optional per region profile instead of all required; region profiles added | S2 |
| `observability/logging_setup.py` | Trace IDs added to every log line; otherwise unchanged | S10 |
| Migrations 1 and 2 | Not yet applied to the real database (confirmed 2026-10-18), so S1 edits migration 2 in place for the new bot fields, `bot_versions` and session region. Memories and reminders get new migrations (S6, S20). Nothing is applied until S1 is done | S1, S6, S20 |
| `supabase/ci/` checks | Extended for each new migration | S1, S6, S20 |
| Module stubs under `src/companion/` (README only) | Reorganised into the new layout: `agent/`, `voice/`, `tools_server/`, `memory/`, `safety/`, `evals/` | S0–S3 |
| `experiments/latency_probe/` | Extended to run from AWS in both regions with more candidates | S2 |
| ARCHITECTURE.md | Largely rewritten to the new design | S0, then kept current |

## 2. Provider regional options (checked 2026-10-17)

These are the options found for each layer, not choices. Each layer's vendor is decided at the step that builds it (principle 8).

Sources are listed in section 8.

| Layer | Australia (default) | United States | Finding |
|---|---|---|---|
| Agent worker | **Self-hosted in AWS `ap-southeast-2`** | Self-hosted in AWS `us-east-1`, or LiveKit Cloud `us-east` | LiveKit Cloud hosts agents only in `us-east`, `eu-central` and `ap-south`. An Australian worker must be self-hosted. Multi-region routing is done by giving each regional deployment its own agent name and dispatching explicitly. |
| Media transport | LiveKit `aus` region group | LiveKit `us` region group | `aus` is a single location without in-region redundancy; `us` has three. Region pinning is per **project**, needs the **Scale** plan or higher, is switched on by LiveKit support, and has no automatic failover. An unpinned project routes each client to its nearest cluster. **Pinning the project to `aus` would force US users through Australia**, so the current plan to pin should be dropped. |
| STT | Deepgram `api.au.deepgram.com` | Deepgram `api.deepgram.com` (global, US) | The AU endpoint serves Nova-3, **Flux** (`/v2/listen`) and **Aura-2 TTS** (`/v1/speak`). Requests to it never leave Australia: if the region is down they fail rather than fall back, so failover must be explicit. |
| LLM hosting candidates (scriptwriter and safety) | Groq, Sydney data centre; Bedrock `ap-southeast-2`; others to be listed | Groq, US data centres; Bedrock `us-east-1`, `us-east-2`, `us-west-2` | Bedrock serves gpt-oss-120b in-region in Sydney and all three US regions; safeguard-20b in the US still to be confirmed. Groq routes automatically to its nearest data centre, but its paid tier is not currently offered, so its free-tier rate limits apply. Other hosts with in-region inference in both countries are still to be identified and measured. |
| TTS | Fish hosted API is served from the US and Tokyo only | Fish hosted API (US) | Fish is a good fit for US sessions and the slowest stage for Australian ones (~465–520ms to first audio). Australian options: Deepgram Aura-2 on the AU endpoint (self-serve), Cartesia's dedicated Australian deployment (enterprise only), Fish S2.1 through a third-party host that advertises Sydney compute (unverified), Azure Neural TTS in Australia East. |
| Turn detection | v1-mini on the worker CPU | Same | LiveKit's docs now say the full v1 model is served on LiveKit Inference in every region and is free for agents deployed on LiveKit Cloud; v1-mini is recommended for self-hosted agents. |
| Backchannel handling | — | — | LiveKit's adaptive interruption model (filters "mm-hm") is included for agents deployed on LiveKit Cloud, with 40,000 free requests a month in development. A self-hosted worker needs its own backchannel rule (VO-05). |
| MCP server | Self-hosted in Sydney beside the database | US workers call the Sydney server (D12) | No vendor dependency. A US server is added only if memories get a US home. |
| Vector store | pgvector in Supabase, Sydney (see D5) | Same database, read cross-region (see D12) | Free: already part of the database. |
| Cache | Upstash Redis `ap-southeast-2`, free tier | Same Sydney database | Upstash supports Sydney and `us-east-1`, but the cache holds only shared state touched at call start and end, so one free Sydney database serves both regions. |
| Database | Supabase, Sydney | — | One project. Its region is fixed. See decision D14. |
| Embeddings | Self-hosted model in the MCP server | Same | Runs wherever the server runs. |

Two corrections to ARCHITECTURE.md follow from this: the region-pinning plan and plan tier are out of date, and Flux on the Australian endpoint is now confirmed.

## 3. Decisions

Numbers are stable references used throughout this plan. Status as of 2026-10-18; the plan itself was approved on that date (D31).

### 3.1 Decided

| # | Decision | Date |
|---|---|---|
| D1 | Bot definitions stay in the `bots` table. Every row is validated by a strict model when loaded, edits create a new immutable row in `bot_versions`, and a release pins bot version IDs. | 2026-10-17 |
| D2a | The scriptwriter LLM chooses which bot speaks and writes its lines. | 2026-10-17 |
| D2 | Hard limits around that choice: the speaker must be a bot in the call; one speaker per turn, two during banter; banter can be switched off on safety-sensitive turns; a reply that breaks a limit is retried once, then replaced by a safe line. | 2026-10-18 |
| D3 | The agent runtime runs the tool loop. LiveKit Agents runs the voice side and calls the agent runtime in-process through `LiveKitBridge`. The MCP server holds the agent's tools. | 2026-10-17 |
| D4 | MCP library: the official `mcp` SDK, confirmed by a short spike and an ADR. | 2026-10-18 |
| D5 | pgvector only, behind a `VectorStore` interface. No Qdrant. | 2026-10-17 |
| D7 | Bot output is **not** screened for now, to protect latency. Output screening is designed as a pluggable stage that can be switched on later without code changes. | 2026-10-18 |
| D10 | One LiveKit project, no region pinning, one agent name per region. | 2026-10-18 |
| D11 | Workers run on our own AWS servers in each region, started on demand (see D35). | 2026-10-18 |
| D12 | Memories, the MCP server, the database, the cache and post-call jobs live in Sydney for every session. | 2026-10-17 |
| D13 | Retention is unlimited for now; documented as a policy. | 2026-10-18 |
| D14 | Claude drafts crisis, refusal and consent lines with official helplines per region; the maintainer approves the exact text at S4. | 2026-10-18 |
| D16 | Evals use free tiers first, under spend caps per run and per month; the numbers are set when evals are first run. | 2026-10-18 |
| D17 | The review console is an admin area in the frontend repo, reusing its login and admin role. | 2026-10-18 |
| D18 | TASK_BREAKDOWN.md is retired; see D36 for removing all other plan documents. | 2026-10-18 |
| D19 | The maintainer makes every commit by hand; each step ends with a suggested commit message. | 2026-10-17 |
| D20 | The extraction job is started from a queue in the Sydney Redis, so a failed run retries. | 2026-10-18 |
| D21 | Paid services only for live-call layers (transport, worker compute, STT, turn detection, scriptwriter and safety LLMs, TTS). Everything else in Sydney on free or self-hosted options where possible. | 2026-10-17 |
| D22 | No vendor is fixed for any layer. Each is chosen by measured latency when its layer is built, preferring in-region inference in Australia and the US. | 2026-10-17 |
| D24 | Latency targets, measured from each region: first audible sound (filler) within 300ms of turn commit at p50 and 500ms at p95; first word of the real reply within 1.0s at p50 and 1.2s at p95. | 2026-10-18 |
| D26 | A failing live-call vendor may fall back to its equivalent in the other region; every fallback is logged. Flagged for the privacy review. | 2026-10-18 |
| D27 | Services run on demand; nothing runs 24/7 unless it must. | 2026-10-18 |
| D28 | Small, short-lived spend on measurement runs is approved. | 2026-10-18 |
| D29 | User-facing behaviours: bots confirm a misheard name or date before remembering it; "what do you remember about me" returns a brief LLM-written summary within hard limits; deleting memories by voice works only when a setting is switched on before the call starts, only specific memories can be deleted, there is no "forget everything", and a deleted memory is deactivated (`is_active = false`) so it is never read again rather than removed; no second safety check; a maximum call length set by the developer, shown in the frontend as a countdown. | 2026-10-18 |
| D31 | The reworded checklist and this plan are approved. | 2026-10-18 |
| D32 | S1 starts with two clearly marked placeholder bots; real characters and voices come later. | 2026-10-18 |
| D33 | Names: the agent runtime (package `companion/agent/`, class `CompanionAgent`) and `LiveKitBridge`. | 2026-10-18 |
| D34 | Reminders, phase 1: our own `reminders` table and MCP tools with written policies; a reminders list in the frontend later. No external calendar sync for now. | 2026-10-18 |
| D15 | The frontend's server chooses the region when it issues the token, from the country of the user's IP address: Australia, New Zealand and Asia use `au`; the Americas and Europe use `us`. A `?region=` override for testing, the browser's time zone as a fallback, and a log line for every decision. | 2026-10-18 |
| D23b | English only for the first release; other languages are added later, each with its own eval set. | 2026-10-18 |
| D25 | Measure `us-east-1` and `us-west-2` during the D8 run and pick the faster end to end. | 2026-10-18 |
| D35 | Servers in the chosen region, and the Sydney MCP server, start when the user opens the room-setup screen and stop after a set idle time with no calls; a short wait on the first visit is acceptable. | 2026-10-18 |
| D36 | PLAN.md is the only plan document in the repo. In S0: delete TASK_BREAKDOWN.md (kept in git history); move REFACTOR_PLAN/HANDOFF.md into `docs/private/`, which is git-ignored, alongside the assessment notes already there; copy HANDOFF's environment notes into a committed `docs/DEVELOPMENT.md`; merge REFACTOR_PLAN/NEW_CLAUDE.md into CLAUDE.md; move the checklist to `docs/`; remove the REFACTOR_PLAN folder; point CLAUDE.md, README.md, ARCHITECTURE.md and the module READMEs at PLAN.md instead of old task numbers. | 2026-10-18 |
| D37 | No per-user limits for now; only the maximum call length. Limits can be added later as configuration. | 2026-10-18 |
| D38 | The user switches memory deletion on or off on the room-setup screen before the call; it defaults to off. | 2026-10-18 |
| D39 | Code comments explain why, not what the language does. Language and library explanations for the maintainer go in private learning notes and in chat, never in committed code. Existing tutorial-style comments are tidied in S0. | 2026-10-18 |

### 3.2 Open

None. Decisions that depend on measurements are in 3.3.

### 3.3 Chosen at their step by measurement

These follow D22 and the targets in D24; nothing to decide now.

| # | Decision | Step | How |
|---|---|---|---|
| D6 | Embedding model | S6 | CPU latency on the Sydney server and retrieval score; candidates `intfloat/multilingual-e5-small`, `BAAI/bge-small-en-v1.5`, `nomic-embed-text-v1.5` |
| D8 | LLM hosts per role and region | S2, S3 | Time to first token from both regions with realistic prompts and reasoning on; candidates Bedrock, Groq (free tier only), other in-region hosts |
| D9 | TTS per region | S13 | Time to first audio from each region, then your listening test; candidates include Fish, Deepgram Aura-2 (Australian endpoint), Azure Neural TTS, Cartesia |
| — | STT per region | S13 | Same method; candidates Deepgram Nova-3 and Flux on the Australian endpoint, others as found |
| — | Extraction LLM | S8 | Off the live call, so free or cheapest first (D21), chosen on extraction accuracy against recorded transcripts |
| — | AWS compute service for on-demand servers | S2, S15 | Start-up time and cost per call for the candidates (D35) |

## 4. Steps

Effort is relative size: **S** small, **M** medium, **L** large; a large step is split into the batches shown. Implementation uses an AI coding assistant under the maintainer's direction, and the maintainer reviews and commits every change, so the pace is set by review and decisions rather than by writing code. Every step ends with `make lint`, `make test` and (from S5) `make eval` passing, and the checklist's "Met by" lines updated.

### S0 — Standards and housekeeping
- **IDs:** EN-02, EN-04, EN-05, EN-06 (toward), EN-03 (partial), AR-09 (ADR)
- **Batch 1, documents:** PLAN.md becomes the only plan (D36). Move the checklist to `docs/`, merge the working rules into CLAUDE.md, move HANDOFF.md into the git-ignored `docs/private/`, copy its environment notes into a committed `docs/DEVELOPMENT.md`, delete TASK_BREAKDOWN.md and the REFACTOR_PLAN folder, and replace old task numbers with plan steps.
- **Batch 2, tooling:** a Makefile (`lint`, `test`, and an `eval` placeholder that fails with a clear message), pre-commit hooks (ruff, mypy, secret scan), a secret-scanning CI step with an allowlist for the fake test URLs, a no-op CI job for docs-only changes so required checks never hang, and `docs/adr/` with a template and the first ADRs converted from ARCHITECTURE.md.
- **Batch 3, accuracy:** fix stale documentation (the sequence diagram's TTS, the multi-bot section's TTS vendor, the wasted-draft cost share of ~7–8% of ~1.5–1.7¢/min, the missing rule against giving the scriptwriter raw transcripts from other calls, the auth tables still marked as a draft, the region-pinning plan and plan tier, Flux on the Australian endpoint, the turn detector's availability, Groq's paid tier not currently offered, the database and stack sections of REQUIREMENTS.md, example preset names in two module READMEs, `.env.example`'s endpoint note, and the README's description of the project); update ARCHITECTURE.md with the responsibility split from section 1 and the decisions so far; tidy tutorial-style comments in existing code (D39).
- **Done when:** pre-commit and CI run the secret scan; `make lint test` pass; no document other than PLAN.md describes future work.
- **Effort:** M, three batches. **Risk:** low.

### S1 — Typed models and validated bot definitions
- **IDs:** AR-01, AR-08, MT-02 (model)
- **Work:** Strict Pydantic v2 models for bot definitions (persona, voice, model per role, memory policy, allowed tools, safety rules), dispatch metadata (now with `region`), script output (speaker segments and tags), memory records, tool inputs and outputs, safety verdicts and eval scenarios. A migration adding the missing bot fields and an immutable `bot_versions` table. A loader that validates every bot row and fails loudly on an invalid one.
- **Done when:** adding a bot needs only a new validated row; tests feed malformed payloads at every boundary, including a bad bot row.
- **Effort:** M. **Frontend:** regenerate Supabase types.

### S2 — Provider interfaces, region profiles and a resilient client
- **IDs:** AR-02, RG-01, RL-01, AR-04 (config)
- **Work:** Typed interfaces for LLM, safety classifier, STT, TTS and vector store. Adapters for the LLM host candidates, starting with OpenAI-compatible APIs, with SDK retries off. A measurement run from both regions to choose hosts (D8). Fakes for tests. Region profiles (`au`, then `us`) naming every endpoint, validated at startup. One async client wrapper giving every vendor call a timeout and backoff retries for idempotent reads only. Refactor `Settings`: vendor API keys stop being required up front (no vendor is fixed, D22); each region profile names the vendors it uses, and startup fails only if a key that profile needs is missing.
- **Done when:** a fake LLM drives tests; invalid profiles fail at startup; timeout and retry behaviour is tested.
- **Effort:** M. **Needs:** D8 and D25 (measured here), start-up times for D35 (measured here).

### S3 — Transport-agnostic agent runtime
- **IDs:** AR-03, AR-05, AR-06, MT-06 (part), EV-10 (foundation), VO-08
- **Work:** The agent runtime: prompt builder with a fixed, documented section order and a token budget per section (snapshot-tested), checks on the LLM's speaker choice (D2), fixed-text responses, and a bounded tool loop interface. A text CLI to chat with the bots. A benchmark test of the engine's own overhead per turn.
- **Done when:** a scripted multi-bot conversation runs end to end in text against the fake and the real LLM; speaker checks and fixed text have unit tests; the overhead benchmark passes the VO-08 budget.
- **Effort:** L, two batches. **Needs:** D2, D3. **Conflict:** replaces the plan for LiveKit to run the tool loop.

### S4 — Safety gate
- **IDs:** SF-01, SF-02, SF-03, AR-05
- **Work:** Screen each user turn in parallel with the draft. ADR with the category-to-action table (block, rephrase, fixed text). Fail closed on error, timeout or unparseable verdict. Output screening as a pluggable stage, off by default (D7), with a test that plugs in a fake output screener.
- **Done when:** tests force a timeout, garbage output and a slow verdict, and the exact fixed text is produced in each case.
- **Effort:** M.

### S5 — Evaluation harness v1
- **IDs:** EV-01, EV-02, EV-03, EV-10
- **Work:** Scenario files (persona, goals, facts to mention, later questions, expected end state). An LLM simulated user. An asyncio runner with a concurrency limit that records model versions and seeds. Scorers that check end state: memories that exist afterwards, tools called with which arguments, safety actions fired. A report with pass^1 and pass^k (k = 4) per scenario and per bot. `make eval`. A first set of 10 scenarios, growing to 30 across later steps.
- **Done when:** `make eval` produces the report; a test proves the eval path and the voice adapter call the same agent runtime.
- **Effort:** L, two batches. Spend caps set by the maintainer at the first run (D16).

### S6 — Memory store and embedding pipeline
- **IDs:** MT-02, MT-04, MT-12, RG-04 (schema)
- **Work:** Embedding benchmark on the target instance type, then the memories migration (adding confidence, kind as fact, preference or event, and `is_active`). A `VectorStore` interface with an in-memory implementation for tests and a pgvector implementation. Chunking and embedding separated from search. A re-embedding script. A retrieval score on seeded memories in the eval report.
- **Done when:** retrieval score is reported; migration passes CI checks; deleting a memory clears every store in a test.
- **Effort:** L. **Needs:** D6 (measured here). **Frontend:** regenerate Supabase types.

### S7 — Tools on an MCP server
- **IDs:** MT-05, MT-06, MT-07, MT-08, MT-10, MT-11, VO-03, VO-08
- **Work:** A standalone MCP server with the memory tools (recall, list, forget, ask another bot's memory after consent). Each session gets a signed, short-lived token carrying user, bots and region; the server derives scope from it and the tool schemas contain no user or bot IDs. Strict argument validation with structured, recoverable errors. stdio in development and tests; in deployment one long-running server beside the memory database over Streamable HTTP, shared by all calls, with the tool list fetched once and connections kept open. The orchestrator discovers tools at startup and an adapter converts their schemas to the chosen LLM host's tool format. Per-call timeout, a maximum number of tool calls per turn, and a graceful line when either limit is hit. Retrieved memories enter the prompt in a delimited data block.
- **Done when:** tests cover discovery, malformed calls, both limits, a request for another user's data returning nothing across the MCP boundary, and a poisoned memory that fails to change behaviour.
- **Effort:** L, two batches. **Needs:** D3, D4.

### S8 — Memory writes, tiers and user control
- **IDs:** MT-01, MT-03, MT-09, RL-04, VO-07, EV-04
- **Work:** The post-call extraction job (ADD, UPDATE, SKIP; idempotent per session). Written promotion and demotion rules between the cheat sheet and deep memory, with an ADR. "What do you remember about me" as a brief LLM-written summary within hard limits. "Forget that" for specific memories, only when the call's deletion setting is on (D38), setting `is_active = false` so the memory leaves every read path; no "forget everything". Retention documented as unlimited (D13). Confirmation of misheard names and dates before they are stored. Multi-session eval scenarios, including facts that change between sessions.
- **Done when:** duplicate and contradicting facts are tested; a deactivated memory never reaches the cheat sheet or recall; deletion is refused when the setting is off; recall accuracy appears in the eval report.
- **Effort:** L, two batches. **Needs:** the extraction model (measured here). **Frontend:** the memory-deletion toggle on the room-setup screen (D38).

### S9 — Red-team set
- **IDs:** EV-08, SF-05, MT-08
- **Work:** Harmful requests, jailbreaks, injection attempts and poisoned memories, each with an expected outcome; block rate and false-alarm rate in the report.
- **Done when:** the red-team report exists.
- **Effort:** M.

### S20 — Reminders (numbered last to keep other step numbers stable)
- **IDs:** MT-13, MT-05, EV-02
- **Work:** A `reminders` table in Sydney. MCP tools to create and list reminders, with policies enforced in code: read the date and time back and get a yes before saving; resolve dates in the user's time zone; reject dates in the past. Bots bring up due reminders in the next call. Eval scenarios scored on the reminders that exist afterwards.
- **Done when:** each policy has a test and eval scenarios pass on end state.
- **Effort:** M. **Frontend:** regenerate Supabase types; a reminders list later.

### S10 — Tracing and the latency and cost report
- **IDs:** OB-01, OB-02, OB-04, VO-01, AR-04, AR-09
- **Work:** OpenTelemetry export (LiveKit Agents already emits spans under the GenAI semantic conventions; Langfuse is one documented backend). Our own spans for safety verdicts, tool calls with arguments and results, and memory reads and writes. Trace IDs on log lines. A generated report: p50 and p95 time to first audio, per-stage latency, tokens and cost per conversation and per bot. A written latency budget with targets.
- **Done when:** one full trace per conversation is visible; the report is generated from an eval run.
- **Effort:** M.

### S11 — Releases and the CI eval gate
- **IDs:** AR-07, EV-06, EV-09
- **Work:** A release manifest pinning bot version IDs, prompt templates, model IDs and the embedding model. `make release` and `make rollback`. The worker registers under an agent name that includes the release, so two releases can run side by side through explicit dispatch. A fast eval subset in CI that fails when pass^k drops below the last release. A command that turns a logged conversation into a regression scenario.
- **Done when:** a pull request shows eval scores; rollback is exercised in a test.
- **Effort:** M. **Needs:** an LLM key as a CI secret, with a spend cap.

### S12 — Multi-bot audio prototype
- **IDs:** VO-02, VO-04 (risk reduction)
- **Work:** The existing Phase 2 prototype: one session publishing one audio track per bot, the frame tag surviving to the custom output, barge-in clearing every track, `bot_speaking` events. Kept outside `src/`. Can be pulled earlier at any point, because nothing before it depends on audio.
- **Effort:** M. **Risk:** the core multi-bot audio assumption is still unproven; if it fails, only the audio router changes.

### S13 — Voice pipeline on the agent runtime
- **IDs:** VO-02, VO-04, VO-05, VO-06, SF-03
- **Work:** The LiveKit session built from the region profile, `LiveKitBridge` streaming from the agent runtime, speculative drafting as designed, sentence-level TTS, the output-screening hook left off (D7), a text normaliser for numbers, dates and times, a backchannel rule, and stored transcripts that keep only what was heard.
- **Done when:** a trace shows stages overlapping; an interruption test checks the stored transcript; backchannels don't trigger replies in simulation.
- **Effort:** L, three batches. **Needs:** D9 (measured here).

### S14 — Reliability under failure
- **IDs:** RL-02, RL-03, RL-04, RL-05
- **Work:** Switching from the primary LLM host to the fallback (rate limit, server error, no first token in time), and to the other region's vendor when a live-call vendor fails (D26). A natural spoken line for each failure type. Reconnect and resume from the stored transcript. A maximum call length set by the developer, enforced by the backend, with a `call_ends_at` event the frontend shows as a countdown. No per-user limits for now (D37).
- **Done when:** tests simulate a provider outage, each failure type, a reconnect, and a rate-limit breach.
- **Effort:** M.

### S15 — Two regions
- **IDs:** RG-02, RG-03, RG-04, RG-05, RG-06
- **Work:** The `us` profile. A Dockerfile and on-demand deployment (D35): workers started in the call's region, the MCP server and extraction job in Sydney, all scaled to zero when idle. Workers that reject a dispatch for another region. A residency ADR. Failover to the other region's vendor when one is unhealthy, logged. Synthetic sessions from both regions with a two-region latency table.
- **Done when:** a trace from each region shows every span served in that region (or an ADR explains the exception); an outage test switches profile.
- **Effort:** L, three batches. **Frontend:** region choice when issuing the token (D15), the `?region=` override, the warm-up request when the room-setup screen opens (D35), dispatch to the regional agent name, logging of each decision.

### S16 — Calibrated judge
- **IDs:** EV-05
- **Work:** A written rubric for persona consistency, warmth and brevity. A judge model. 20 to 30 conversations hand-labelled by you; the agreement rate in the report.
- **Effort:** M. **Needs:** your labelling time.

### S17 — Realistic audio and load
- **IDs:** EV-07, RL-06
- **Work:** Voice-mode runs with varied synthetic voices, background noise, phone-quality compression and interruptions, reported clean versus realistic. LiveKit's audio simulations are an option alongside our own runner. A load test with 20 or more simulated conversations at once.
- **Effort:** M.

### S18 — Review console
- **IDs:** OB-03, EV-06 (UI)
- **Work:** A small React and TypeScript app to browse conversations, play audio, see the trace and memories used, annotate problems and turn a conversation into a test.
- **Effort:** L. **Frontend:** this step is built in the frontend repo's admin area (D17).

### S19 — One-command run and presentation
- **IDs:** EN-01, EN-03, EN-07, EN-08
- **Work:** Docker Compose (worker, MCP server, Redis, Postgres with pgvector) and `make demo` (text mode needs only an LLM key). A README that leads with a short demo video, an architecture diagram, eval and latency tables, how to run it, and honest limitations. A short write-up on how reliability and recall were measured.
- **Effort:** M.

**Total:** 38 tickets. At two to four batches reviewed a day, that is roughly two to four weeks. Work that cannot be compressed sits alongside it and may set the real pace:

- the open decisions in section 3.2, the real bot roster, the fixed safety wording and the voice listening test;
- hand-labelling 20–30 conversations for the judge (S16);
- applying each migration by hand in the Supabase SQL editor and relaying frontend changes;
- vendor and cloud setup: accounts with the chosen LLM, STT and TTS vendors, AWS in two regions, CI secrets;
- eval runs against real models under rate limits, kept slow by the free-first rule;
- live voice calls to tune turn-taking, backchannels and the banter fade by ear;
- the multi-bot audio prototype (S12), which may force a redesign of the audio router.

## 5. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| LiveKit Agents changes quickly (1.8.x; `mcp_servers` already deprecated; span format changed in 1.7 and 1.8) | Adapter breakage | Keep LiveKit behind the thin adapter (D3); pin versions; re-read docs at S12 and S13 |
| Eval spend grows with scenarios × k × judge | Cost | Spend cap per run; fakes for unit-level checks; full suite nightly, subset per pull request |
| Managed LLM hosts queue requests (~200–250ms measured on Groq's free tier) | Time to first text | Speculative drafting and fillers as designed; choose hosts by measured time to first token (D8) |
| TTS remains the slowest stage in Australia | Time to first audio | D9 measurement; filler lengths tuned to it |
| Backchannel model unavailable to a self-hosted worker | False interruptions | Own rule (VO-05) tested in simulation |
| Supabase is single-region | Cross-region recall latency for US sessions | D12; measured in S15 |
| Fish free model ends 30 Nov 2026 | TTS stops working for tests | Budget for the paid model before then |
| Cold start of on-demand servers | A wait before the first call of a session | Warm up when the room-setup screen opens (D35); measure start-up times early |
| Deactivated memories and unlimited retention keep personal data | Privacy obligations | Documented policy; flagged for the privacy review before real users |
| Scope (70 items) | Long tail | Steps ordered by impact; each ships on its own |

## 6. Changes the frontend repo will need

- Choose the region when issuing the LiveKit token (D15), with a `?region=` override and a log line for each decision.
- Send a warm-up request when the room-setup screen opens, so servers are ready by the time the call starts (D35).
- Dispatch to the regional agent name, and add `region` and the memory-deletion setting (D38) to the dispatch metadata.
- Show a countdown from the `call_ends_at` event (S14).
- Host the review console in the admin area (S18), and later a reminders list (S20).
- Regenerate Supabase types after every migration (S1, S6, S8, S20).
- Copy the updated ARCHITECTURE.md once S0 fixes the stale sections.

## 7. Working agreement for each step

1. List the checklist IDs the step touches before starting.
2. Stop and ask if the step would weaken any item.
3. Run `make lint`, `make test` and `make eval` (once it exists) and report results.
4. Finish with a checklist report: IDs newly met with evidence, IDs regressed, IDs made easier.
5. Update the "Met by" lines; never renumber IDs; never mark an item met without a test or runnable command.
6. Stop with a suggested commit message. Jaime reviews and commits every change himself.

## 8. Sources

- LiveKit: [agent deployment regions](https://docs.livekit.io/deploy/admin/regions/agent-deployment.md), [regions and endpoints](https://docs.livekit.io/deploy/admin/regions/endpoints.md), [region pinning](https://docs.livekit.io/deploy/admin/regions/region-pinning.md), [turn detector](https://docs.livekit.io/agents/logic/turns/turn-detector.md), [adaptive interruption handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling.md), [MCP](https://docs.livekit.io/agents/logic/tools/mcp.md), [async tools](https://docs.livekit.io/agents/logic/tools/async.md), [simulations](https://docs.livekit.io/testing/simulations.md), [unit tests](https://docs.livekit.io/testing/unit-tests.md), [OpenTelemetry traces](https://docs.livekit.io/testing/observability/tracing.md), [Inference](https://docs.livekit.io/agents/models/inference.md)
- Deepgram: [regional endpoints](https://developers.deepgram.com/reference/regional-endpoints)
- Groq: [optimizing latency (`x-groq-region`)](https://console.groq.com/docs/production-readiness/optimizing-latency), [community thread on regional endpoints](https://community.groq.com/t/can-i-connect-to-regional-api-endpoints-with-groqcloud/835)
- Amazon Bedrock: [gpt-oss-120b model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html)
- Upstash: [global database regions](https://upstash.com/docs/redis/features/globaldatabase)
- Cartesia: [regional endpoints](https://docs.cartesia.ai/enterprise/regional-endpoints)
- Third-party Sydney host for Fish S2.1 (unverified): [SLNG Australia](https://www.slng.ai/regions/australia)
- MCP: [specification 2026-07-28 transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), [`mcp` on PyPI](https://pypi.org/project/mcp/), [`fastmcp` on PyPI](https://pypi.org/project/fastmcp/)
