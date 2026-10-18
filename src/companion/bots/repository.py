"""Loads bot definitions from the database and validates every row."""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import TupleRow, dict_row
from pydantic import ValidationError

from companion.contracts import BotDefinition

QUERY_TIMEOUT_S = 2.0

# Each requested bot with its latest version. Columns are aliased to the field
# names of BotDefinition so a row validates directly.
_CURRENT_VERSIONS = """
SELECT DISTINCT ON (b.id)
       b.id, v.id AS version_id, v.version, b.slug, b.display_name, b.ui_description,
       b.avatar_url, b.is_active, v.persona_prompt, v.voices, v.allowed_tools,
       v.memory_policy AS memory, v.safety_rules AS safety
FROM public.bots AS b
JOIN public.bot_versions AS v ON v.bot_id = b.id
WHERE b.id = ANY(%(ids)s)
ORDER BY b.id, v.version DESC
"""


class UnknownBotError(Exception):
    """A requested bot doesn't exist or has no version yet."""


class InvalidBotError(Exception):
    """A bot's stored definition doesn't match the bot model."""


def bot_from_row(row: Mapping[str, Any]) -> BotDefinition:
    """Validate one database row, naming the bot and every problem if it's invalid."""
    try:
        return BotDefinition.model_validate(dict(row))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in item['loc']) or 'row'}: {item['msg']}"
            for item in error.errors(include_url=False)
        )
        bot = f"{row.get('slug', '?')} version {row.get('version', '?')}"
        raise InvalidBotError(f"bot {bot} is invalid: {problems}") from None


async def load_current_bots(
    conn: AsyncConnection[TupleRow], bot_ids: Sequence[UUID]
) -> tuple[BotDefinition, ...]:
    """Load the latest version of each bot, in the order requested.

    Raises UnknownBotError if any bot is missing and InvalidBotError if any stored
    definition is invalid. The query is cancelled after QUERY_TIMEOUT_S.
    """
    async with asyncio.timeout(QUERY_TIMEOUT_S), conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(_CURRENT_VERSIONS, {"ids": list(bot_ids)})
        rows = {row["id"]: row for row in await cursor.fetchall()}
    missing = [str(bot_id) for bot_id in bot_ids if bot_id not in rows]
    if missing:
        raise UnknownBotError(f"no bot with a version for id(s): {', '.join(missing)}")
    return tuple(bot_from_row(rows[bot_id]) for bot_id in bot_ids)
