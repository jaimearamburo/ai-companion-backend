"""Dispatch metadata: what the frontend sends when it starts a call."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from companion.contracts._base import Contract, PresetName, Seq, has_duplicates

type Region = Literal["au", "us"]
# Matches the user_role enum: admins (developers) may put any number of bots in a call.
type UserRole = Literal["admin", "user"]


class Presets(Contract):
    """The provider preset chosen for each selectable layer."""

    stt: PresetName
    tts: PresetName
    llm: PresetName
    safety: PresetName
    turn_detector: PresetName
    speculative_trigger: PresetName


class DispatchMetadata(Contract):
    """The JSON the frontend puts in `createDispatch(...)`'s metadata.

    Parse it with `DispatchMetadata.model_validate_json(ctx.job.metadata)`.
    The per-role bot limit needs the user's role from the database, so it is
    checked at session start, not here.
    """

    user_id: UUID
    region: Region
    bots: Seq[UUID] = Field(min_length=1)
    memory_deletion_enabled: bool
    presets: Presets

    @model_validator(mode="after")
    def _bots_unique(self) -> Self:
        if has_duplicates(self.bots):
            raise ValueError("a bot can only be in a call once")
        return self
