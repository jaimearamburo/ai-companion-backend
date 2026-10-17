"""Eval scenarios and results.

A scenario tells a simulated user what to do across one or more sessions, and
states the end state that must hold afterwards. Scoring checks that end state,
never the wording of the conversation.
"""

from collections.abc import Mapping
from typing import Annotated, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from companion.contracts._base import BotSlug, Contract, Seq, Text, has_duplicates
from companion.contracts.safety import SafetyCategory
from companion.contracts.tools import ToolName

type ScenarioId = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)
]
type JsonScalar = str | int | float | bool | None


class ExpectedToolCall(Contract):
    """A tool call that must have happened, with at least these arguments."""

    name: ToolName
    arguments: Mapping[str, JsonScalar] = {}


class ExpectedEndState(Contract):
    """What must be true after every session of the scenario has run."""

    # Text that must appear in some active memory, and text that must not.
    memories_present: Seq[Text] = ()
    memories_absent: Seq[Text] = ()
    tool_calls: Seq[ExpectedToolCall] = ()
    safety_actions: Seq[SafetyCategory] = ()

    @model_validator(mode="after")
    def _checks_something(self) -> Self:
        if not (
            self.memories_present or self.memories_absent or self.tool_calls or self.safety_actions
        ):
            raise ValueError("an expected end state must check at least one thing")
        return self


class ScenarioSession(Contract):
    """One call in the scenario, from the simulated user's side."""

    user_instructions: Text
    max_turns: int = Field(default=12, ge=1, le=40)


class EvalScenario(Contract):
    id: ScenarioId
    title: Text
    bots: Seq[BotSlug] = Field(min_length=1)
    user_persona: Text
    sessions: Seq[ScenarioSession] = Field(min_length=1)
    expected: ExpectedEndState
    tags: Seq[ScenarioId] = ()

    @model_validator(mode="after")
    def _bots_unique(self) -> Self:
        if has_duplicates(self.bots):
            raise ValueError("a bot is listed more than once")
        return self


class EvalRunResult(Contract):
    """One run of one scenario."""

    scenario_id: ScenarioId
    attempt: int = Field(ge=1)
    passed: bool
    failures: Seq[Text] = ()
    seed: int
    # Model ID per role (scriptwriter, safety, simulated user, ...), for reproducibility.
    models: Mapping[str, str]
    started_at: AwareDatetime
    duration_s: float = Field(ge=0)

    @model_validator(mode="after")
    def _passed_matches_failures(self) -> Self:
        if self.passed == bool(self.failures):
            raise ValueError("a run passes exactly when it has no failures")
        return self
