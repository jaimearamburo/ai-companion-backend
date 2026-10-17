"""Memory records keep their type-specific fields consistent."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from companion.contracts import MemoryRecord

MEMORY_ID = uuid4()
BOT = uuid4()


def record(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": MEMORY_ID,
        "user_id": uuid4(),
        "session_id": uuid4(),
        "type": "core_fact",
        "kind": "event",
        "text": "Their sister is visiting on 25 October 2026.",
        "importance": 7,
        "confidence": 0.9,
        "occurred_at": datetime(2026, 10, 25, tzinfo=UTC),
        "created_at": datetime(2026, 10, 18, tzinfo=UTC),
        "witnesses": [BOT],
    }
    data.update(changes)
    return data


def test_core_fact_and_summary_are_valid() -> None:
    assert MemoryRecord.model_validate(record()).is_active
    summary = record(type="session_summary", kind=None, importance=None)
    assert MemoryRecord.model_validate(summary).type == "session_summary"


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": None},
        {"importance": None},
        {"type": "session_summary"},
        {"importance": 11},
        {"confidence": 1.5},
        {"kind": "opinion"},
        {"created_at": datetime(2026, 10, 18)},
        {"witnesses": []},
        {"witnesses": [BOT, BOT]},
        {"superseded_by": MEMORY_ID},
        {"text": ""},
    ],
)
def test_inconsistent_record_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(record(**changes))
