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

from app.database import get_db
from app.models import DownloadRequest, ForcedJoinChannel, Group, Language, Plan, User
from app.payments.base import PaymentGatewayError
from app.providers.manager import manager
from app.routes.deps import require_internal_secret
from app.schemas.internal import (
    DownloadRequestIn,
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
from app.services.subscription_service import check_access
from app.workers.queue import enqueue

log = logging.getLogger("zed.internal")

router = APIRouter(
    prefix="/api/internal", tags=["internal"], dependencies=[Depends(require_internal_secret)]
)


async def _upsert_user(db: AsyncSession, data: UserUpsertIn) -> User:
    result = await db.execute(select(User).where(User.telegram_id == data.telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=data.telegram_id,
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            language=data.language or "fa",
        )
        db.add(user)
        await db.flush()
    else:
        # Refresh profile fields; language is NOT overwritten here — the user
        # picks it explicitly via the /language endpoint.
        user.username = data.username
        user.first_name = data.first_name
        user.last_name = data.last_name
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
    await db.commit()
    return {"ok": True}


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
