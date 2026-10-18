"""Checks run when a call starts, before the agent joins the room."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from psycopg import AsyncConnection
from psycopg.rows import TupleRow

from companion.bots import InvalidBotError, UnknownBotError, load_current_bots
from companion.contracts import BotDefinition, DispatchMetadata, UserRole
from companion.observability import get_logger

REGULAR_USER_BOT_LIMIT = 2
QUERY_TIMEOUT_S = 2.0

type RejectReason = Literal[
    "unknown_user", "too_many_bots", "unknown_bot", "inactive_bot", "invalid_bot"
]

logger = get_logger(__name__)


class SessionRejectedError(Exception):
    """The call must not start; `reason` is a stable code for logs and the frontend."""

    def __init__(self, reason: RejectReason, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason: RejectReason = reason


@dataclass(frozen=True, slots=True)
class SessionStart:
    """Everything validated at call start that the rest of the call relies on."""

    metadata: DispatchMetadata
    role: UserRole
    bots: tuple[BotDefinition, ...]


def check_bot_limit(role: UserRole, bot_count: int) -> None:
    """Regular users may have at most two bots in a call; admins have no limit."""
    if role == "user" and bot_count > REGULAR_USER_BOT_LIMIT:
        raise SessionRejectedError(
            "too_many_bots",
            f"regular users may have at most {REGULAR_USER_BOT_LIMIT} bots, got {bot_count}",
        )


async def load_user_role(conn: AsyncConnection[TupleRow], metadata: DispatchMetadata) -> UserRole:
    async with asyncio.timeout(QUERY_TIMEOUT_S), conn.cursor() as cursor:
        await cursor.execute(
            "SELECT role::text FROM public.users WHERE id = %s", (metadata.user_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        raise SessionRejectedError(
            "unknown_user", "the user in the dispatch metadata doesn't exist"
        )
    role = row[0]
    if role not in ("admin", "user"):
        raise SessionRejectedError("unknown_user", "the user has an unrecognised role")
    return "admin" if role == "admin" else "user"


async def prepare_session(
    conn: AsyncConnection[TupleRow], metadata: DispatchMetadata
) -> SessionStart:
    """Validate a new call against the database, or raise SessionRejectedError."""
    try:
        role = await load_user_role(conn, metadata)
        check_bot_limit(role, len(metadata.bots))
        try:
            bots = await load_current_bots(conn, metadata.bots)
        except UnknownBotError as error:
            raise SessionRejectedError("unknown_bot", str(error)) from error
        except InvalidBotError as error:
            raise SessionRejectedError("invalid_bot", str(error)) from error
        inactive = [bot.slug for bot in bots if not bot.is_active]
        if inactive:
            raise SessionRejectedError("inactive_bot", f"retired bot(s): {', '.join(inactive)}")
    except SessionRejectedError as rejection:
        logger.warning("session_rejected", reason=rejection.reason, detail=str(rejection))
        raise
    return SessionStart(metadata=metadata, role=role, bots=bots)
