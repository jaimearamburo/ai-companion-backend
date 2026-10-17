"""Memory records as stored in and read from the database."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from companion.contracts._base import Contract, Seq, Text, has_duplicates

type MemoryType = Literal["core_fact", "session_summary"]
type MemoryKind = Literal["fact", "preference", "event"]


class MemoryRecord(Contract):
    """One memory with the bots that witnessed it."""

    id: UUID
    user_id: UUID
    session_id: UUID | None
    type: MemoryType
    kind: MemoryKind | None = None
    text: Annotated[Text, StringConstraints(max_length=2000)]
    importance: int | None = Field(default=None, ge=1, le=10)
    confidence: float | None = Field(default=None, ge=0, le=1)
    occurred_at: AwareDatetime | None = None
    created_at: AwareDatetime
    is_active: bool = True
    superseded_by: UUID | None = None
    witnesses: Seq[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.type == "core_fact" and (self.kind is None or self.importance is None):
            raise ValueError("a core fact needs a kind and an importance")
        if self.type == "session_summary" and (
            self.kind is not None or self.importance is not None
        ):
            raise ValueError("a session summary has no kind or importance")
        if self.superseded_by == self.id:
            raise ValueError("a memory cannot supersede itself")
        if has_duplicates(self.witnesses):
            raise ValueError("a bot is listed as a witness more than once")
        return self
