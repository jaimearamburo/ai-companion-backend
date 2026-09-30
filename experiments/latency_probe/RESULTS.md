# Latency probe — results

All measurements from the developer's home internet connection in Australia (about 15ms round trip to Sydney). From a server in AWS Sydney every row would drop by roughly that distance; comparisons between services are unaffected.

## Probe run — 2026-09-30

Seven timed runs per row after one warm-up; LLM requests spaced 2s apart with automatic retries off. LLM rows use a short one-line prompt (see the follow-up tests below for a realistic prompt).

| Measurement | Min | Median | Max (ms) |
|---|---:|---:|---:|
| **Network round trip** (DNS excluded) | | | |
| LiveKit Cloud | 10.5 | 17.0 | 24.7 |
| Groq API | 13.8 | 15.3 | 17.1 |
| Amazon Bedrock (ap-southeast-2) | 14.3 | 16.0 | 17.3 |
| Deepgram — Australian endpoint | 14.1 | 16.6 | 27.5 |
| Deepgram — global endpoint | 165.2 | 173.0 | 178.2 |
| Fish API (Cloudflare edge — see note) | 14.3 | 16.6 | 18.3 |
| Redis (Upstash) | 14.9 | 16.3 | 17.3 |
| Postgres (Supabase) | 11.9 | 16.6 | 20.1 |
| **LLM — first visible text, short prompt** | | | |
| Groq gpt-oss-120b | 326.6 | 403.6 | 896.1 |
| Bedrock gpt-oss-120b | 405.3 | 526.2 | 646.2 |
| Groq gpt-oss-20b | 321.1 | 369.9 | 478.1 |
| Bedrock gpt-oss-20b | 268.6 | 474.6 | 692.9 |
| Groq safeguard-20b | 110.1 | 117.4 | 151.1 |
| Bedrock safeguard-20b | 246.2 | 448.0 | 499.0 |
| **STT (request/response, 1-second clip)** | | | |
| Deepgram — Australian endpoint | 56.4 | 69.9 | 213.7 |
| Deepgram — global endpoint | 272.2 | 281.8 | 292.6 |
| **TTS — time to first audio (Fish S2.1, free model, request/response API)** | | | |
| latency=low | 435.4 | 521.3 | 1,054.5 |
| latency=balanced | 427.6 | 465.4 | 548.6 |
| **Memory** | | | |
| Redis PING, open connection | 9.5 | 11.1 | 13.3 |
| Redis connection setup (one-off) | — | 142.2 | — |
| Postgres SELECT 1, open connection | 11.6 | 12.6 | 15.3 |
| Postgres connection setup (one-off) | — | 285.7 | — |

"First token (any)" rows (which include the model's reasoning) are printed by the probe but omitted here; on Groq they're \~15–50ms earlier than first visible text. Bedrock streams no separate reasoning tokens.

**Fish note:** the round trip only reaches Cloudflare's Sydney site (the `cf-ray` header ends in `SYD`); synthesis itself happens in Fish's US/Tokyo infrastructure, which is why first audio takes \~465–520ms despite the 16ms round trip.

## Follow-up tests — 2026-09-29/30

One-off scripts (in `experiments/modal_inference/` and ad hoc), realistic \~1.2k-token scriptwriter prompt (two personas, rules, a fact sheet), 10–12 runs each, requests spaced out, retries off.

**Groq — where and why:**

| Groq (all requests served from region `syd`) | First visible text, median | Groq-reported queue time | Groq-reported prompt processing |
|---|---:|---:|---:|
| gpt-oss-20b, short prompt | 328ms | 199ms | 7ms |
| gpt-oss-20b, realistic prompt | 465ms | 203ms | 81ms |
| gpt-oss-120b, short prompt | 400ms | 259ms | 5ms |
| gpt-oss-120b, realistic prompt | 531ms | 244ms | 57ms |

- The `x-groq-region` response header was `syd` on every request: Groq serves both models from Sydney.
- **\~200–250ms of every request is queueing** on Groq's shared capacity; the model itself is fast. 20b vs 120b differs by only \~60–70ms.
- Realistic prompts hit the free tier's rate limit (HTTP 429). With the SDK's default automatic retries on, these showed up as 7–11 *second* "latencies" — retries must be off when measuring.
- `qwen/qwen3.8-27b` is listed but blocked on this account (HTTP 403).

**Bedrock Sydney — standard vs Priority tier** (realistic prompt, first visible text, median): 20b 550 / 554ms; 120b 553 / 431ms. Priority doesn't materially help.

**Self-hosted gpt-oss-20b on Modal (Australian region):** no measurement possible — no GPU container ever started (L40S, then A100-40GB / A100-80GB / H100), 10+ minutes queued each attempt. No GPU time was billed.

## What it shows

1. **Every chosen service except TTS answers from Australia.** Deepgram's Australian endpoint saves \~150–280ms per round trip over the global one.
2. **Groq beats Bedrock Sydney** for both models, and is steadier for the safety model (\~117ms vs \~448ms). Chosen: Groq primary, Bedrock automatic fallback.
3. **The LLM's first visible text (\~400–530ms) is dominated by Groq's queue**, not model size or distance. Under 200ms isn't reachable on these managed hosts with reasoning on; the speculative bet absorbs \~250ms and the filler covers the rest.
4. **Fish's hosted TTS adds \~465–520ms to first audio** from Australia on the free model over the request/response API — the largest remaining latency. Still to measure: its streaming WebSocket API (what the agent uses) and the paid model.
5. **Persistent connections matter:** opening a Redis or Postgres connection costs \~140–290ms; a query over an open one \~11–13ms.
6. **Occasional outliers** (a 1s Fish request, 900ms Groq request) — every vendor call needs a timeout.
