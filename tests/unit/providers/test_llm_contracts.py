"""Chat messages keep tool-call fields consistent; streamed events parse by type."""

import pytest
from pydantic import TypeAdapter, ValidationError

from companion.contracts.llm import ChatEvent, ChatMessage, ChatRequest, ToolCallEvent

EVENTS: TypeAdapter[ChatEvent] = TypeAdapter(ChatEvent)


def test_event_parses_by_type() -> None:
    event = EVENTS.validate_json(
        '{"type": "tool_call", "call": {"id": "c1", "name": "recall_memory", "arguments": {}}}'
    )
    assert isinstance(event, ToolCallEvent)


@pytest.mark.parametrize(
    "message",
    [
        {"role": "user", "content": "x", "tool_calls": [{"id": "c", "name": "t", "arguments": {}}]},
        {"role": "tool", "content": "result"},
        {"role": "user", "content": "x", "tool_call_id": "c1"},
        {"role": "robot", "content": "x"},
    ],
)
def test_inconsistent_message_is_rejected(message: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatMessage.model_validate(message)


def test_request_needs_a_message_and_valid_limits() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=())
    with pytest.raises(ValidationError):
        ChatRequest(messages=(ChatMessage(role="user", content="x"),), max_output_tokens=0)
