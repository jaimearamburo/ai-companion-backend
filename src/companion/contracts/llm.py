"""Vendor-neutral shapes for talking to a chat LLM.

Every LLM adapter translates these to and from its vendor's API, so the agent
runtime never sees a vendor-specific type.
"""

from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, StringConstraints, model_validator

from companion.contracts._base import Contract, Seq

type ToolSpecName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class ToolSpec(Contract):
    """A tool offered to the model: its name, purpose and JSON Schema for arguments."""

    name: ToolSpecName
    description: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    parameters: Mapping[str, JsonValue]


class ToolCall(Contract):
    """The model asking for a tool to be run."""

    id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    name: ToolSpecName
    arguments: Mapping[str, JsonValue]


class ChatMessage(Contract):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    # Set on assistant messages that requested tools.
    tool_calls: Seq[ToolCall] = ()
    # Set on tool messages: which call this result answers.
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages carry tool calls")
        if (self.role == "tool") != (self.tool_call_id is not None):
            raise ValueError("tool messages, and only tool messages, carry a tool_call_id")
        return self


class ChatRequest(Contract):
    messages: Seq[ChatMessage] = Field(min_length=1)
    tools: Seq[ToolSpec] = ()
    # "none" forces a final answer, e.g. once the tool-call limit is reached.
    tool_choice: Literal["auto", "none"] = "auto"
    max_output_tokens: int = Field(default=512, ge=1, le=8192)
    # Reasoning stays on; only its effort is configurable.
    reasoning_effort: Literal["low", "medium", "high"] = "low"


class TokenUsage(Contract):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class TextDelta(Contract):
    type: Literal["text"] = "text"
    text: str


class ToolCallEvent(Contract):
    type: Literal["tool_call"] = "tool_call"
    call: ToolCall


class Finished(Contract):
    type: Literal["finished"] = "finished"
    reason: Literal["stop", "tool_calls", "length"]
    usage: TokenUsage


type ChatEvent = Annotated[TextDelta | ToolCallEvent | Finished, Field(discriminator="type")]
"""One item of a streamed reply: text as it arrives, a tool call, or the end."""
