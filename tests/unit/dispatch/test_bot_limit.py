"""Regular users may have at most two bots in a call; admins have no limit."""

import pytest

from companion.contracts import UserRole
from companion.dispatch import REGULAR_USER_BOT_LIMIT, SessionRejectedError, check_bot_limit


@pytest.mark.parametrize(("role", "count"), [("user", 1), ("user", 2), ("admin", 2), ("admin", 12)])
def test_allowed_bot_counts(role: UserRole, count: int) -> None:
    check_bot_limit(role, count)


def test_regular_user_over_the_limit_is_rejected() -> None:
    with pytest.raises(SessionRejectedError) as caught:
        check_bot_limit("user", REGULAR_USER_BOT_LIMIT + 1)
    assert caught.value.reason == "too_many_bots"
