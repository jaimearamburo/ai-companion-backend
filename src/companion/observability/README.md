# `observability/` — Observability

Structured logging with call context attached automatically, and (later) the per-turn metrics the spec asks for: bets fired/wasted, bet-to-commit time, recall tool usage, vendor latencies.

## Usage

```python
from companion.observability import configure_logging, get_logger, bind_session_context, bind_turn_context

configure_logging(level=settings.log_level, render_json=settings.use_json_logs)  # once, at startup

logger = get_logger(__name__)
bind_session_context(session_id="...", presets={"stt": "inworld_stt1", ...})  # at call start
bind_turn_context(turn_id="...")                                              # at each turn
logger.info("bet_fired", bets_this_turn=1)
```

Log an event name plus key=value fields, not formatted sentences — fields stay searchable in JSON.

## How it works

- **One format for everything:** our code logs through structlog; LiveKit and other libraries log through Python's standard `logging`. Both go through the same processors and renderer.
- **Formats:** readable console lines locally, one JSON object per line when deployed (chosen by `LOG_FORMAT` / `ENVIRONMENT`, see `config/`).
- **Call context** (`session_id`, `turn_id`, `presets`) is held in context variables, which asyncio copies into every task a call starts — bind once, and it appears on every line from that call.
- **Privacy rule:** fields named `pii_*` (and LiveKit's `lk.pii.*`) are stripped from every line above DEBUG. Put anything a user said in a `pii_` field — never in the event name or another field. Combined with the config rule that refuses DEBUG in production, what users say never reaches production logs.

**Spec:** REQUIREMENTS.md → "Error handling" (structured logging); ARCHITECTURE.md → "Turn-taking" (metrics).

**Status:** logging implemented (task 0.8); metrics not yet.
