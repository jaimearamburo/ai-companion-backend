"""A safety verdict's category must match whether it is safe."""

from typing import Any

import pytest
from pydantic import ValidationError

from companion.contracts import SafetyVerdict


def test_valid_verdicts() -> None:
    assert SafetyVerdict(safe=True).category is None
    assert SafetyVerdict(safe=False, category="self_harm").category == "self_harm"


@pytest.mark.parametrize(
    "data",
    [
        {"safe": True, "category": "medical_advice"},
        {"safe": False},
        {"safe": False, "category": "rude"},
        {"safe": "false"},
        {"safe": True, "reason": "fine"},
    ],
)
def test_malformed_verdict_is_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SafetyVerdict.model_validate(data)
