# Latency probe — results

**Run:** 2026-09-29, from the developer's home internet connection in Australia (about 15ms round trip to Sydney). Seven timed runs per row after one warm-up. From a server in AWS Sydney, every row would drop by roughly that 15ms of home-connection distance; comparisons between services are unaffected.

## Measured

| Measurement | Min | Median | Max (ms) |
|---|---:|---:|---:|
| **Network round trip** | | | |
| LiveKit Cloud | 13.7 | 18.0 | 25.2 |
| Groq API | 12.8 | 16.3 | 18.3 |
| Amazon Bedrock (ap-southeast-2) | 13.3 | 16.6 | 17.8 |
| Deepgram — Australian endpoint | 14.0 | 15.1 | 17.4 |
| Deepgram — global endpoint | 291.8 | 295.3 | 298.9 |
| Redis (Upstash) | 13.6 | 16.5 | 21.8 |
| Postgres (Supabase) | 15.9 | 19.9 | 26.7 |
| **LLM — scriptwriter model** | | | |
| Groq gpt-oss-120b — first token (any) | 97.9 | 363.2 | 786.6 |
| Groq gpt-oss-120b — first visible text | 126.8 | 412.4 | 835.8 |
| Bedrock gpt-oss-120b — first visible text | 353.0 | 518.3 | 624.3 |
| Bedrock gpt-oss-20b — first visible text (reference) | 384.2 | 428.8 | 555.8 |
| Groq gpt-oss-20b (reference) | — | — | HTTP 403: model not enabled on this Groq account |
| **LLM — safety model** | | | |
| Groq safeguard-20b — first token (any) | 96.5 | 101.4 | 107.6 |
| Groq safeguard-20b — first visible text | 117.9 | 124.6 | 136.7 |
| Bedrock safeguard-20b — first visible text | 245.5 | 391.8 | 462.7 |
| **STT (request/response, 1-second clip)** | | | |
| Deepgram — Australian endpoint | 45.8 | 67.8 | 2,068.5 |
| Deepgram — global endpoint | 324.1 | 388.6 | 603.1 |
| **Memory** | | | |
| Redis PING, open connection | 6.7 | 11.8 | 14.0 |
| Redis connection setup (one-off) | — | 111.4 | — |
| Postgres SELECT 1, open connection | 12.5 | 15.5 | 21.3 |
| Postgres connection setup (one-off) | — | 114.1 | — |

Bedrock returns no separate reasoning tokens in its stream, so its "first token (any)" equals "first visible text"; only the latter is shown.

## What it shows

1. **Every chosen service answers from Australia.** LiveKit, Groq's API, Bedrock, Deepgram's Australian endpoint, Upstash and Supabase all sit at the same \~15ms as the home connection's distance to Sydney. Deepgram's global endpoint is \~295ms away — the Australian endpoint saves \~280ms per round trip.
2. **Groq beats Bedrock Sydney on both models**, despite Bedrock being confirmed in-region: safety model \~125ms vs \~392ms (median, first visible text), scriptwriter \~412ms vs \~518ms. In-region hosting is not automatically faster.
3. **Groq's gpt-oss-120b is highly variable**: 127ms at best, 836ms at worst, 412ms median. The safety model on the same API is steady at \~100–135ms, so the network isn't the cause; likely queueing/capacity for the larger model, or serving from outside Sydney for some requests. Not determinable from here.
4. **The scriptwriter's time to first text (\~400–500ms) is the largest single latency in the turn**, larger than the design's \~200ms bet head start. The speculative bet absorbs part of it; the filler has to cover the rest. gpt-oss-20b on Groq, which would likely be much faster (the same-size safety model starts in \~100ms), is blocked on this account.
5. **Persistent connections matter**: opening a Redis or Postgres connection costs \~110ms; a query over an open connection costs \~12–16ms.
6. **Occasional outliers** (one Deepgram request at \~2s, one Postgres connect earlier at \~1s) — a reminder that every vendor call needs a timeout.
