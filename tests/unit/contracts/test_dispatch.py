"""Dispatch metadata arrives as a JSON string from the frontend."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from companion.contracts import DispatchMetadata

USER = "5b1c2a0e-3f4d-4c5b-9a6e-7d8f9a0b1c2d"
BOT_A = "0f8e2d1c-4b3a-4c2d-8e1f-2a3b4c5d6e7f"
BOT_B = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"


def valid() -> dict[str, Any]:
    return {
        "user_id": USER,
        "region": "au",
        "bots": [BOT_A, BOT_B],
        "memory_deletion_enabled": False,
        "presets": {
            "stt": "deepgram_nova3_au",
            "tts": "fish_s21_hosted",
            "llm": "bedrock_gptoss120b_syd",
            "safety": "groq_safeguard20b",
            "turn_detector": "livekit_v1_mini",
            "speculative_trigger": "auto",
        },
    }


def test_valid_metadata_parses_from_json() -> None:
    metadata = DispatchMetadata.model_validate_json(json.dumps(valid()))
    assert metadata.region == "au"
    assert len(metadata.bots) == 2
    assert metadata.presets.turn_detector == "livekit_v1_mini"


def change(path: str, value: Any) -> dict[str, Any]:
    data = valid()
    target = data
    *parents, last = path.split(".")
    for key in parents:
        target = target[key]
    if value is DELETE:
        del target[last]
    else:
        target[last] = value
    return data


DELETE = object()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("region", "eu"),
        ("user_id", "not-a-uuid"),
        ("bots", []),
        ("bots", [BOT_A, BOT_A]),
        ("memory_deletion_enabled", "false"),
        ("presets.llm", "Bedrock GPT"),
        ("presets.stt", DELETE),
        ("extra_field", 1),
    ],
)
def test_malformed_metadata_is_rejected(path: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        DispatchMetadata.model_validate_json(json.dumps(change(path, value), default=str))


def test_metadata_is_immutable() -> None:
    metadata = DispatchMetadata.model_validate_json(json.dumps(valid()))
    with pytest.raises(ValidationError):
        metadata.region = "us"  # type: ignore[misc]
