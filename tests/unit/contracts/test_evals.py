"""Eval scenarios load from YAML-shaped data; results stay internally consistent."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from companion.contracts import EvalRunResult, EvalScenario


def scenario(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "remembers-sister-visit",
        "title": "Remembers a family visit across calls",
        "bots": ["gary"],
        "user_persona": "Chatty, mentions family often.",
        "sessions": [
            {"user_instructions": "Mention that your sister Anne visits next Saturday."},
            {"user_instructions": "Ask Gary who is visiting this weekend.", "max_turns": 6},
        ],
        "expected": {
            "memories_present": ["Anne"],
            "tool_calls": [{"name": "recall_memory", "arguments": {}}],
        },
    }
    data.update(changes)
    return data


def test_scenario_loads_from_lists() -> None:
    loaded = EvalScenario.model_validate(scenario())
    assert len(loaded.sessions) == 2
    assert loaded.expected.memories_present == ("Anne",)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "Remembers Sister"},
        {"bots": []},
        {"bots": ["gary", "gary"]},
        {"sessions": []},
        {"expected": {}},
        {"expected": {"tool_calls": [{"name": "drop_table"}]}},
        {"expected": {"safety_actions": ["rude"]}},
        {"sessions": [{"user_instructions": "Talk", "max_turns": 0}]},
    ],
)
def test_malformed_scenario_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EvalScenario.model_validate(scenario(**changes))


def result(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "scenario_id": "remembers-sister-visit",
        "attempt": 1,
        "passed": True,
        "seed": 7,
        "models": {"scriptwriter": "gpt-oss-120b"},
        "started_at": datetime(2026, 10, 18, tzinfo=UTC),
        "duration_s": 12.5,
    }
    data.update(changes)
    return data


def test_result_passed_matches_failures() -> None:
    assert EvalRunResult.model_validate(result()).passed
    failed = result(passed=False, failures=["no active memory mentions Anne"])
    assert EvalRunResult.model_validate(failed).failures


@pytest.mark.parametrize(
    "changes",
    [
        {"passed": True, "failures": ["something"]},
        {"passed": False},
        {"attempt": 0},
        {"started_at": datetime(2026, 10, 18)},
        {"duration_s": -1.0},
    ],
)
def test_inconsistent_result_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EvalRunResult.model_validate(result(**changes))
