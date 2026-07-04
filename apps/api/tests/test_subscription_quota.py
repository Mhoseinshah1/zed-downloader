"""Access control + quota accounting (app.services.subscription_service).

Covers: free-tier limit, in-flight (queued/processing) rows counting against
the free tier / subscriptions / group daily quota, subscription download_limit
enforcement, and consume_download debiting exactly the recorded entitlement.
"""
import datetime as dt

from app.database import utcnow
from app.models import DownloadRequest, Group, Plan, Setting, Subscription, User
from app.services import subscription_service as ss
from app.services.subscription_service import (
    VIA_FREE,
    VIA_GROUP_QUOTA,
    VIA_USER_SUB,
    check_access,
    consume_download,
)


# --- factories -------------------------------------------------------------

async def _user(session, telegram_id=1001, blocked=False):
    u = User(telegram_id=telegram_id, is_blocked=blocked)
    session.add(u)
    await session.flush()
    return u


async def _group(session, chat_id=-500, daily_limit=None, downloads_today=0, enabled=True):
    g = Group(
        telegram_chat_id=chat_id,
        is_enabled=enabled,
        daily_limit=daily_limit,
        downloads_today=downloads_today,
        quota_date=utcnow().date(),
    )
    session.add(g)
    await session.flush()
    return g


async def _plan(session, *, download_limit=0, scope="user", name="Test Plan"):
    p = Plan(
        name=name,
        price=1000,
        currency="IRT",
        duration_days=30,
        download_limit=download_limit,
        scope=scope,
        is_active=True,
    )
    session.add(p)
    await session.flush()
    return p


async def _subscription(session, plan, *, user_id=None, group_id=None, downloads_used=0):
    now = utcnow()
    sub = Subscription(
        user_id=user_id,
        group_id=group_id,
        plan_id=plan.id,
        starts_at=now - dt.timedelta(days=1),
        expires_at=now + dt.timedelta(days=30),
        downloads_used=downloads_used,
        is_active=True,
    )
    session.add(sub)
    await session.flush()
    return sub


async def _request(session, *, user_id=None, group_id=None, status="queued",
                   consumed_from=None, subscription_id=None):
    req = DownloadRequest(
        user_id=user_id,
        group_id=group_id,
        url="https://example.com/x",
        url_hash="hash",
        status=status,
        consumed_from=consumed_from,
        subscription_id=subscription_id,
        created_at=utcnow(),
    )
    session.add(req)
    await session.flush()
    return req


async def _set_free_limit(session, value):
    session.add(Setting(key="free_downloads_per_day", value=str(value)))
    await session.flush()


# --- free tier -------------------------------------------------------------

async def test_free_tier_allows_until_limit(session):
    await _set_free_limit(session, 2)
    await _plan(session)  # so plans list is populated on denial
    user = await _user(session)

    v = await check_access(session, user)
    assert v.allowed is True
    assert v.reason == "ok"
    assert v.granted_via == VIA_FREE
    assert v.remaining == 2


async def test_free_tier_in_flight_reduces_remaining(session):
    await _set_free_limit(session, 3)
    user = await _user(session)
    # One queued + one processing free-tier request already in flight today.
    await _request(session, user_id=user.id, status="queued", consumed_from=VIA_FREE)
    await _request(session, user_id=user.id, status="processing", consumed_from=VIA_FREE)

    v = await check_access(session, user)
    assert v.allowed is True
    assert v.remaining == 1  # 3 - 2 in-flight


async def test_free_tier_denied_at_limit(session):
    await _set_free_limit(session, 2)
    await _plan(session)
    user = await _user(session)
    await _request(session, user_id=user.id, status="completed", consumed_from=VIA_FREE)
    await _request(session, user_id=user.id, status="queued", consumed_from=VIA_FREE)

    v = await check_access(session, user)
    assert v.allowed is False
    assert v.reason == "need_subscription"
    assert len(v.plans) >= 1


async def test_free_tier_ignores_rows_tagged_to_other_entitlements(session):
    # A row admitted via a subscription must NOT eat the personal free tier.
    await _set_free_limit(session, 2)
    user = await _user(session)
    plan = await _plan(session, download_limit=10)
    sub = await _subscription(session, plan, user_id=user.id)
    await _request(session, user_id=user.id, status="completed",
                   consumed_from=VIA_USER_SUB, subscription_id=sub.id)

    used = await ss._free_tier_used_today(session, user.id)
    assert used == 0


# --- subscription limit ----------------------------------------------------

async def test_subscription_unlimited_plan_allows(session):
    user = await _user(session)
    plan = await _plan(session, download_limit=0)  # 0 == unlimited
    await _subscription(session, plan, user_id=user.id)

    v = await check_access(session, user)
    assert v.allowed is True
    assert v.granted_via == VIA_USER_SUB
    assert v.remaining is None  # unlimited


async def test_subscription_remaining_counts_in_flight(session):
    user = await _user(session)
    plan = await _plan(session, download_limit=5)
    sub = await _subscription(session, plan, user_id=user.id, downloads_used=0)
    # Two in-flight requests attributed to the subscription.
    await _request(session, user_id=user.id, status="queued",
                   consumed_from=VIA_USER_SUB, subscription_id=sub.id)
    await _request(session, user_id=user.id, status="processing",
                   consumed_from=VIA_USER_SUB, subscription_id=sub.id)

    v = await check_access(session, user)
    assert v.allowed is True
    assert v.subscription is not None
    assert v.remaining == 3  # 5 - 0 used - 2 in-flight


async def test_subscription_denied_when_in_flight_exhausts_limit(session):
    user = await _user(session)
    plan = await _plan(session, download_limit=3)
    sub = await _subscription(session, plan, user_id=user.id, downloads_used=1)
    # downloads_used(1) + in-flight(2) == limit(3) -> nothing remaining.
    await _request(session, user_id=user.id, status="queued",
                   consumed_from=VIA_USER_SUB, subscription_id=sub.id)
    await _request(session, user_id=user.id, status="processing",
                   consumed_from=VIA_USER_SUB, subscription_id=sub.id)

    v = await check_access(session, user)
    assert v.allowed is False
    assert v.reason == "limit_reached"


# --- group daily quota -----------------------------------------------------

async def test_group_daily_quota_counts_in_flight(session):
    user = await _user(session)
    group = await _group(session, daily_limit=3, downloads_today=0)
    await _request(session, user_id=user.id, group_id=group.id, status="queued",
                   consumed_from=VIA_GROUP_QUOTA)

    v = await check_access(session, user, group)
    assert v.allowed is True
    assert v.granted_via == VIA_GROUP_QUOTA
    assert v.remaining == 2  # 3 - 0 today - 1 in-flight


async def test_group_daily_quota_denied_when_in_flight_exhausts(session):
    user = await _user(session)
    group = await _group(session, daily_limit=2, downloads_today=0)
    await _request(session, user_id=user.id, group_id=group.id, status="queued",
                   consumed_from=VIA_GROUP_QUOTA)
    await _request(session, user_id=user.id, group_id=group.id, status="processing",
                   consumed_from=VIA_GROUP_QUOTA)

    v = await check_access(session, user, group)
    assert v.allowed is False
    assert v.reason == "limit_reached"


async def test_group_subscription_in_flight_reduces_remaining(session):
    user = await _user(session)
    group = await _group(session, daily_limit=None)
    plan = await _plan(session, download_limit=4, scope="group", name="Group Plan")
    sub = await _subscription(session, plan, group_id=group.id, downloads_used=1)
    await _request(session, user_id=user.id, group_id=group.id, status="queued",
                   consumed_from=ss.VIA_GROUP_SUB, subscription_id=sub.id)

    v = await check_access(session, user, group)
    assert v.allowed is True
    assert v.granted_via == ss.VIA_GROUP_SUB
    assert v.remaining == 2  # 4 - 1 used - 1 in-flight


async def test_blocked_user_denied(session):
    user = await _user(session, blocked=True)
    v = await check_access(session, user)
    assert v.allowed is False
    assert v.reason == "blocked"


# --- consume_download debiting --------------------------------------------

async def test_consume_debits_user_subscription(session):
    user = await _user(session)
    plan = await _plan(session, download_limit=10)
    sub = await _subscription(session, plan, user_id=user.id, downloads_used=0)
    req = await _request(session, user_id=user.id, status="processing",
                         consumed_from=VIA_USER_SUB, subscription_id=sub.id)

    await consume_download(session, req)

    assert sub.downloads_used == 1
    assert user.total_downloads == 1


async def test_consume_free_does_not_debit_subscription(session):
    # A request tagged consumed_from="free" must not touch any subscription,
    # even when the user has an active one.
    user = await _user(session)
    plan = await _plan(session, download_limit=10)
    sub = await _subscription(session, plan, user_id=user.id, downloads_used=0)
    req = await _request(session, user_id=user.id, status="processing",
                         consumed_from=VIA_FREE, subscription_id=None)

    await consume_download(session, req)

    assert sub.downloads_used == 0  # untouched
    assert user.total_downloads == 1  # personal counter still moves


async def test_consume_debits_group_quota(session):
    group = await _group(session, daily_limit=5, downloads_today=0)
    req = await _request(session, group_id=group.id, status="processing",
                         consumed_from=VIA_GROUP_QUOTA)

    await consume_download(session, req)

    assert group.downloads_today == 1
    assert group.total_downloads == 1
