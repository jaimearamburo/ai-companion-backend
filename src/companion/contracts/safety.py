"""The safety model's verdict on a user turn.

Parsing the model's raw output and failing closed on errors or timeouts is the
safety gate's job; this is the shape a valid verdict must have.
"""

from typing import Literal, Self

from pydantic import model_validator

from companion.contracts._base import Contract

# Provisional; the final list and its actions are fixed in the safety gate's ADR.
type SafetyCategory = Literal[
    "self_harm", "medical_advice", "violence", "sexual_content", "illegal_activity", "other"
]


class SafetyVerdict(Contract):
    safe: bool
    category: SafetyCategory | None = None

    @model_validator(mode="after")
    def _category_matches(self) -> Self:
        if self.safe and self.category is not None:
            raise ValueError("a safe verdict has no category")
        if not self.safe and self.category is None:
            raise ValueError("an unsafe verdict needs a category")
        return self
