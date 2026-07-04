"""Internal endpoints consumed by the Telegram bot.

Every route here is guarded by the shared X-Internal-Secret header — these
are never exposed to end users directly (Caddy only proxies them inside the
compose network; the bot calls http://api:8000).
"""
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, utcnow
from app.models import DownloadRequest, ForcedJoinChannel, Group, Language, Plan, User
from app.payments.base import PaymentGatewayError
from app.providers.manager import manager
from app.routes.deps import require_internal_secret
from app.schemas.internal import (
    DownloadRequestIn,
    DownloadRequestPlaceholderIn,
    GroupInternalOut,
    GroupUpsertIn,
    LanguageIn,
    PaymentCreateIn,
    PlanPublicOut,
    UserInternalOut,
    UserUpsertIn,
)
from app.services.payment_service import GATEWAYS, create_payment_record
from app.services.ratelimit import is_rate_limited
from app.services.subscription_service import active_subscription, check_access, get_setting
from app.config import get_settings
from app.workers.queue import enqueue

log = logging.getLogger("zed.internal")

router = APIRouter(
    prefix="/api/internal", tags=["internal"], dependencies=[Depends(require_internal_secret)]
)


async def _upsert_user(db: AsyncSession, data: UserUpsertIn) -> User:
    """Create or update a user keyed on telegram_id (never duplicates).

    Profile fields and last_seen_at are refreshed on every call; language is
    NOT overwritten on update (the user sets it explicitly via /language) but
    seeds the row on first creation.
    """
    result = await db.execute(select(User).where(User.telegram_id == data.telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=data.telegram_id,
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            language=data.language or "fa",
            last_seen_at=utcnow(),
        )
        db.add(user)
        await db.flush()
    else:
        user.username = data.username
        user.first_name = data.first_name
        user.last_name = data.last_name
        user.last_seen_at = utcnow()
    return user


async def _upsert_group(db: AsyncSession, chat_id: int, title: str | None, username: str | None) -> Group:
    result = await db.execute(select(Group).where(Group.telegram_chat_id == chat_id))
    group = result.scalar_one_or_none()
    if group is None:
        group = Group(telegram_chat_id=chat_id, title=title, username=username)
        db.add(group)
        await db.flush()
    else:
        if title:
            group.title = title
        if username:
            group.username = username
    return group


@router.post("/users/upsert", response_model=UserInternalOut)
async def users_upsert(body: UserUpsertIn, db: AsyncSession = Depends(get_db)) -> User:
    user = await _upsert_user(db, body)
    await db.commit()
    return user


@router.post("/users/{telegram_id}/language")
async def set_language(telegram_id: int, body: LanguageIn, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(Language).where(Language.code == body.language, Language.is_active.is_(True))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown or inactive language")
    user_result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    user.language = body.language
    user.last_seen_at = utcnow()
    await db.commit()
    return {"ok": True}


@router.get("/users/{telegram_id}")
async def get_user_account(telegram_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Account summary for the bot's 'My Account' screen. 404 if unknown."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    sub = await active_subscription(db, user_id=user.id)
    subscription = None
    if sub is not None:
        limit = sub.plan.download_limit if sub.plan else 0
        subscription = {
            "plan_name": sub.plan.name if sub.plan else None,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "downloads_used": sub.downloads_used,
            "download_limit": limit,  # 0 = unlimited
        }

    # Free-tier daily quota (informational; real enforcement lives in the
    # download flow). Configurable via settings.free_downloads_per_day.
    free_limit_raw = await get_setting(db, "free_downloads_per_day")
    try:
        free_limit = int(free_limit_raw) if free_limit_raw is not None else get_settings().FREE_DOWNLOADS_PER_DAY
    except (TypeError, ValueError):
        free_limit = get_settings().FREE_DOWNLOADS_PER_DAY

    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language": user.language,
        "is_blocked": user.is_blocked,
        "account_type": "subscription" if subscription else "free",
        "total_downloads": user.total_downloads,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
        "free_daily_quota": free_limit,
        "subscription": subscription,
    }


@router.post("/groups/upsert", response_model=GroupInternalOut)
async def groups_upsert(body: GroupUpsertIn, db: AsyncSession = Depends(get_db)) -> Group:
    group = await _upsert_group(db, body.telegram_chat_id, body.title, body.username)
    await db.commit()
    return group


def _plan_payload(plans: list[Plan]) -> list[dict]:
    return [PlanPublicOut.model_validate(p).model_dump(mode="json") for p in plans]


@router.post("/download/request")
async def download_request(body: DownloadRequestIn, db: AsyncSession = Depends(get_db)) -> dict:
    user = await _upsert_user(
        db,
        UserUpsertIn(
            telegram_id=body.telegram_id,
            username=body.username,
            first_name=body.first_name,
            last_name=body.last_name,
            language=body.language,
        ),
    )
    group: Group | None = None
    if body.chat_id is not None and body.chat_id < 0:  # Telegram group ids are negative
        group = await _upsert_group(db, body.chat_id, None, None)

    # Throttle before doing any real work so spam can't flood the queue.
    if await is_rate_limited(telegram_id=body.telegram_id, chat_id=body.chat_id):
        await db.commit()  # keep the user/group upserts
        return {"status": "denied", "reason": "rate_limited"}

    platform = await manager.resolve_platform(db, body.url)
    if platform is None:
        await db.commit()  # keep the user/group upserts
        return {"status": "error", "reason": "unsupported_url"}

    verdict = await check_access(db, user, group)
    url_hash = hashlib.sha256(body.url.encode("utf-8")).hexdigest()

    if not verdict.allowed:
        # Record the denial for auditing; denied rows never count as quota.
        db.add(
            DownloadRequest(
                user_id=user.id,
                group_id=group.id if group else None,
                url=body.url,
                url_hash=url_hash,
                platform_id=platform.id,
                status="denied",
                error_code=verdict.reason,
            )
        )
        await db.commit()
        response: dict = {"status": "denied", "reason": verdict.reason}
        if verdict.reason in ("need_subscription", "limit_reached") and verdict.plans:
            response["plans"] = _plan_payload(verdict.plans)
        return response

    request = DownloadRequest(
        user_id=user.id,
        group_id=group.id if group else None,
        url=body.url,
        url_hash=url_hash,
        platform_id=platform.id,
        status="queued",
        # Tag the entitlement that admitted this request; quota accounting
        # counts in-flight rows and debits completions against exactly it.
        consumed_from=verdict.granted_via,
        subscription_id=verdict.subscription.id if verdict.subscription else None,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    try:
        await enqueue(
            {
                "request_id": request.id,
                "telegram_id": body.telegram_id,
                "chat_id": body.chat_id if body.chat_id is not None else body.telegram_id,
                "url": body.url,
                "language": user.language,
            }
        )
    except Exception as exc:
        log.error("enqueue failed for request %s: %s", request.id, exc)
        request.status = "failed"
        request.error_code = "unknown_error"
        await db.commit()
        return {"status": "error", "reason": "queue_unavailable"}

    return {"status": "queued", "request_id": request.id}


@router.post("/download-requests")
async def create_download_request(
    body: DownloadRequestPlaceholderIn, db: AsyncSession = Depends(get_db)
) -> dict:
    """Phase 2 placeholder intake: upsert the user, detect the platform, and
    RECORD the request (status='received') WITHOUT enqueuing a real download.

    Reuses the existing DownloadRequest model. 'received' rows are not swept by
    the worker and do not consume any quota, so this is a safe log-only path
    until the real queue is turned on in Phase 3.
    """
    user = await _upsert_user(
        db,
        UserUpsertIn(
            telegram_id=body.telegram_id,
            username=body.username,
            first_name=body.first_name,
            last_name=body.last_name,
            language=body.language,
        ),
    )
    group: Group | None = None
    if body.chat_id is not None and body.chat_id < 0:  # Telegram group ids are negative
        group = await _upsert_group(db, body.chat_id, None, None)

    platform = await manager.resolve_platform(db, body.url)
    url_hash = hashlib.sha256(body.url.encode("utf-8")).hexdigest()
    request = DownloadRequest(
        user_id=user.id,
        group_id=group.id if group else None,
        url=body.url,
        url_hash=url_hash,
        platform_id=platform.id if platform else None,
        status="received",
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    return {
        "status": "received",
        "request_id": request.id,
        "detected_platform": platform.slug if platform else "unknown",
    }


@router.get("/plans")
async def list_plans(scope: str = "user", db: AsyncSession = Depends(get_db)) -> dict:
    """Active plans for a scope ('user' by default, 'group' for group buys)."""
    if scope not in ("user", "group"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope must be 'user' or 'group'")
    result = await db.execute(
        select(Plan)
        .where(Plan.is_active.is_(True), Plan.scope == scope)
        .order_by(Plan.sort_order.asc(), Plan.price.asc())
    )
    return {"plans": _plan_payload(list(result.scalars()))}


@router.get("/texts")
async def list_texts(db: AsyncSession = Depends(get_db)) -> dict:
    """All panel-editable bot texts, for the bot to overlay on its bundled
    i18n. Shape: {lang: {key: value}}."""
    from app.models import BotText

    rows = (await db.execute(select(BotText))).scalars().all()
    texts: dict[str, dict[str, str]] = {}
    for row in rows:
        texts.setdefault(row.lang, {})[row.key] = row.value
    return {"texts": texts}


@router.get("/forced-join")
async def forced_join_channels(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(ForcedJoinChannel)
        .where(ForcedJoinChannel.is_active.is_(True))
        .order_by(ForcedJoinChannel.sort_order.asc(), ForcedJoinChannel.id.asc())
    )
    channels = [
        {"id": c.id, "channel_id": c.channel_id, "username": c.username, "title": c.title}
        for c in result.scalars()
    ]
    return {"channels": channels}


@router.post("/payments/create")
async def payments_create(body: PaymentCreateIn, db: AsyncSession = Depends(get_db)) -> dict:
    if body.gateway not in GATEWAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown gateway: {body.gateway}")
    user_result = await db.execute(select(User).where(User.telegram_id == body.telegram_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    plan = await db.get(Plan, body.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found or inactive")

    group: Group | None = None
    if plan.scope == "group":
        # A group-scope plan must be bought from within the target group so we
        # know which group the subscription activates for.
        if body.chat_id is None or body.chat_id >= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "group plans must be purchased from inside the group",
            )
        group = await _upsert_group(db, body.chat_id, None, None)
    elif plan.scope != "user":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"plan scope '{plan.scope}' is not purchasable")

    try:
        payment, payment_url = await create_payment_record(
            db, user=user, plan=plan, gateway_name=body.gateway, group=group
        )
    except PaymentGatewayError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"gateway error: {exc}")
    return {"payment_id": payment.id, "payment_url": payment_url, "authority": payment.authority}
