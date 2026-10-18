"""A stored bot definition is validated, and errors name the bot and the problem."""

from typing import Any
from uuid import uuid4

import pytest

from companion.bots import InvalidBotError, bot_from_row


def row(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": uuid4(),
        "version_id": uuid4(),
        "version": 3,
        "slug": "gary",
        "display_name": "Gary",
        "ui_description": "",
        "avatar_url": None,
        "is_active": True,
        "persona_prompt": "A cheerful gardener.",
        "voices": {"fish_s21_hosted": "voice-gary"},
        "allowed_tools": ["recall_memory"],
        "memory": {},
        "safety": {},
    }
    data.update(changes)
    return data


def test_database_row_becomes_a_definition_with_defaults() -> None:
    bot = bot_from_row(row())
    assert bot.version == 3
    assert bot.memory.cheat_sheet_max_facts == 20


def test_invalid_row_names_the_bot_and_each_problem() -> None:
    with pytest.raises(InvalidBotError) as caught:
        bot_from_row(row(allowed_tools=["delete_user"], voices={}))
    message = str(caught.value)
    assert "gary version 3" in message
    assert "allowed_tools.0" in message
    assert "voices" in message
