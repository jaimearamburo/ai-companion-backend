"""Bot definitions as loaded from the database."""

from collections.abc import Mapping
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from companion.contracts._base import BotSlug, Contract, PresetName, Seq, Text, has_duplicates
from companion.contracts.tools import ToolName

type VoiceId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class MemoryPolicy(Contract):
    """How a bot uses the user's memories."""

    cheat_sheet_max_facts: int = Field(default=20, ge=1, le=100)
    # Whether the bot may look up another bot's memories once the user agrees.
    shares_on_request: bool = True


class BotSafetyRules(Contract):
    """Per-bot safety settings layered on the global safety gate."""

    banter_on_sensitive_turns: bool = False


class BotDefinition(Contract):
    """One version of one bot. Edits create a new version; old ones never change."""

    id: UUID
    # The bot_versions row: releases and session_bots pin this ID.
    version_id: UUID
    version: int = Field(ge=1)
    slug: BotSlug
    display_name: Annotated[Text, StringConstraints(max_length=60)]
    persona_prompt: Annotated[Text, StringConstraints(max_length=4000)]
    ui_description: Annotated[str, StringConstraints(max_length=500)] = ""
    avatar_url: Annotated[str, StringConstraints(pattern=r"^https://\S+$")] | None = None
    # Voice per TTS preset, because each TTS vendor has its own voice IDs and the
    # TTS vendor is chosen per region.
    voices: Mapping[PresetName, VoiceId] = Field(min_length=1)
    allowed_tools: Seq[ToolName] = ()
    memory: MemoryPolicy = MemoryPolicy()
    safety: BotSafetyRules = BotSafetyRules()
    is_active: bool = True

    @model_validator(mode="after")
    def _tools_unique(self) -> Self:
        if has_duplicates(self.allowed_tools):
            raise ValueError("allowed_tools lists a tool more than once")
        return self
