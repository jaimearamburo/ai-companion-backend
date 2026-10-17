# Voice Companion — Backend

[![CI](https://github.com/jaimearamburo/ai-companion-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/jaimearamburo/ai-companion-backend/actions/workflows/ci.yml)

The backend of a hobby **real-time voice AI companion app**: you have a spoken conversation with one or two AI companion characters, who listen, decide between them who should answer, reply in their own distinct voices, occasionally chime in on each other, and remember what you've talked about before.

This repository is the voice pipeline and the database schema. The web app (login, picking companions, joining the call) is a separate Next.js repository.

## How it works

A call is a continuous loop: the user speaks, the pipeline works out when they've finished, writes a reply for the right character, checks it, and speaks it — aiming for the first sound within a few hundred milliseconds.

```
  user's voice
       │  real-time audio (WebRTC)
       ▼
  LiveKit Cloud ──────────────► Agent (this repo, Python, LiveKit Agents)
                                  │
                                  ├─ Speech-to-text ......... Deepgram, Australian endpoint
                                  ├─ Turn-taking ............ has the user finished? start drafting early
                                  ├─ Scriptwriter LLM ....... who speaks, and what they say
                                  │    └─ Safety check ...... runs in parallel; blocks unsafe replies
                                  ├─ Text-to-speech ......... Fish Audio, one voice per character
                                  └─ Memory + data .......... Redis, Supabase Postgres
                                  │
       ◄──────────────────────────┘  each character's voice on its own audio track
```

| Layer | What it does | Built with |
|---|---|---|
| **Real-time transport** | Carries the call's audio between the browser and the agent | LiveKit Cloud (WebRTC) |
| **Agent** | Runs the conversation loop for each call and wires the layers below together | Python, LiveKit Agents |
| **Speech-to-text** | Streams a live transcript of what the user is saying | Deepgram Nova-3 (Australian endpoint) |
| **Turn-taking** | Detects when the user has really finished speaking, and starts drafting a reply *before* that's certain — discarded if they keep talking — to hide model latency | LiveKit turn detector + a custom speculative trigger |
| **Scriptwriter LLM** | One model plays every character: decides which companion should reply (or both), writes their lines with emotional cues, and can look up older memories when it needs them | gpt-oss-120b on Groq (Sydney), with automatic fallback to Amazon Bedrock (Sydney) |
| **Safety** | A separate classifier checks the conversation alongside the reply; if anything is unclear or fails, a safe response plays instead (fails closed) | gpt-oss-safeguard-20b |
| **Text-to-speech** | Turns each line into speech in that character's voice, streamed as it's generated | Fish Audio |
| **Memory** | Recent conversation in the prompt; a short profile loaded when a call starts; long-term memories searched only when needed, and written after each call | Redis, Postgres + pgvector |
| **Data** | Accounts, companions, call history, transcripts — schema owned by this repo | Supabase Postgres |

## Engineering highlights

- **Swappable providers.** Every vendor (speech-to-text, LLM, safety, text-to-speech, turn detection) sits behind a named preset, so providers can be compared or replaced by configuration rather than code changes.
- **Measured, not assumed.** Vendor and hosting choices were made from a latency study run from Australia ([results](experiments/latency_probe/RESULTS.md)) — e.g. finding that most of the LLM's response time was queueing on the provider's side, not the model itself.
- **Resilience by design.** Every external call has a timeout and a failure path; the safety check fails closed; the LLM falls back to a second provider automatically.
- **Data stays in Australia** for every latency-critical service except text-to-speech, and row-level security keeps the database closed to the browser.
- **Quality gates.** Strict static typing (`mypy --strict`), linting, tests with coverage, and a CI job that applies every database migration to a throwaway Postgres and checks the schema's rules actually hold.

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
| [REQUIREMENTS.md](REQUIREMENTS.md) | Engineering standards and working rules |
| [experiments/latency_probe/RESULTS.md](experiments/latency_probe/RESULTS.md) | Measured latency of every service from Australia |
| [supabase/README.md](supabase/README.md) | How database migrations are written, checked and applied |
| `src/companion/*/README.md` | What each module owns |

## Repository layout

```
src/companion/        the application package
├── config/           typed settings from environment variables
├── dispatch/         parses/validates per-call settings sent by the frontend
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

Requires [uv](https://docs.astral.sh/uv/) (Python package and version manager — installs the right Python version automatically).

```bash
uv sync                       # create .venv and install everything
cp .env.example .env          # then fill in real credentials

uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy                   # type check (strict)
uv run pytest                 # tests, with a coverage report of untested lines/branches
uv run pytest --cov-report=html   # same, plus a clickable report in htmlcov/index.html
```

CI runs the same checks on every push, plus the database migration check (`.github/workflows/ci.yml`).

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
