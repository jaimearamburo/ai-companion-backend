"""Tests for structured logging: format, call context and the privacy rule."""

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import structlog

from companion.observability import (
    bind_session_context,
    bind_turn_context,
    clear_call_context,
    configure_logging,
    get_logger,
)


@pytest.fixture(autouse=True)
def reset_logging() -> Iterator[None]:
    """Undo global logging setup after each test so tests can't affect each other.

    Code before ``yield`` runs before the test, code after runs once it ends.
    """
    yield
    clear_call_context()
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def json_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    """Parse every line written to the stream as a JSON object."""
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_json_lines_carry_bound_call_context() -> None:
    stream = io.StringIO()
    configure_logging(render_json=True, stream=stream)
    bind_session_context(session_id="sess-1", presets={"stt": "inworld_stt1"})
    bind_turn_context(turn_id="turn-7")

    get_logger("companion.test").info("bet_fired", bets_this_turn=1)

    (line,) = json_lines(stream)
    assert line["event"] == "bet_fired"
    assert line["level"] == "info"
    assert line["logger"] == "companion.test"
    assert line["session_id"] == "sess-1"
    assert line["turn_id"] == "turn-7"
    assert line["presets"] == {"stt": "inworld_stt1"}
    assert line["bets_this_turn"] == 1
    assert "timestamp" in line


def test_turn_context_is_replaced_not_duplicated() -> None:
    stream = io.StringIO()
    configure_logging(render_json=True, stream=stream)
    bind_turn_context(turn_id="turn-1")
    bind_turn_context(turn_id="turn-2")

    get_logger("companion.test").info("turn_committed")

    assert json_lines(stream)[0]["turn_id"] == "turn-2"


def test_cleared_context_no_longer_appears() -> None:
    stream = io.StringIO()
    configure_logging(render_json=True, stream=stream)
    bind_session_context(session_id="sess-1", presets={})
    clear_call_context()

    get_logger("companion.test").info("call_ended")

    assert "session_id" not in json_lines(stream)[0]


def test_third_party_standard_logging_uses_same_format_and_context() -> None:
    # LiveKit logs through Python's standard logging module, not structlog.
    stream = io.StringIO()
    configure_logging(render_json=True, stream=stream)
    bind_session_context(session_id="sess-1", presets={})

    logging.getLogger("livekit.agents").warning("reconnecting")

    (line,) = json_lines(stream)
    assert line["event"] == "reconnecting"
    assert line["level"] == "warning"
    assert line["logger"] == "livekit.agents"
    assert line["session_id"] == "sess-1"


def test_personal_information_is_dropped_above_debug() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", render_json=True, stream=stream)
    logger = get_logger("companion.test")

    logger.info("transcript_received", pii_transcript="I told my doctor", characters=16)
    logger.debug("transcript_received", pii_transcript="I told my doctor")

    info_line, debug_line = json_lines(stream)
    assert "pii_transcript" not in info_line
    assert info_line["characters"] == 16  # non-personal fields are kept
    assert debug_line["pii_transcript"] == "I told my doctor"


def test_livekit_personal_fields_are_dropped_above_debug() -> None:
    stream = io.StringIO()
    configure_logging(render_json=True, stream=stream)

    get_logger("companion.test").info("stt_final", **{"lk.pii.user_transcript": "private words"})

    assert "private words" not in stream.getvalue()


def test_level_filters_lower_severity_lines() -> None:
    stream = io.StringIO()
    configure_logging(level="WARNING", render_json=True, stream=stream)
    logger = get_logger("companion.test")

    logger.info("ignored")
    logger.warning("kept")

    assert [line["event"] for line in json_lines(stream)] == ["kept"]


def test_exceptions_are_included_as_text_in_json() -> None:
    stream = io.StringIO()
    configure_logging(render_json=True, stream=stream)

    try:
        raise TimeoutError("groq did not answer")
    except TimeoutError:
        get_logger("companion.test").exception("safety_check_failed")

    (line,) = json_lines(stream)
    assert "TimeoutError: groq did not answer" in line["exception"]


def test_console_format_is_human_readable_not_json() -> None:
    stream = io.StringIO()
    configure_logging(render_json=False, stream=stream)
    bind_session_context(session_id="sess-1", presets={})

    get_logger("companion.test").info("worker_started")

    output = stream.getvalue()
    assert "worker_started" in output
    assert "session_id=sess-1" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)
    # Writing to a buffer, not a terminal, so no colour escape codes.
    assert "\x1b[" not in output
