"""The fakes behave like real providers: streaming, tool calls, failures and delays."""

import time

import pytest

from companion.contracts import SafetyVerdict
from companion.contracts.llm import (
    ChatMessage,
    ChatRequest,
    Finished,
    TextDelta,
    ToolCall,
    ToolCallEvent,
)
from companion.providers import ChatModel, SafetyClassifier
from companion.providers.fakes import (
    FakeChatModel,
    FakeSafetyClassifier,
    ScriptedReply,
    ScriptExhaustedError,
)

REQUEST = ChatRequest(messages=(ChatMessage(role="user", content="Hello"),))


async def collect(model: ChatModel, request: ChatRequest) -> list[object]:
    return [event async for event in model.stream(request)]


async def test_streams_text_in_chunks_then_finishes() -> None:
    model = FakeChatModel([ScriptedReply(text="Hello there, friend!")], chunk_size=6)
    events = await collect(model, REQUEST)
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(texts) == "Hello there, friend!"
    assert len(texts) == 4
    assert isinstance(events[-1], Finished)
    assert events[-1].reason == "stop"
    assert model.requests == [REQUEST]


async def test_tool_calls_end_with_tool_calls_reason() -> None:
    call = ToolCall(id="c1", name="recall_memory", arguments={"query": "sister"})
    model = FakeChatModel([ScriptedReply(tool_calls=(call,))])
    events = await collect(model, REQUEST)
    assert events[0] == ToolCallEvent(call=call)
    last = events[-1]
    assert isinstance(last, Finished)
    assert last.reason == "tool_calls"


async def test_running_out_of_replies_raises() -> None:
    model = FakeChatModel([])
    with pytest.raises(ScriptExhaustedError):
        await collect(model, REQUEST)


async def test_fake_safety_returns_raises_and_delays() -> None:
    classifier: SafetyClassifier = FakeSafetyClassifier(
        [SafetyVerdict(safe=True), None], delay_s=0.05
    )
    started = time.perf_counter()
    assert (await classifier.classify("hi")).safe
    assert time.perf_counter() - started >= 0.05
    with pytest.raises(RuntimeError):
        await classifier.classify("again")


async def test_fake_safety_runs_out_of_verdicts() -> None:
    classifier = FakeSafetyClassifier([])
    with pytest.raises(ScriptExhaustedError):
        await classifier.classify("hi")
