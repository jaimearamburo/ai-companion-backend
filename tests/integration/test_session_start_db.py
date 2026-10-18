"""Call-start checks against the real schema: role lookup, bot limit, versions."""

import json
from uuid import UUID, uuid4

import pytest
from psycopg import AsyncConnection
from psycopg.rows import TupleRow

from companion.contracts import DispatchMetadata
from companion.dispatch import SessionRejectedError, prepare_session

pytestmark = pytest.mark.db

PRESETS = {
    "stt": "deepgram_nova3_au",
    "tts": "fish_s21_hosted",
    "llm": "bedrock_gptoss120b_syd",
    "safety": "groq_safeguard20b",
    "turn_detector": "livekit_v1_mini",
    "speculative_trigger": "auto",
}


async def add_user(db: AsyncConnection[TupleRow], role: str) -> UUID:
    cursor = await db.execute(
        "INSERT INTO public.users (email, role) VALUES (%s, %s) RETURNING id",
        (f"{uuid4().hex}@example.com", role),
    )
    row = await cursor.fetchone()
    assert row is not None
    return UUID(str(row[0]))


async def add_bot(
    db: AsyncConnection[TupleRow],
    *,
    versions: int = 1,
    active: bool = True,
    tools: tuple[str, ...] = (),
) -> UUID:
    slug = f"bot-{uuid4().hex[:8]}"
    cursor = await db.execute(
        "INSERT INTO public.bots (slug, display_name, is_active) VALUES (%s, %s, %s) RETURNING id",
        (slug, slug.title(), active),
    )
    row = await cursor.fetchone()
    assert row is not None
    bot_id = UUID(str(row[0]))
    for version in range(1, versions + 1):
        await db.execute(
            "INSERT INTO public.bot_versions"
            " (bot_id, version, persona_prompt, voices, allowed_tools)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                bot_id,
                version,
                f"Persona v{version}.",
                json.dumps({"fish_s21_hosted": "v"}),
                list(tools),
            ),
        )
    return bot_id


def metadata(user_id: UUID, bots: list[UUID]) -> DispatchMetadata:
    payload = {
        "user_id": str(user_id),
        "region": "au",
        "bots": [str(bot) for bot in bots],
        "memory_deletion_enabled": False,
        "presets": PRESETS,
    }
    return DispatchMetadata.model_validate_json(json.dumps(payload))


async def test_loads_the_latest_version_of_each_bot_in_order(db: AsyncConnection[TupleRow]) -> None:
    user = await add_user(db, "user")
    first, second = await add_bot(db, versions=3), await add_bot(db)
    session = await prepare_session(db, metadata(user, [second, first]))
    assert session.role == "user"
    assert [bot.id for bot in session.bots] == [second, first]
    assert session.bots[1].version == 3
    assert session.bots[1].persona_prompt == "Persona v3."


async def test_regular_user_with_three_bots_is_rejected(db: AsyncConnection[TupleRow]) -> None:
    user = await add_user(db, "user")
    bots = [await add_bot(db) for _ in range(3)]
    with pytest.raises(SessionRejectedError) as caught:
        await prepare_session(db, metadata(user, bots))
    assert caught.value.reason == "too_many_bots"


async def test_admin_may_use_any_number_of_bots(db: AsyncConnection[TupleRow]) -> None:
    admin = await add_user(db, "admin")
    bots = [await add_bot(db) for _ in range(4)]
    session = await prepare_session(db, metadata(admin, bots))
    assert len(session.bots) == 4


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("unknown_user", "unknown_user"),
        ("unknown_bot", "unknown_bot"),
        ("no_version", "unknown_bot"),
        ("retired", "inactive_bot"),
        ("bad_tool", "invalid_bot"),
    ],
)
async def test_rejections(db: AsyncConnection[TupleRow], setup: str, reason: str) -> None:
    user = uuid4() if setup == "unknown_user" else await add_user(db, "user")
    match setup:
        case "unknown_bot":
            bot = uuid4()
        case "no_version":
            bot = await add_bot(db, versions=0)
        case "retired":
            bot = await add_bot(db, active=False)
        case "bad_tool":
            bot = await add_bot(db, tools=("delete_user",))
        case _:
            bot = await add_bot(db)
    with pytest.raises(SessionRejectedError) as caught:
        await prepare_session(db, metadata(user, [bot]))
    assert caught.value.reason == reason
