"""Scripted stand-ins for real providers, used by tests, evals and the text CLI."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from companion.contracts import SafetyVerdict
from companion.contracts.llm import (
    ChatEvent,
    ChatRequest,
    Finished,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallEvent,
)


@dataclass(frozen=True, slots=True)
class ScriptedReply:
    """One reply the fake will give: text, tool calls, or both."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class ScriptExhaustedError(Exception):
    """The fake was asked for more replies than it was given."""


@dataclass
class FakeChatModel:
    """Replays scripted replies in order and records every request it receives."""

    replies: Sequence[ScriptedReply]
    preset: str = "fake_llm"
    # Split text into chunks of this many characters, to exercise streaming.
    chunk_size: int = 8
    requests: list[ChatRequest] = field(default_factory=list)

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.requests.append(request)
        index = len(self.requests) - 1
        if index >= len(self.replies):
            raise ScriptExhaustedError(f"no scripted reply for request {index + 1}")
        reply = self.replies[index]
        for start in range(0, len(reply.text), self.chunk_size):
            yield TextDelta(text=reply.text[start : start + self.chunk_size])
        for call in reply.tool_calls:
            yield ToolCallEvent(call=call)
        yield Finished(
            reason="tool_calls" if reply.tool_calls else "stop",
            usage=TokenUsage(
                prompt_tokens=len(request.messages), completion_tokens=len(reply.text)
            ),
        )


@dataclass
class FakeSafetyClassifier:
    """Returns scripted verdicts; a verdict of None raises, and a delay simulates a slow model."""

    verdicts: Sequence[SafetyVerdict | None]
    preset: str = "fake_safety"
    delay_s: float = 0.0
    texts: list[str] = field(default_factory=list)

    async def classify(self, text: str) -> SafetyVerdict:
        self.texts.append(text)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        index = len(self.texts) - 1
        if index >= len(self.verdicts):
            raise ScriptExhaustedError(f"no scripted verdict for call {index + 1}")
        verdict = self.verdicts[index]
        if verdict is None:
            raise RuntimeError("scripted safety failure")
        return verdict
