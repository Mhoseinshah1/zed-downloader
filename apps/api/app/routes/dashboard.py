"""Admin dashboard: stats + service health."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_version
from app.database import get_db, utcnow
from app.models import DownloadRequest, Payment, Subscription, User
from app.routes.deps import get_current_admin
from app.workers.queue import get_redis, queue_length

log = logging.getLogger("zed.dashboard")

router = APIRouter(
    prefix="/api/admin", tags=["dashboard"], dependencies=[Depends(get_current_admin)]
)


@router.get("/dashboard/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> dict:
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async def _count(query) -> int:
        return int((await db.execute(query)).scalar_one() or 0)

    users_total = await _count(select(func.count(User.id)))
    users_today = await _count(select(func.count(User.id)).where(User.created_at >= day_start))
    downloads_total = await _count(
        select(func.count(DownloadRequest.id)).where(DownloadRequest.status == "completed")
    )
    downloads_today = await _count(
        select(func.count(DownloadRequest.id)).where(
            DownloadRequest.status == "completed", DownloadRequest.completed_at >= day_start
        )
    )
    active_subscriptions = await _count(
        select(func.count(Subscription.id)).where(
            Subscription.is_active.is_(True), Subscription.expires_at > utcnow()
        )
    )

    revenue_total = (
        await db.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "success"))
    ).scalar_one()
    revenue_today = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == "success", Payment.paid_at >= day_start
            )
        )
    ).scalar_one()

    by_status_rows = await db.execute(
        select(DownloadRequest.status, func.count(DownloadRequest.id)).group_by(DownloadRequest.status)
    )
    downloads_by_status = {row[0]: row[1] for row in by_status_rows}

    try:
        pending_jobs = await queue_length()
    except Exception as exc:
        log.warning("queue length unavailable: %s", exc)
        pending_jobs = -1  # -1 = redis unreachable

    return {
        "users_total": users_total,
        "users_today": users_today,
        "downloads_total": downloads_total,
        "downloads_today": downloads_today,
        "active_subscriptions": active_subscriptions,
        "revenue_total": float(revenue_total),
        "revenue_today": float(revenue_today),
        "queue_length": pending_jobs,
        "downloads_by_status": downloads_by_status,
    }


@router.get("/system/health")
async def system_health(db: AsyncSession = Depends(get_db)) -> dict:
    database = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        log.error("db health check failed: %s", exc)
        database = "error"

    redis_status = "ok"
    try:
        await get_redis().ping()
    except Exception as exc:
        log.error("redis health check failed: %s", exc)
        redis_status = "error"

    return {"api": "ok", "database": database, "redis": redis_status, "version": get_version()}
