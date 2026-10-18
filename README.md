# Voice Companion — Backend

[![CI](https://github.com/jaimearamburo/ai-companion-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/jaimearamburo/ai-companion-backend/actions/workflows/ci.yml)

The backend of a **real-time voice AI companion**: you talk with one or two AI companion characters, who listen, decide between them who should answer, reply in their own voices, occasionally talk over each other, and remember earlier conversations. Built for Australia first, with US infrastructure for users in the Americas and Europe.

This repository holds the agent, its tools, the voice pipeline and the database schema. The web app (login, picking companions, joining the call) is a separate Next.js repository.

## How it works

A call is a continuous loop: the user speaks, the pipeline works out when they've finished, the agent writes a reply for the right character, and the reply is spoken. The target is the first sound within 300ms of the user finishing and the first word of the real reply within a second.

```
  user's voice
       │  real-time audio (WebRTC)
       ▼
  LiveKit Cloud ──► Worker (this repo; one per call, in the user's region)
                      ├─ LiveKit Agents ..... speech to text, turn-taking, text to speech, per-character audio tracks
                      └─ Agent runtime ...... prompt, scriptwriter LLM, safety check, tool loop
                              │ tool calls (MCP)
                              ▼
                    MCP server (Sydney) .... memory and reminder tools, scoped to the user
                              │
                    Postgres + pgvector .... users, characters, calls, transcripts, memories
```

| Layer | What it does |
|---|---|
| **Real-time transport** | Carries the call's audio between the browser and the worker (LiveKit Cloud, WebRTC) |
| **Voice pipeline** | Streams speech to text, detects when the user has really finished, starts drafting a reply early to hide model latency, and speaks each character in its own voice (LiveKit Agents) |
| **Agent runtime** | One LLM plays every character: it chooses who answers and writes their lines, within limits enforced in code; a separate safety model screens what the user says and fails closed |
| **Tools** | A standalone MCP server serves memory and reminder tools and decides whose data each request may see |
| **Memory** | A short profile loaded at call start; older memories searched only when needed; new memories extracted after each call |
| **Data** | Accounts, characters, calls, transcripts and memories in Supabase Postgres, schema owned by this repo |

No vendor is fixed for any layer: each is chosen by latency measured from both regions ([results so far](experiments/latency_probe/RESULTS.md)). The full design is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Engineering approach

- **Measured, not assumed.** Vendor and region choices come from latency measured where the system runs; for example, most of the LLM's response time turned out to be queueing on the provider, not the model.
- **Guardrails in code.** User scoping, tool limits, speaker limits and fixed safety wording are enforced by code and tests, not by the prompt.
- **Proof by evaluation.** The agent is designed to be tested with simulated users, scored on what ends up stored, and run repeatedly to measure reliability.
- **The database enforces its own rules.** Same-user references, row-level security on every table, and CI checks that try to break each rule.
- **Quality gates.** Strict typing, linting, tests with coverage, secret scanning on every commit and in CI, and decision records for each significant choice.

## How this project is built

I designed this project and own it end to end: the architecture, the product decisions, the vendor and hosting choices (made from my own measurements), and the review of every change before it's committed.

I use **Claude Code** (an AI coding assistant) as a pair programmer for implementation and research, directed through written requirements — [REQUIREMENTS.md](REQUIREMENTS.md) and [CLAUDE.md](CLAUDE.md) are the standing instructions I give it, and [PLAN.md](PLAN.md) is the plan I work through with it in small, reviewable batches.

## Status

Early stage: the foundations are in place.

- **Done:** project foundation (typed configuration, structured logging with privacy rules, CI); database schema for accounts, companions, calls, transcripts and companion–user relationships, with automated checks; vendor research backed by a latency study.
- **Remaining work** is in [PLAN.md](PLAN.md), and progress against the definition of done is in [docs/DESIGN_CHECKLIST.md](docs/DESIGN_CHECKLIST.md).

## Documentation

| File | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The full design: stack, latency budget, memory, database schema, cost model, known issues |
| [PLAN.md](PLAN.md) | The plan: steps, decisions and their status |
| [docs/DESIGN_CHECKLIST.md](docs/DESIGN_CHECKLIST.md) | The definition of done, with evidence for each item |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Environment notes and gotchas |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Engineering standards and working rules |
| [experiments/latency_probe/RESULTS.md](experiments/latency_probe/RESULTS.md) | Measured latency of every service from Australia |
| [supabase/README.md](supabase/README.md) | How database migrations are written, checked and applied |
| `src/companion/*/README.md` | What each module owns |

## Repository layout

```
src/companion/        the application package
├── bots/             loads and validates bot definitions from the database
├── config/           typed settings from environment variables
├── contracts/        strict typed models for everything crossing a boundary
├── dispatch/         call-start checks: user, bot limit per role, bot versions
├── providers/        preset name → configured STT/TTS/LLM/turn detector (all vendor specifics live here)
├── turn_taking/      speculative drafting triggers, limits and cancellation
├── safety/           safety gate (fails closed)
├── scriptwriter/     scriptwriter prompt, script format, memory-lookup tool
├── memory/           profile, memory search, embeddings, memory queries
├── extraction/       post-call memory extraction job
├── audio/            per-character audio tracks, interruption timing, events for the frontend
├── pipeline/         wires the modules into one call's pipeline (the only place they meet)
└── observability/    structured logging, per-turn metrics
tests/unit/           mirrors src/companion/
tests/integration/    pipeline tests against recorded vendor responses
experiments/          measurement scripts (latency probe, self-hosting experiment)
supabase/             the database schema (migrations/) and its CI checks (ci/)
```

## Local development

Requires [uv](https://docs.astral.sh/uv/) (Python package and version manager; it installs the right Python version automatically) and `make`.

```bash
make install                  # install dependencies and the git pre-commit hooks
cp .env.example .env          # then fill in real credentials

make lint                     # lint, formatting check and strict type check
make format                   # format the code and apply safe lint fixes
make test                     # tests, with a coverage report of untested lines and branches
make help                     # list every target
```

Every commit runs the same checks plus a secret scan through pre-commit hooks. CI runs them again on every push to `main` and every pull request, together with the database migration checks and a secret scan of the full history (`.github/workflows/ci.yml`). Decisions are recorded in [docs/adr/](docs/adr/).

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
