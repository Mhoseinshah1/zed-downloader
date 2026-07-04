"""Phase 2 backend tests: user upsert/persistence, account summary, and the
placeholder download-request intake."""
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import DownloadRequest, User
from app.routes.internal import (
    create_download_request,
    get_user_account,
    set_language,
    users_upsert,
)
from app.schemas.internal import (
    DownloadRequestPlaceholderIn,
    LanguageIn,
    UserUpsertIn,
)
from app.seed import seed


async def test_upsert_does_not_duplicate_and_sets_last_seen(session):
    body = UserUpsertIn(telegram_id=111, username="ali", first_name="Ali")
    u1 = await users_upsert(body, session)
    assert u1.last_seen_at is not None
    first_seen = u1.last_seen_at

    # Second upsert of the same telegram_id must update, not insert.
    await users_upsert(UserUpsertIn(telegram_id=111, username="ali2"), session)
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    assert count == 1

    refreshed = (await session.execute(select(User).where(User.telegram_id == 111))).scalar_one()
    assert refreshed.username == "ali2"
    assert refreshed.last_seen_at >= first_seen


async def test_language_update_keeps_single_row(session):
    await seed()  # languages must be active for set_language to accept them
    await users_upsert(UserUpsertIn(telegram_id=222, language="fa"), session)
    await set_language(222, LanguageIn(language="en"), session)

    user = (await session.execute(select(User).where(User.telegram_id == 222))).scalar_one()
    assert user.language == "en"
    assert user.last_seen_at is not None
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    assert count == 1


async def test_get_account_free_user(session):
    await users_upsert(UserUpsertIn(telegram_id=333, username="sara"), session)
    account = await get_user_account(333, session)
    assert account["telegram_id"] == 333
    assert account["username"] == "sara"
    assert account["account_type"] == "free"
    assert account["subscription"] is None
    assert account["total_downloads"] == 0
    assert account["last_seen_at"] is not None
    assert account["free_daily_quota"] >= 0


async def test_get_account_unknown_is_404(session):
    with pytest.raises(HTTPException) as exc:
        await get_user_account(999999, session)
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://youtu.be/abc", "youtube"),
        ("https://www.instagram.com/p/x/", "instagram"),
        ("https://www.tiktok.com/@a/video/1", "tiktok"),
        ("https://x.com/a/status/1", "twitter"),
        ("https://example.com/page", "generic"),
    ],
)
async def test_placeholder_request_detects_platform(session, url, expected):
    await seed()  # platforms must exist for resolution
    result = await create_download_request(
        DownloadRequestPlaceholderIn(telegram_id=444, url=url), session
    )
    assert result["status"] == "received"
    assert result["detected_platform"] == expected

    row = (
        await session.execute(select(DownloadRequest).where(DownloadRequest.id == result["request_id"]))
    ).scalar_one()
    assert row.status == "received"
    # 'received' is not a quota-counted status, so the placeholder consumes nothing.
    assert row.consumed_from is None


async def test_placeholder_request_upserts_user_once(session):
    await seed()
    await create_download_request(
        DownloadRequestPlaceholderIn(telegram_id=555, url="https://youtu.be/a"), session
    )
    await create_download_request(
        DownloadRequestPlaceholderIn(telegram_id=555, url="https://youtu.be/b"), session
    )
    users = (await session.execute(select(func.count(User.id)))).scalar_one()
    reqs = (await session.execute(select(func.count(DownloadRequest.id)))).scalar_one()
    assert users == 1  # no duplicate user
    assert reqs == 2   # both links recorded
