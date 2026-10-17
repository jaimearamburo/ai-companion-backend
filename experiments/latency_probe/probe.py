"""Latency probe: measures how fast each external service responds from this machine.

Run with:  uv run --group experiments python experiments/latency_probe/probe.py

What it measures (each several times, reporting min / median / max):
  1. Network round trip (TCP connect time, with DNS resolved beforehand) to every
     service host — pure distance, which also hints at where a service is served from.
  2. LLM time to first token for GPT-OSS-120B (scriptwriter) and GPT-OSS-Safeguard-20B
     (safety), on Groq and on Amazon Bedrock (Sydney): both the first token of any kind
     (including the model's brief internal reasoning) and the first visible text.
  3. Deepgram STT request time on the Australian endpoint vs the global one.
  3b. Fish Audio TTS time to first audio (hosted S2.1, free model), which shows the
     real cost of Fish serving from outside Australia.
  4. Redis (Upstash) PING and Postgres (Supabase) ``SELECT 1`` round trips over an
     already-open connection, plus the one-off connection setup time.

It reuses the application's settings loader, so it reads the same ``.env``. It
never prints secrets or full hostnames (some contain project identifiers).
Every operation has a timeout; a failure is recorded and the probe carries on.
Cost per run is a fraction of a cent.
"""

import asyncio
import io
import math
import socket
import statistics
import struct
import time
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from urllib.parse import urlsplit

import httpx
import psycopg
import redis.asyncio as redis_async
from openai import APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from companion.config import Settings, load_settings

REPEATS = 7  # timed repetitions per measurement, after one untimed warm-up
TIMEOUT_S = 30.0  # upper bound for any single operation

# The same short exchange for every LLM, so hosts are compared like for like.
SCRIPT_SYSTEM = "You are Gary, a warm, chatty companion. Reply with one short spoken sentence."
SAFETY_SYSTEM = (
    "Classify the user's message. Answer with exactly one word: SAFE, or UNSAFE if it "
    "asks for medical advice or mentions self-harm."
)
USER_LINE = "I was just thinking about my sister coming to visit this weekend, isn't that nice."
LLM_PAUSE_S = 2.0  # spacing between LLM requests, to stay under Groq's free-tier rate limits

FISH_TTS_URL = "https://api.fish.audio/v1/tts"
FISH_MODEL = "s2.1-pro-free"  # the free hosted S2.1 model (free until 30 Nov 2026)
FISH_VOICE = "933563129e564b19a115bedd57b7406a"  # default voice of LiveKit's Fish plugin
FISH_LINE = "That sounds lovely, mate. How long is your sister staying?"


@dataclass
class Result:
    """One measurement row: a name, the timings collected, and any errors."""

    name: str
    samples_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    note: str = ""

    def summary(self) -> str:
        if not self.samples_ms:
            return f"{self.name:52} FAILED  {'; '.join(sorted(set(self.errors)))}"
        values = sorted(self.samples_ms)
        text = (
            f"{self.name:52} min {values[0]:7.1f}  median {statistics.median(values):7.1f}"
            f"  max {values[-1]:7.1f} ms"
        )
        if self.errors:
            text += f"  ({len(self.errors)} errors)"
        if self.note:
            text += f"  [{self.note}]"
        return text


async def repeat(result: Result, operation: Callable[[], Awaitable[float]]) -> Result:
    """Run one warm-up, then time the operation REPEATS times.

    ``operation`` returns the milliseconds it measured itself (so each
    measurement decides exactly what it times). Exceptions are recorded by
    type only, because some exception messages can contain connection details.
    """
    for attempt in range(REPEATS + 1):
        try:
            elapsed = await asyncio.wait_for(operation(), timeout=TIMEOUT_S)
        except TimeoutError:
            result.errors.append("timeout")
            continue
        except APIStatusError as error:
            result.errors.append(f"HTTP {error.status_code}")
            continue
        # Any failure is data here, not a crash: record it and keep measuring.
        except Exception as error:
            result.errors.append(type(error).__name__)
            continue
        if attempt > 0:  # attempt 0 is the warm-up
            result.samples_ms.append(elapsed)
    return result


def ms_since(start: float) -> float:
    return (time.perf_counter() - start) * 1000


# --- 1. Network round trip -------------------------------------------------


async def tcp_connect_ms(address: str, port: int) -> float:
    """Time to open a TCP connection to an already-resolved IP address.

    Resolving the hostname (DNS) is done once, beforehand: a DNS lookup can take
    tens of milliseconds and would otherwise be counted as network distance.
    """
    start = time.perf_counter()
    _reader, writer = await asyncio.open_connection(address, port)
    elapsed = ms_since(start)
    writer.close()
    await writer.wait_closed()
    return elapsed


async def resolve(host: str, port: int) -> str:
    """Look up a hostname's first IP address (the DNS step, done outside timing)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return str(infos[0][4][0])


def host_and_port(url: str, default_port: int) -> tuple[str, int]:
    parts = urlsplit(url)
    return parts.hostname or "", parts.port or default_port


# --- 2. LLM time to first token --------------------------------------------


@dataclass(frozen=True)
class LlmTarget:
    label: str
    base_url: str
    api_key: str
    model: str
    system: str


def has_reasoning(delta: object) -> bool:
    """Whether a streamed chunk carries reasoning text.

    Hosts return GPT-OSS reasoning under non-standard field names ("reasoning"
    on Groq, "reasoning_content" elsewhere), which the SDK keeps in model_extra.
    """
    extra = getattr(delta, "model_extra", None) or {}
    return any(extra.get(name) for name in ("reasoning", "reasoning_content"))


async def llm_first_token_ms(
    client: AsyncOpenAI, target: LlmTarget, result: Result, first_any: Result
) -> float:
    """Stream one reply; return time to the first visible text token.

    Also appends, to ``first_any``, the time to the first token of any kind
    (reasoning or text) — the gap between the two is the model's thinking time.

    GPT-OSS models "think" briefly before answering (reasoning tokens), so the
    first visible token is what matters for speech. Reasoning effort is set to
    low, matching the spec; if a host rejects that parameter the request is
    retried without it and the row is annotated.
    """
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": target.system},
        {"role": "user", "content": USER_LINE},
    ]
    await asyncio.sleep(LLM_PAUSE_S)  # before the clock starts, so not measured
    start = time.perf_counter()
    try:
        stream = await client.chat.completions.create(
            model=target.model,
            messages=messages,
            max_tokens=300,
            stream=True,
            reasoning_effort="low",
        )
    except APIStatusError as error:
        if error.status_code != 400:
            raise
        result.note = "reasoning_effort not accepted; host default used"
        start = time.perf_counter()
        stream = await client.chat.completions.create(
            model=target.model,
            messages=messages,
            max_tokens=300,
            stream=True,
        )
    first_text_ms: float | None = None
    first_any_ms: float | None = None
    async for chunk in stream:
        # Some chunks carry no choices (e.g. usage or keep-alive chunks).
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if first_any_ms is None and (delta.content or has_reasoning(delta)):
            first_any_ms = ms_since(start)
        if first_text_ms is None and delta.content:
            first_text_ms = ms_since(start)
    if first_any_ms is not None:
        first_any.samples_ms.append(first_any_ms)
    if first_text_ms is None:
        raise RuntimeError("no visible text returned")
    return first_text_ms


# --- 3. Deepgram -------------------------------------------------------------


def one_second_tone_wav() -> bytes:
    """A 1-second 440 Hz tone as a WAV file, generated in memory.

    Real speech isn't needed to time the round trip; Deepgram processes the
    audio either way (and returns an empty transcript for a tone).
    """
    rate = 16_000
    samples = (int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit samples
        wav.setframerate(rate)
        wav.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    return buffer.getvalue()


async def deepgram_request_ms(http: httpx.AsyncClient, base: str, key: str, audio: bytes) -> float:
    start = time.perf_counter()
    response = await http.post(
        f"{base}/v1/listen",
        params={"model": "nova-3"},
        headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
        content=audio,
    )
    response.raise_for_status()
    return ms_since(start)


# --- 3b. Fish Audio TTS -----------------------------------------------------


async def fish_first_audio_ms(
    http: httpx.AsyncClient, key: str, latency_mode: str, edges: set[str]
) -> float:
    """Request speech for one short line; return time to the first audio bytes.

    Fish streams the audio as it's generated, so the first bytes are what
    playback would wait for. The request is abandoned once they arrive. The
    ``cf-ray`` header ends with the code of the Cloudflare site that answered
    (e.g. "-SYD"), recorded to show where the connection entered Fish's network.
    """
    start = time.perf_counter()
    async with http.stream(
        "POST",
        FISH_TTS_URL,
        headers={"Authorization": f"Bearer {key}", "model": FISH_MODEL},
        json={
            "text": FISH_LINE,
            "reference_id": FISH_VOICE,
            "format": "pcm",  # raw audio: no encoder delay on Fish's side
            "latency": latency_mode,
        },
    ) as response:
        response.raise_for_status()
        edges.add(response.headers.get("cf-ray", "?-?").rsplit("-", 1)[-1])
        async for chunk in response.aiter_bytes():
            if chunk:
                return ms_since(start)
    raise RuntimeError("no audio returned")


# --- The run -----------------------------------------------------------------


async def main() -> None:
    settings: Settings = load_settings()
    results: list[Result] = []

    # 1. Network round trips. Hosts are labelled by service, never printed.
    bedrock_host = f"bedrock-runtime.{settings.bedrock_region}.amazonaws.com"
    hosts = {
        "LiveKit Cloud": host_and_port(settings.livekit_url, 443),
        "Groq API": ("api.groq.com", 443),
        f"Bedrock ({settings.bedrock_region})": (bedrock_host, 443),
        "Deepgram Australian endpoint": ("api.au.deepgram.com", 443),
        "Deepgram global endpoint": ("api.deepgram.com", 443),
        "Fish API (Cloudflare edge)": ("api.fish.audio", 443),
        "Redis (Upstash)": host_and_port(settings.redis_url.get_secret_value(), 6379),
        "Postgres (Supabase)": host_and_port(settings.supabase_db_url.get_secret_value(), 5432),
    }
    for label, (host, port) in hosts.items():
        row = Result(f"network round trip: {label}")
        try:
            address = await asyncio.wait_for(resolve(host, port), timeout=TIMEOUT_S)
        except Exception as error:
            row.errors.append(f"DNS {type(error).__name__}")
            results.append(row)
            continue
        results.append(await repeat(row, partial(tcp_connect_ms, address, port)))

    # 2. LLMs: both models on both hosts.
    groq_url = "https://api.groq.com/openai/v1"
    bedrock_url = f"https://{bedrock_host}/openai/v1"
    groq_key = settings.groq_api_key.get_secret_value()
    bedrock_key = settings.bedrock_api_key.get_secret_value()
    targets = [
        LlmTarget("Groq gpt-oss-120b", groq_url, groq_key, "openai/gpt-oss-120b", SCRIPT_SYSTEM),
        LlmTarget(
            "Bedrock gpt-oss-120b",
            bedrock_url,
            bedrock_key,
            "openai.gpt-oss-120b-1:0",
            SCRIPT_SYSTEM,
        ),
        # 20b as a reference point: same family, half the size, twice the speed.
        LlmTarget("Groq gpt-oss-20b", groq_url, groq_key, "openai/gpt-oss-20b", SCRIPT_SYSTEM),
        LlmTarget(
            "Bedrock gpt-oss-20b",
            bedrock_url,
            bedrock_key,
            "openai.gpt-oss-20b-1:0",
            SCRIPT_SYSTEM,
        ),
        LlmTarget(
            "Groq safeguard-20b", groq_url, groq_key, "openai/gpt-oss-safeguard-20b", SAFETY_SYSTEM
        ),
        LlmTarget(
            "Bedrock safeguard-20b",
            bedrock_url,
            bedrock_key,
            "openai.gpt-oss-safeguard-20b",
            SAFETY_SYSTEM,
        ),
    ]
    for target in targets:
        # One client per target keeps its connection open between repetitions,
        # as the real agent would, so timings exclude connection setup.
        # max_retries=0: the SDK otherwise retries rate-limited requests silently,
        # which would show up as extra latency instead of as errors.
        async with AsyncOpenAI(
            base_url=target.base_url, api_key=target.api_key, max_retries=0
        ) as client:
            row = Result(f"LLM first visible text: {target.label}")
            any_row = Result(f"LLM first token (any): {target.label}")
            await repeat(
                row,
                partial(llm_first_token_ms, client, target, row, any_row),
            )
            # The warm-up's "any" sample is recorded too (unless the warm-up failed);
            # drop it so both rows cover the same timed runs.
            if len(any_row.samples_ms) > len(row.samples_ms):
                any_row.samples_ms = any_row.samples_ms[1:]
            results.extend([any_row, row])

    # 3. Deepgram, Australian vs global endpoint.
    audio = one_second_tone_wav()
    deepgram_key = settings.deepgram_api_key.get_secret_value()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as http:
        for label, base in (
            ("Australian", "https://api.au.deepgram.com"),
            ("global", "https://api.deepgram.com"),
        ):
            results.append(
                await repeat(
                    Result(f"Deepgram 1s-audio request: {label} endpoint"),
                    partial(deepgram_request_ms, http, base, deepgram_key, audio),
                )
            )

    # 3b. Fish TTS, at two of its speed/quality settings.
    fish_key = settings.fish_api_key.get_secret_value()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as http:
        for latency_mode in ("low", "balanced"):
            edges: set[str] = set()
            row = Result(f"Fish TTS first audio: S2.1, latency={latency_mode}")
            await repeat(
                row,
                partial(fish_first_audio_ms, http, fish_key, latency_mode, edges),
            )
            row.note = f"entered via Cloudflare {'/'.join(sorted(edges))}"
            results.append(row)

    # 4. Redis and Postgres over an already-open connection, plus setup time.
    redis_client = redis_async.from_url(settings.redis_url.get_secret_value())
    start = time.perf_counter()
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=TIMEOUT_S)
        results.append(Result("Redis connection setup (one-off)", [ms_since(start)]))

        async def redis_ping_ms() -> float:
            t0 = time.perf_counter()
            await redis_client.ping()
            return ms_since(t0)

        results.append(await repeat(Result("Redis PING (open connection)"), redis_ping_ms))
    except Exception as error:
        results.append(Result("Redis", errors=[type(error).__name__]))
    finally:
        await redis_client.aclose()

    start = time.perf_counter()
    try:
        # prepare_threshold=None disables prepared statements, as required behind
        # Supabase's transaction pooler; harmless on a direct/session connection.
        connection = await asyncio.wait_for(
            psycopg.AsyncConnection.connect(
                settings.supabase_db_url.get_secret_value(), prepare_threshold=None
            ),
            timeout=TIMEOUT_S,
        )
        results.append(Result("Postgres connection setup (one-off)", [ms_since(start)]))
        async with connection:

            async def select_one_ms() -> float:
                t0 = time.perf_counter()
                await connection.execute("SELECT 1")
                return ms_since(t0)

            select_row = Result("Postgres SELECT 1 (open connection)")
            results.append(await repeat(select_row, select_one_ms))
    except Exception as error:
        results.append(Result("Postgres", errors=[type(error).__name__]))

    print(f"\nLatency probe — {REPEATS} timed runs each after one warm-up\n")
    for row in results:
        print(row.summary())


if __name__ == "__main__":
    asyncio.run(main())
