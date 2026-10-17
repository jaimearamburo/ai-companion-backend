"""Tool contracts reject bad arguments, including any attempt to choose the user."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from companion.contracts import (
    ForgetMemoryInput,
    ListMemoriesInput,
    RecallMemoryInput,
    RecallMemoryOutput,
    ToolError,
)


def test_valid_tool_inputs() -> None:
    assert RecallMemoryInput.model_validate_json('{"query": "sister visit"}').other_bot is None
    assert ListMemoriesInput.model_validate_json("{}") == ListMemoriesInput()
    forget = '{"memory_id": "5b1c2a0e-3f4d-4c5b-9a6e-7d8f9a0b1c2d"}'
    assert ForgetMemoryInput.model_validate_json(forget).memory_id.version == 4


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": "   "},
        {"query": "x" * 301},
        {"query": "sister", "other_bot": "Jason!"},
        {"query": "sister", "user_id": "5b1c2a0e-3f4d-4c5b-9a6e-7d8f9a0b1c2d"},
        {"query": "sister", "bot_id": "gary"},
        {"query": 42},
    ],
)
def test_malformed_recall_arguments_are_rejected(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RecallMemoryInput.model_validate_json(json.dumps(arguments))


def test_list_memories_takes_no_arguments() -> None:
    with pytest.raises(ValidationError):
        ListMemoriesInput.model_validate_json('{"user_id": "someone-else"}')


def test_recall_returns_at_most_five_memories() -> None:
    item = {"memory_id": "5b1c2a0e-3f4d-4c5b-9a6e-7d8f9a0b1c2d", "text": "Likes tomatoes."}
    with pytest.raises(ValidationError):
        RecallMemoryOutput.model_validate_json(json.dumps({"memories": [item] * 6}))


def test_tool_error_codes_are_fixed() -> None:
    error = ToolError(code="not_found", message="No memory with that id.", retryable=False)
    assert error.code == "not_found"
    with pytest.raises(ValidationError):
        ToolError.model_validate({"code": "oops", "message": "x", "retryable": False})
