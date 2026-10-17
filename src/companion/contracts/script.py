"""The scriptwriter's output: who says what, in order.

Structure only. Limits that depend on the call (the speaker must be in the
room, how many bots may speak, whether banter is allowed) are checked by the
agent runtime.
"""

import re
from typing import Annotated, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from companion.contracts._base import BotSlug, Contract, Seq, Text

# Engine-neutral non-verbal cues; each TTS preset translates them to its own markup.
NON_VERBAL_CUES = frozenset({"laugh", "chuckle", "sigh", "gasp", "pause"})
_CUE = re.compile(r"\[([^\[\]]*)\]")


class ScriptLine(Contract):
    """One bot's line, with optional inline cues such as `[laugh]`."""

    bot: BotSlug
    text: Annotated[Text, StringConstraints(max_length=600)]
    # Set when this line cuts in on the previous bot's line (banter).
    interrupts: BotSlug | None = None

    @field_validator("text")
    @classmethod
    def _known_cues(cls, text: str) -> str:
        unknown = {cue for cue in _CUE.findall(text) if cue not in NON_VERBAL_CUES}
        if unknown:
            raise ValueError(f"unknown non-verbal cues: {', '.join(sorted(unknown))}")
        if not _CUE.sub("", text).strip():
            raise ValueError("a line needs words, not only cues")
        return text

    @model_validator(mode="after")
    def _not_self_interrupt(self) -> Self:
        if self.interrupts == self.bot:
            raise ValueError("a bot cannot interrupt itself")
        return self


class Script(Contract):
    """A reply for one user turn."""

    lines: Seq[ScriptLine] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _interruptions_follow_their_target(self) -> Self:
        for previous, line in zip((None, *self.lines), self.lines, strict=False):
            if line.interrupts is None:
                continue
            if previous is None or previous.bot != line.interrupts:
                raise ValueError(
                    f"{line.bot} interrupts {line.interrupts}, who didn't speak just before"
                )
        return self
