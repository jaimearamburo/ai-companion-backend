# Voice Companion — Backend

The real-time voice pipeline for the Voice Companion: a self-hosted [LiveKit Agents](https://docs.livekit.io/agents/) worker (Python) that listens to a user, decides which AI companion bot(s) should respond, checks safety, draws on the user's memories, and streams each bot's voice back into the call. It also owns the shared Supabase database schema.

The frontend (Next.js — login, room setup, joining the call) lives in a separate repo.

## Documentation

| File | What it is |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Source-of-truth spec for the whole project (shared with the frontend repo) |
| [REQUIREMENTS.md](REQUIREMENTS.md) | How this repo is built: engineering bar, process, working rules |
| [TASK_BREAKDOWN.md](TASK_BREAKDOWN.md) | Phased task list for building this backend |
| `src/companion/*/README.md` | What each module owns |

## Layout

```
src/companion/        the application package
├── config/           typed settings from environment variables
├── dispatch/         parses/validates per-call dispatch metadata from the frontend
├── providers/        preset name → configured STT/TTS/LLM/turn detector (all vendor specifics live here)
├── turn_taking/      speculative-bet triggers, bet cap and cancellation
├── safety/           safety gate (fails closed)
├── scriptwriter/     scriptwriter prompt, script format, recall_memory tool hookup
├── memory/           cheat sheet, recall search, embeddings, memory queries
├── extraction/       post-call fact extraction job
├── audio/            per-bot tracks, banter scheduler, bot_speaking/bot_fade events
├── pipeline/         wires the modules into one call's pipeline (the only place they meet)
└── observability/    structured logging, per-turn metrics
tests/unit/           mirrors src/companion/
tests/integration/    pipeline tests against recorded vendor responses
supabase/             the database schema (migrations/) and its CI checks (ci/) — single source of truth for both repos
```

## Local development

Requires [uv](https://docs.astral.sh/uv/) (Python package and version manager — installs the right Python version automatically).

```bash
uv sync                       # create .venv and install everything (like `npm install`)
cp .env.example .env          # then fill in real credentials

uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy                   # type check (strict)
uv run pytest                 # tests, with a coverage report of untested lines/branches
uv run pytest --cov-report=html   # same, plus a clickable report in htmlcov/index.html
```

CI runs the same four checks on every push (`.github/workflows/ci.yml`).

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
