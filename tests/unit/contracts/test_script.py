"""The scriptwriter's output is checked for structure before it reaches TTS."""

from typing import Any

import pytest
from pydantic import ValidationError

from companion.contracts import Script


def test_single_line_with_cue() -> None:
    script = Script.model_validate({"lines": [{"bot": "gary", "text": "[chuckle] Oh, lovely!"}]})
    assert script.lines[0].bot == "gary"


def test_banter_interruption_follows_its_target() -> None:
    script = Script.model_validate(
        {
            "lines": [
                {"bot": "gary", "text": "My tomatoes this year are the biggest I've ever"},
                {"bot": "paul", "text": "Hold your horses, young man!", "interrupts": "gary"},
            ]
        }
    )
    assert script.lines[1].interrupts == "gary"


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [{"bot": "gary", "text": "[cough] Hello"}],
        [{"bot": "gary", "text": "[laugh] [sigh]"}],
        [{"bot": "gary", "text": "Hello", "interrupts": "gary"}],
        [{"bot": "gary", "text": "Hello", "interrupts": "paul"}],
        [
            {"bot": "gary", "text": "Hello"},
            {"bot": "paul", "text": "Hi"},
            {"bot": "anne", "text": "Wait", "interrupts": "gary"},
        ],
        [{"bot": "gary", "text": "x" * 601}],
        [{"bot": "gary", "text": "Hi"}] * 7,
        [{"bot": "gary", "text": "Hi", "emotion": "happy"}],
    ],
)
def test_malformed_script_is_rejected(lines: list[dict[str, Any]]) -> None:
    with pytest.raises(ValidationError):
        Script.model_validate({"lines": lines})
