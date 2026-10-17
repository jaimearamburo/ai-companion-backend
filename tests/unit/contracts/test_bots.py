"""Bot definitions are validated as they're loaded from database rows."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from companion.contracts import BotDefinition


def row(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": uuid4(),
        "version": 1,
        "slug": "gary",
        "display_name": "Gary",
        "persona_prompt": "A cheerful gardener who loves to talk about tomatoes.",
        "voices": {"fish_s21_hosted": "933563129e564b19a115bedd57b7406a"},
        "allowed_tools": ["recall_memory", "list_memories"],
    }
    data.update(changes)
    return data


def test_valid_row_loads_with_defaults() -> None:
    bot = BotDefinition.model_validate(row())
    assert bot.allowed_tools == ("recall_memory", "list_memories")
    assert bot.memory.cheat_sheet_max_facts == 20
    assert bot.safety.banter_on_sensitive_turns is False
    assert bot.is_active


@pytest.mark.parametrize(
    "changes",
    [
        {"slug": "Gary"},
        {"slug": "gary_smith"},
        {"version": 0},
        {"display_name": "   "},
        {"voices": {}},
        {"voices": {"Fish Hosted": "abc"}},
        {"allowed_tools": ["delete_user"]},
        {"allowed_tools": ["recall_memory", "recall_memory"]},
        {"avatar_url": "http://example.com/gary.png"},
        {"id": "5b1c2a0e-3f4d-4c5b-9a6e-7d8f9a0b1c2d"},
        {"is_active": "yes"},
        {"memory": {"cheat_sheet_max_facts": 0}},
        {"unknown_column": 1},
    ],
)
def test_malformed_row_fails_loudly(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BotDefinition.model_validate(row(**changes))
