"""Inputs and outputs of the tools the agent can call.

Tool inputs never carry user or bot IDs: the tool server takes them from the
session, so the model cannot ask for another user's data. Unknown fields,
such as a model-supplied `user_id`, are rejected.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

from companion.contracts._base import BotSlug, Contract, Seq, Text

type ToolName = Literal["recall_memory", "list_memories", "forget_memory"]

type Query = Annotated[Text, StringConstraints(max_length=300)]


class RecallMemoryInput(Contract):
    """Search the user's memories that the calling bot may see."""

    query: Query
    # Another bot whose memories to search; only after the user has agreed.
    other_bot: BotSlug | None = None


class ListMemoriesInput(Contract):
    """List the user's active memories that the calling bot may see."""


class ForgetMemoryInput(Contract):
    """Deactivate one memory returned earlier in this call."""

    memory_id: UUID


class MemoryItem(Contract):
    """One memory as returned to the model."""

    memory_id: UUID
    text: Text
    occurred_at: AwareDatetime | None = None


class RecallMemoryOutput(Contract):
    memories: Seq[MemoryItem] = Field(max_length=5)


class ListMemoriesOutput(Contract):
    memories: Seq[MemoryItem] = Field(max_length=50)


class ForgetMemoryOutput(Contract):
    forgotten: bool


type ToolErrorCode = Literal[
    "invalid_arguments", "not_found", "not_allowed", "timeout", "unavailable"
]


class ToolError(Contract):
    """A failure the model can read and recover from, instead of an exception."""

    code: ToolErrorCode
    message: Annotated[Text, StringConstraints(max_length=300)]
    retryable: bool
