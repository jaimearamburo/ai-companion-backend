"""Structured logging with call context attached automatically.

Two kinds of code log in this worker: ours, through structlog, and third-party
libraries such as LiveKit, through Python's standard ``logging`` module. Both
are routed through the same pipeline of "processors" (small functions that each
add to or edit a log entry) and the same renderer, so every line has one format.

Call context — session id, turn id, active provider presets — is stored in
``contextvars``: per-task variables that asyncio copies into every task a call
starts. Once bound at the start of a call, it appears on every log line that
call produces, without being passed around by hand.

Privacy rule: fields whose names start with ``pii_`` (personally identifiable
information, e.g. ``pii_transcript``) are stripped from every line above DEBUG
level. DEBUG itself is refused in production by the config module, so what
users say can reach local debug output but never production logs.
"""

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, TextIO

import structlog

# Prefixes marking fields that may hold personal information. "lk.pii." is the
# prefix LiveKit Agents uses for the same purpose (e.g. "lk.pii.user_transcript").
PII_PREFIXES = ("pii_", "lk.pii.")

# structlog's type for one log entry: a mutable dict of field name -> value.
# Values are genuinely arbitrary here (anything a caller chooses to log).
type EventDict = MutableMapping[str, Any]


def drop_pii_above_debug(_logger: object, method_name: str, event_dict: EventDict) -> EventDict:
    """Processor: remove personal-information fields unless this is a debug line.

    structlog calls every processor with (logger, level name, event dict) and
    passes the returned dict on to the next processor.
    """
    if method_name != "debug":
        for key in [k for k in event_dict if k.startswith(PII_PREFIXES)]:
            del event_dict[key]
    return event_dict


def configure_logging(
    *, level: str = "INFO", render_json: bool = False, stream: TextIO | None = None
) -> None:
    """Set up logging for the whole process. Call once, at startup.

    Args:
        level: Minimum level written ("DEBUG", "INFO", "WARNING", "ERROR").
        render_json: One JSON object per line (deployed) instead of readable
            coloured console lines (local development).
        stream: Where lines are written; defaults to standard error. Tests pass
            an in-memory stream to inspect the output.
    """
    # Processors shared by our logs and third-party logs, applied in order.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,  # add the bound call context
        structlog.stdlib.add_logger_name,  # which module logged it
        structlog.stdlib.add_log_level,  # "info", "error", ...
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        drop_pii_above_debug,
    ]

    renderer: structlog.types.Processor
    if render_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=_supports_colour(stream))

    # Our own loggers: run the shared processors, then hand the entry to the
    # standard logging machinery (wrap_for_formatter) so the single handler
    # below renders ours and third-party lines identically.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # The formatter that actually renders every line. foreign_pre_chain runs the
    # shared processors on third-party (standard logging) entries, which never
    # went through structlog.configure above.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # JSON needs exceptions as text; the console renderer prints them itself.
            *([structlog.processors.format_exc_info] if render_json else []),
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(formatter)

    # Replace any existing handlers on the root logger (the parent of every
    # standard logger), so each line is written exactly once, in our format.
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a logger for a module. Convention: ``get_logger(__name__)``."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger


def bind_session_context(*, session_id: str, presets: Mapping[str, str]) -> None:
    """Attach call-level context to every log line from here on in this call."""
    structlog.contextvars.bind_contextvars(session_id=session_id, presets=dict(presets))


def bind_turn_context(*, turn_id: str) -> None:
    """Attach (or replace) the current turn id on every log line."""
    structlog.contextvars.bind_contextvars(turn_id=turn_id)


def clear_call_context() -> None:
    """Remove all call context, e.g. when a call ends."""
    structlog.contextvars.clear_contextvars()


def _supports_colour(stream: TextIO | None) -> bool:
    """Colour only when writing to a real terminal (not a file or a test buffer)."""
    target = stream or sys.stderr
    return hasattr(target, "isatty") and target.isatty()
