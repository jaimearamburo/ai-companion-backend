"""Scriptwriter latency: self-hosted gpt-oss-20b on Modal (Australia) vs Groq (Sydney).

Run after deploying llm_server.py:
    uv run --group experiments python experiments/modal_inference/latency_test.py

Uses a realistic scriptwriter prompt (~1.2k tokens: two personas, rules, a fact
sheet) because prompt length drives time to first token. Measures, per model,
host and reasoning effort (low / medium):
  - first token of any kind (the model's reasoning starts streaming)
  - first visible text (what speech has to wait for)
The gap between the two is thinking time. Also measures the network round trip
to the Modal endpoint (TCP connect, DNS excluded).

The first request to Modal starts the container (a cold start: minutes the first
time, while the model downloads), so it's an untimed warm-up with a long timeout.
Automatic retries are disabled so rate limits show up as errors, not as delays.
"""

import asyncio
import socket
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from companion.config import load_settings

REPEATS = 10
PAUSE_S = 3.0  # spacing between requests, to stay under Groq's rate limits
TIMEOUT_S = 60.0
COLD_START_TIMEOUT_S = 30 * 60.0

_TOPICS = [
    "their garden", "a sister called Anne", "a dog named Max", "liking jazz",
    "a knee operation", "a trip to Perth", "cooking lasagne", "a neighbour called Tom",
    "the footy on Saturdays", "a nephew at uni", "an allergy to penicillin",
    "playing bridge", "a favourite café", "reading crime novels", "a leaking roof",
    "bird-watching", "a cat called Misty", "learning Italian", "a choir group", "sourdough",
]  # fmt: skip
FACTS = "\n".join(f"- The user mentioned {t} on a previous call." for t in _TOPICS * 3)
SYSTEM = (
    "You write dialogue for two companion characters in a voice call.\n"
    "GARY: retired builder, warm, jokes about his tomatoes, calls people 'mate'.\n"
    "PAUL: former teacher, gentle, precise, teases Gary, asks thoughtful questions.\n"
    "Rules: reply as ONE character, one or two short spoken sentences, natural and "
    "kind. Start with the character's name and a colon. Never give medical advice. "
    "Use the facts below only when relevant.\nKnown facts about the user:\n" + FACTS
)
# The reasoning levels compared.
type Effort = Literal["low", "medium"]

USER_LINE = "I was just thinking about my sister coming to visit this weekend, isn't that nice."


@dataclass
class Row:
    name: str
    first_any: list[float] = field(default_factory=list)
    first_text: list[float] = field(default_factory=list)
    errors: Counter[str] = field(default_factory=Counter)
    sample: str = ""


def median(values: list[float]) -> str:
    return f"{statistics.median(values):6.0f}" if values else "     —"


def span(values: list[float]) -> str:
    return f"{min(values):4.0f}-{max(values):4.0f}" if values else "    —    "


def has_reasoning(delta: object) -> bool:
    """Reasoning arrives under non-standard field names, kept in model_extra."""
    extra = getattr(delta, "model_extra", None) or {}
    return any(extra.get(name) for name in ("reasoning", "reasoning_content"))


async def one_request(
    client: AsyncOpenAI, model: str, effort: Effort
) -> tuple[float | None, float | None, str]:
    """Stream one reply; return (first token of any kind, first visible text, text)."""
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER_LINE},
    ]
    start = time.perf_counter()
    first_any: float | None = None
    first_text: float | None = None
    text = ""
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=600,
        stream=True,
        reasoning_effort=effort,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        now = (time.perf_counter() - start) * 1000
        if first_any is None and (delta.content or has_reasoning(delta)):
            first_any = now
        if delta.content:
            if first_text is None:
                first_text = now
            text += delta.content
    return first_any, first_text, text


async def measure(client: AsyncOpenAI, label: str, model: str, effort: Effort) -> Row:
    row = Row(f"{label:26} reasoning={effort:6}")
    for attempt in range(REPEATS + 1):
        await asyncio.sleep(PAUSE_S)
        # The very first request may cold-start the Modal container: allow minutes.
        timeout = COLD_START_TIMEOUT_S if attempt == 0 else TIMEOUT_S
        try:
            async with asyncio.timeout(timeout):
                first_any, first_text, text = await one_request(client, model, effort)
        except TimeoutError:
            row.errors["timeout"] += 1
            continue
        except APIStatusError as error:
            row.errors[f"HTTP {error.status_code}"] += 1
            continue
        except Exception as error:
            row.errors[type(error).__name__] += 1
            continue
        if attempt == 0:
            continue  # warm-up, not timed
        if first_any is not None:
            row.first_any.append(first_any)
        if first_text is not None:
            row.first_text.append(first_text)
            row.sample = text
    return row


async def tcp_round_trip_ms(host: str) -> list[float]:
    loop = asyncio.get_running_loop()
    address = (await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM))[0][4][0]
    samples = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        _reader, writer = await asyncio.open_connection(str(address), 443)
        samples.append((time.perf_counter() - start) * 1000)
        writer.close()
        await writer.wait_closed()
    return samples


async def main() -> None:
    settings = load_settings()
    extra = dotenv_values(Path(".env"))
    modal_url = extra.get("MODAL_LLM_URL") or ""
    modal_key = extra.get("MODAL_LLM_API_KEY") or ""
    if not modal_url or not modal_key:
        raise SystemExit("MODAL_LLM_URL and MODAL_LLM_API_KEY must be set in .env")

    modal_host = urlsplit(modal_url).hostname or ""
    rtt = await tcp_round_trip_ms(modal_host)
    print(f"\nNetwork round trip to the Modal endpoint: median {statistics.median(rtt):.0f} ms")

    rows: list[Row] = []
    async with (
        AsyncOpenAI(base_url=f"{modal_url}/v1", api_key=modal_key, max_retries=0) as modal,
        AsyncOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key.get_secret_value(),
            max_retries=0,
        ) as groq,
    ):
        efforts: tuple[Effort, ...] = ("low", "medium")
        for effort in efforts:
            rows.append(await measure(modal, "Modal L40S (au) 20b", "gpt-oss-20b", effort))
            rows.append(await measure(groq, "Groq (syd) 20b", "openai/gpt-oss-20b", effort))
            rows.append(await measure(groq, "Groq (syd) 120b", "openai/gpt-oss-120b", effort))

    print(f"\n~1.2k-token scriptwriter prompt, {REPEATS} timed runs each (ms)\n")
    print(f"{'':45} {'first token (any)':>22}   {'first visible text':>24}")
    print(f"{'':45} {'median':>8} {'range':>13}   {'median':>8} {'range':>13}")
    for row in rows:
        errors = f"  errors: {dict(row.errors)}" if row.errors else ""
        print(
            f"{row.name:45} {median(row.first_any):>8} {span(row.first_any):>13}"
            f"   {median(row.first_text):>8} {span(row.first_text):>13}{errors}"
        )
    print("\nSample replies (last timed run):")
    for row in rows:
        print(f"  {row.name}: {row.sample.strip()[:120]!r}")


if __name__ == "__main__":
    asyncio.run(main())
