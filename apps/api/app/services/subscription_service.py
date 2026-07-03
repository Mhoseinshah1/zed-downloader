"""Access control + quota accounting.

INVARIANT: quota is decremented ONLY by consume_download(), which the worker
calls strictly AFTER a successful upload to the user. Nothing else in the
codebase may mutate downloads_used / total_downloads / downloads_today.
"""
import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import utcnow
from app.models import DownloadRequest, Group, Plan, Setting, Subscription, User

# Statuses that count against the free tier: everything in-flight or done.
# Failures and denials never consume quota.
_COUNTED_STATUSES = ("queued", "processing", "completed")


@dataclass
class AccessVerdict:
    allowed: bool
    # ok | blocked | maintenance | limit_reached | need_subscription | group_disabled
    reason: str
    subscription: Subscription | None = None
    plans: list[Plan] = field(default_factory=list)
    remaining: int | None = None


async def get_setting(session: AsyncSession, key: str, default: str | None = None) -> str | None:
    row = await session.execute(select(Setting.value).where(Setting.key == key))
    value = row.scalar_one_or_none()
    return value if value is not None else default


async def active_subscription(
    session: AsyncSession, *, user_id: int | None = None, group_id: int | None = None
) -> Subscription | None:
    """Newest-expiring active, unexpired subscription for a user OR a group."""
    query = select(Subscription).where(
        Subscription.is_active.is_(True), Subscription.expires_at > utcnow()
    )
    if user_id is not None:
        query = query.where(Subscription.user_id == user_id)
    if group_id is not None:
        query = query.where(Subscription.group_id == group_id)
    query = query.order_by(Subscription.expires_at.desc()).limit(1)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def plans_for_user(session: AsyncSession) -> list[Plan]:
    result = await session.execute(
        select(Plan)
        .where(Plan.is_active.is_(True), Plan.scope == "user")
        .order_by(Plan.sort_order.asc(), Plan.price.asc())
    )
    return list(result.scalars())


def _subscription_has_capacity(sub: Subscription) -> bool:
    limit = sub.plan.download_limit
    return limit == 0 or sub.downloads_used < limit


async def _free_tier_used_today(session: AsyncSession, user_id: int) -> int:
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.count(DownloadRequest.id)).where(
            DownloadRequest.user_id == user_id,
            DownloadRequest.created_at >= day_start,
            DownloadRequest.status.in_(_COUNTED_STATUSES),
        )
    )
    return int(result.scalar_one() or 0)


def _reset_group_day_if_needed(group: Group) -> None:
    today = utcnow().date()
    if group.quota_date != today:
        group.quota_date = today
        group.downloads_today = 0


async def check_access(session: AsyncSession, user: User, group: Group | None = None) -> AccessVerdict:
    """Decide whether this user (optionally inside a group) may download now.

    Check order (fixed): maintenance -> user blocked -> group enabled/quota ->
    group subscription -> user subscription -> free tier.
    """
    # 1. Global maintenance switch.
    maintenance = (await get_setting(session, "maintenance_mode", "false") or "").lower()
    if maintenance in ("true", "1", "on", "yes"):
        return AccessVerdict(False, "maintenance")

    # 2. Blocked user.
    if user.is_blocked:
        return AccessVerdict(False, "blocked")

    # 3. Group checks (only when the request comes from a group chat).
    if group is not None:
        if not group.is_enabled:
            return AccessVerdict(False, "group_disabled")

        group_sub = await active_subscription(session, group_id=group.id)
        if group_sub is not None:
            if _subscription_has_capacity(group_sub):
                return AccessVerdict(True, "ok", subscription=group_sub)
            return AccessVerdict(False, "limit_reached", plans=await plans_for_user(session))

        if group.daily_limit is not None:
            _reset_group_day_if_needed(group)
            if group.downloads_today >= group.daily_limit:
                return AccessVerdict(False, "limit_reached")
            return AccessVerdict(True, "ok", remaining=group.daily_limit - group.downloads_today)
        # Group without subscription or own quota: fall through to the
        # requesting user's entitlements.

    # 4. Personal subscription.
    user_sub = await active_subscription(session, user_id=user.id)
    if user_sub is not None:
        if _subscription_has_capacity(user_sub):
            limit = user_sub.plan.download_limit
            remaining = None if limit == 0 else limit - user_sub.downloads_used
            return AccessVerdict(True, "ok", subscription=user_sub, remaining=remaining)
        return AccessVerdict(False, "limit_reached", plans=await plans_for_user(session))

    # 5. Free tier.
    free_limit_raw = await get_setting(session, "free_downloads_per_day")
    try:
        free_limit = int(free_limit_raw) if free_limit_raw is not None else get_settings().FREE_DOWNLOADS_PER_DAY
    except ValueError:
        free_limit = get_settings().FREE_DOWNLOADS_PER_DAY
    used = await _free_tier_used_today(session, user.id)
    if used >= free_limit:
        return AccessVerdict(False, "need_subscription", plans=await plans_for_user(session))
    return AccessVerdict(True, "ok", remaining=free_limit - used)


async def consume_download(session: AsyncSession, request: DownloadRequest) -> None:
    """Book one successful download. Worker-only, called strictly AFTER the
    file has been uploaded to the user (money-safety invariant #4).

    Flushes but does not commit — the caller owns the transaction.
    """
    user = await session.get(User, request.user_id) if request.user_id else None
    if user is not None:
        user.total_downloads += 1

    if request.group_id:
        group = await session.get(Group, request.group_id)
        if group is not None:
            group.total_downloads += 1
            group_sub = await active_subscription(session, group_id=group.id)
            if group_sub is not None:
                group_sub.downloads_used += 1
            elif group.daily_limit is not None:
                _reset_group_day_if_needed(group)
                group.downloads_today += 1
            elif user is not None:
                await _consume_user_entitlement(session, user)
    elif user is not None:
        await _consume_user_entitlement(session, user)

    await session.flush()


async def _consume_user_entitlement(session: AsyncSession, user: User) -> None:
    user_sub = await active_subscription(session, user_id=user.id)
    if user_sub is not None:
        user_sub.downloads_used += 1
    # Free tier consumes implicitly: it is counted from completed/in-flight
    # download_requests rows, so nothing to increment here.
