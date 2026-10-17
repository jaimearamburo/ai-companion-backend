# Development notes

Things about this repo's environment that the code and other docs don't make obvious. Setup commands are in the [README](../README.md); the plan is in [PLAN.md](../PLAN.md).

## Tooling

- **Pre-commit hooks** run on every commit: whitespace and file checks, ruff, mypy and gitleaks. Install them with `make install`. The first run downloads Go to build gitleaks, so it takes a minute. Run every hook by hand with `uv run pre-commit run --all-files`.

- **uv only.** `uv sync` installs the `dev` group; `uv sync --all-groups` also installs `experiments`. CI runs `uv sync --locked --all-groups`, so a stale `uv.lock` fails CI. Run `uv lock` after editing `pyproject.toml`.
- **mypy checks `experiments/` too** (`files = ["src", "tests", "experiments"]`). Experiment scripts must stay strict-clean without `type: ignore`.
- **Ruff also formats Python code blocks inside Markdown.** A malformed code block in a README can fail `ruff format --check`.
- **Python is pinned to 3.13** (`.python-version`, `requires-python = ">=3.13,<3.14"`); uv installs it automatically.

## CI

- **CI always runs.** Its first job checks which files changed; for changes that touch only Markdown or the licence, the code and migration jobs are skipped, which GitHub counts as passing, so required checks never hang. The secret scan runs on every change.
- **The secret scan covers the full history** with a checksum-verified gitleaks release. Narrow exceptions live in `.gitleaks.toml`; add one only for a confirmed false positive, as specific as possible.
- **`supabase/ci/checks.sql` lists the migration versions** in its final block. Every new migration must add its version there, plus its own behavioural checks.

## Migrations

- **Applied by hand, never by tooling.** Each file is pasted into the Supabase SQL editor, in filename order. Never point `supabase/ci/apply_migrations.sh` or any script at the real database.
- **Each file is one transaction** (`BEGIN; … COMMIT;`) and records itself in `supabase_migrations.schema_migrations`, so the Supabase CLI would recognise it if adopted later.
- **Never edit a migration once it has been applied** to the real database; write a new one.
- **The CI bootstrap mimics Supabase's defaults.** `supabase/ci/bootstrap.sql` creates `anon`, `authenticated` and `service_role` and grants them access to new tables, so the migrations' `REVOKE` statements are actually tested. A new table, or partition, without `REVOKE` and `ENABLE ROW LEVEL SECURITY` fails CI.

## Environment variables and secrets

- **Required and optional variables** are listed in `.env.example` and enforced by `src/companion/config/settings.py`.
- **Empty means unset:** `KEY=` counts as missing.
- **Unrelated variables are ignored** (`extra="ignore"`), so `.env` can also hold experiment-only keys such as `MODAL_LLM_URL` and `MODAL_LLM_API_KEY`.
- **Quoted values** in `.env` are fine for pydantic-settings; any hand-written check that reads the file must strip the quotes first.
- **Never print secret values, URLs or hostnames from `.env`**; some hostnames contain project identifiers. Check names and formats only.

## Vendors

- **Supabase connection.** Development uses the direct connection (port 5432). The production design is the transaction pooler (port 6543) with prepared statements disabled in the driver, plus a small client-side pool: each call runs in its own process, so a direct connection per call would exhaust Postgres's connection limit. Opening a connection costs about 285ms, so connections stay open.
- **The OpenAI SDK retries 429 responses silently.** With default retries on, rate-limited requests show up as 7–11 second "latencies". Use `max_retries=0` for anything latency-sensitive and handle retries deliberately.
- **Bedrock** is called through its OpenAI-compatible endpoint (`https://bedrock-runtime.<region>.amazonaws.com/openai/v1`) with a long-term Bedrock API key. It streams no separate reasoning tokens.
- **Groq** reports the serving data centre in the `x-groq-region` response header. Only its free tier is currently available, with rate limits that realistic prompts hit.
- **Fish Audio's free model** (`s2.1-pro-free`) runs until 30 Nov 2026 and may use requests to train Fish's models: test conversations only.
- **LiveKit Cloud's "agents region" setting** applies to agents hosted by LiveKit, so it is irrelevant to the self-hosted worker.

## Shell (WSL)

- **`pkill -f <pattern>`** can match and kill the shell running it (exit 144). Stop Modal apps with `modal app stop companion-llm` instead.

## Parked GPU experiments

- **Modal:** the `companion-llm` app is stopped; the Modal secret `companion-llm-key` still exists. Always run `modal app stop companion-llm` after an experiment.
- **RunPod:** if the design in ARCHITECTURE.md → Voice (TTS) is ever built, every Pod must be terminated, not stopped, after each call, with all the layered shut-offs described there.
