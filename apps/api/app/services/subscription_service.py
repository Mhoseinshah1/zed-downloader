"""Access control + quota accounting.

INVARIANTS:
- Quota is decremented ONLY by consume_download(), which the worker calls
  strictly AFTER a successful upload to the user. Nothing else in the
  codebase may mutate downloads_used / total_downloads / downloads_today.
- Every admitted request is tagged (consumed_from + subscription_id) with
  the entitlement that granted it. Capacity checks count in-flight
  (queued/processing) rows against that same entitlement, so a user cannot
  overrun a limit by queueing many downloads before the first completes,
  and completions are debited against exactly the entitlement that admitted
  them — even if a different one became active meanwhile.
"""
import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import utcnow
from app.models import DownloadRequest, Group, Plan, Setting, Subscription, User

# Rows that occupy quota: in-flight or delivered. Failures/denials never count.
_COUNTED_STATUSES = ("queued", "processing", "completed")
# Rows admitted but not yet debited (downloads_used counts only completions).
_IN_FLIGHT_STATUSES = ("queued", "processing")

# consumed_from tags
VIA_FREE = "free"
VIA_USER_SUB = "user_sub"
VIA_GROUP_SUB = "group_sub"
VIA_GROUP_QUOTA = "group_quota"


@dataclass
class AccessVerdict:
    allowed: bool
    # ok | blocked | maintenance | limit_reached | need_subscription | group_disabled
    reason: str
    subscription: Subscription | None = None
    plans: list[Plan] = field(default_factory=list)
    remaining: int | None = None
    # Entitlement that granted access (VIA_* above); None when denied.
    granted_via: str | None = None


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


def _day_start() -> dt.datetime:
    return utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


async def _in_flight_for_subscription(session: AsyncSession, subscription_id: int) -> int:
    """Admitted-but-not-yet-debited requests attributed to a subscription."""
    result = await session.execute(
        select(func.count(DownloadRequest.id)).where(
            DownloadRequest.subscription_id == subscription_id,
            DownloadRequest.status.in_(_IN_FLIGHT_STATUSES),
        )
    )
    return int(result.scalar_one() or 0)


async def _subscription_remaining(session: AsyncSession, sub: Subscription) -> int | None:
    """Remaining capacity incl. in-flight requests. None = unlimited plan."""
    limit = sub.plan.download_limit
    if limit == 0:
        return None
    in_flight = await _in_flight_for_subscription(session, sub.id)
    return limit - sub.downloads_used - in_flight


async def _free_tier_used_today(session: AsyncSession, user_id: int) -> int:
    """Free-tier usage = today's in-flight or completed rows the free tier
    admitted (rows admitted by subscriptions/group quota are tagged and
    therefore excluded — they must not eat the personal free tier)."""
    result = await session.execute(
        select(func.count(DownloadRequest.id)).where(
            DownloadRequest.user_id == user_id,
            DownloadRequest.created_at >= _day_start(),
            DownloadRequest.status.in_(_COUNTED_STATUSES),
            DownloadRequest.consumed_from == VIA_FREE,
        )
    )
    return int(result.scalar_one() or 0)


async def _group_quota_in_flight_today(session: AsyncSession, group_id: int) -> int:
    result = await session.execute(
        select(func.count(DownloadRequest.id)).where(
            DownloadRequest.group_id == group_id,
            DownloadRequest.created_at >= _day_start(),
            DownloadRequest.status.in_(_IN_FLIGHT_STATUSES),
            DownloadRequest.consumed_from == VIA_GROUP_QUOTA,
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

    NOTE: two truly concurrent admission requests can both pass the same
    capacity check (bounded overrun of at most the API concurrency); a v2
    hardening item is an atomic reservation.
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
            remaining = await _subscription_remaining(session, group_sub)
            if remaining is None or remaining > 0:
                return AccessVerdict(
                    True, "ok", subscription=group_sub, remaining=remaining, granted_via=VIA_GROUP_SUB
                )
            return AccessVerdict(False, "limit_reached", plans=await plans_for_user(session))

        if group.daily_limit is not None:
            _reset_group_day_if_needed(group)
            in_flight = await _group_quota_in_flight_today(session, group.id)
            remaining = group.daily_limit - group.downloads_today - in_flight
            if remaining <= 0:
                return AccessVerdict(False, "limit_reached")
            return AccessVerdict(True, "ok", remaining=remaining, granted_via=VIA_GROUP_QUOTA)
        # Group without subscription or own quota: fall through to the
        # requesting user's entitlements.

    # 4. Personal subscription.
    user_sub = await active_subscription(session, user_id=user.id)
    if user_sub is not None:
        remaining = await _subscription_remaining(session, user_sub)
        if remaining is None or remaining > 0:
            return AccessVerdict(
                True, "ok", subscription=user_sub, remaining=remaining, granted_via=VIA_USER_SUB
            )
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
    return AccessVerdict(True, "ok", remaining=free_limit - used, granted_via=VIA_FREE)


async def consume_download(session: AsyncSession, request: DownloadRequest) -> None:
    """Book one successful download. Worker-only, called strictly AFTER the
    file has been uploaded to the user (money-safety invariant #4).

    Debits exactly the entitlement recorded on the request at admission
    time (consumed_from / subscription_id) — never re-resolved, so an
    entitlement that changed mid-download is neither double-debited nor
    skipped. Flushes but does not commit — the caller owns the transaction.
    """
    user = await session.get(User, request.user_id) if request.user_id else None
    if user is not None:
        user.total_downloads += 1

    group = await session.get(Group, request.group_id) if request.group_id else None
    if group is not None:
        group.total_downloads += 1

    if request.consumed_from in (VIA_USER_SUB, VIA_GROUP_SUB) and request.subscription_id:
        subscription = await session.get(Subscription, request.subscription_id)
        # Debit even if the subscription has since expired or hit its limit —
        # the download was admitted against it. Missing row -> no-op.
        if subscription is not None:
            subscription.downloads_used += 1
    elif request.consumed_from == VIA_GROUP_QUOTA and group is not None:
        _reset_group_day_if_needed(group)
        group.downloads_today += 1
    # VIA_FREE consumes implicitly: it is counted from tagged
    # download_requests rows, so nothing to increment here.

    await session.flush()
