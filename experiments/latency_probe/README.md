# Latency probe

Measures how fast each external service in the pipeline responds from the machine it runs on, so vendor and hosting choices are based on measured numbers rather than published claims. Not part of the application: it lives outside `src/` and has its own dependency group (`experiments`), which is never installed in the deployed image.

## Run

```bash
uv run --group experiments python experiments/latency_probe/probe.py
```

It reads the same `.env` as the application (through `companion.config.load_settings`), so every required setting must be present. A run makes a few dozen small requests and costs a fraction of a cent.

## What it measures

Each measurement runs once untimed (warm-up), then 7 timed times; the table shows min / median / max in milliseconds.

| Row | What it times | Why |
|---|---|---|
| network round trip | TCP connection to each service host, DNS resolved beforehand | Pure network distance — shows whether a service answers from nearby |
| LLM first token (any) | Request sent → first streamed token, including the model's internal reasoning | Network + queueing + prompt processing |
| LLM first visible text | Request sent → first token of the actual reply | What speech actually waits for; the gap to the row above is reasoning time |
| Deepgram 1s-audio request | Uploading a 1-second clip and receiving the transcript, Australian vs global endpoint | Endpoint location effect (a request/response call, not streaming latency) |
| Redis PING / Postgres SELECT 1 | Round trip over an already-open connection | Per-query cost with a persistent connection |
| connection setup | Opening a new Redis / Postgres connection | Why the agent keeps connections open |

## Privacy

Prints no secrets and no hostnames (some contain project identifiers); services are labelled by name. Errors are reported by type or HTTP status only. The prompts sent are fixed test sentences.

## Results

See [RESULTS.md](RESULTS.md).
